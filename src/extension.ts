/**
 * Mei — AI assistant GNOME Shell extension.
 *
 * This is the main entry point. It wires up the panel indicator,
 * chat popup, theme manager, and the active AI provider.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { MeiIndicator } from './panel/indicator.js';
import { ChatPopup } from './ui/chatPopup.js';
import { ThemeManager } from './utils/theme.js';
import { Logger, Tag } from './utils/logger.js';
import { ChatStore, ChatSession } from './utils/chatStore.js';

import type { Provider, ProviderConfig, ProviderId, ChatMessage, StreamUpdate } from './providers/types.js';
import { OllamaProvider } from './providers/ollama.js';
import { LlamaCppProvider } from './providers/llamacpp.js';
import { OpenAIProvider, GroqProvider, MistralProvider, OpenRouterProvider, DeepSeekProvider, CustomProvider, OpenCodeProvider } from './providers/openai.js';
import { AnthropicProvider } from './providers/anthropic.js';
import { GeminiProvider } from './providers/gemini.js';

type StoredProviderConfig = {
    url?: string;
    modelName?: string;
    apiKey?: string;
    mode?: string;
    thinking?: string;
    reasoningEffort?: string;
};

export default class MeiExtension extends Extension {
    private _indicator: MeiIndicator | null = null;
    private _popup: ChatPopup | null = null;
    private _themeManager: ThemeManager | null = null;
    private _soupSession: Soup.Session | null = null;
    private _cancellable: Gio.Cancellable | null = null;
    private _messages: ChatMessage[] = [];
    private _messagesBackup: ChatMessage[] | null = null;
    private _settings: Gio.Settings | null = null;
    private _settingsSignalId: number = 0;
    private _provider: Provider | null = null;
    private _chatStore: ChatStore | null = null;
    private _chatSessionId: string | null = null;

    enable(): void {
        Logger.info(Tag.Extension, 'Enabling Mei extension');
        this._soupSession = new Soup.Session({ timeout: 300 });
        this._messages = [];
        this._settings = this.getSettings();

        /* ── Theme ──────────────────────────────────────── */
        this._themeManager = new ThemeManager();

        /* ── Store ──────────────────────────────────────── */
        this._chatStore = new ChatStore();
        this._chatSessionId = null;

        /* ── Provider ───────────────────────────────────── */
        this._provider = this._createProvider();

        /* ── Panel indicator ────────────────────────────── */
        this._indicator = new MeiIndicator();
        this._indicator.onClicked = () => this._popup?.toggle();
        this._indicator.onStopRequested = () => {
            this._onCancel();
            this._popup?.open();
        };

        /* ── Chat popup ───────────────────────────────── */
        this._popup = new ChatPopup(this._indicator.actor, this._themeManager, this._settings);
        this._popup.onSend = (text: string) => this._onSend(text);
        this._popup.onCancel = () => this._onCancel();
        this._popup.onOpenSettings = () => this.openPreferences();
        this._popup.onReload = (index: number) => this._onReload(index);
        this._popup.onNewChat = () => this._onNewChat();
        this._popup.onHistoryRequested = () => this._onHistoryRequested();
        this._popup.onLoadChat = (id: string) => this._onLoadChat(id);
        this._popup.onDeleteChat = (id: string) => this._onDeleteChat(id);
        this._popup.onToggleExpand = (isExpanded: boolean) => {
            if (isExpanded) {
                this._popup?.showHistory(this._messages);
            } else {
                this._popup?.showMessage('assistant', getLastAssistantContent(this._messages));
            }
        };

        /* ── Re-create provider when settings change ──── */
        this._settingsSignalId = this._settings.connect('changed', (_settings: Gio.Settings, key: string) => {
            Logger.info(Tag.Extension, `Setting changed: ${key}`);
            this._provider = this._createProvider();
        });

        Logger.info(Tag.Extension, 'Mei extension enabled');
    }

    disable(): void {
        Logger.info(Tag.Extension, 'Disabling Mei extension');
        this._indicator?.destroy();
        this._indicator = null;

        this._popup?.destroy();
        this._popup = null;

        this._themeManager?.destroy();
        this._themeManager = null;

        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
        }

        this._soupSession?.abort();
        this._soupSession = null;

        if (this._settings && this._settingsSignalId !== 0) {
            this._settings.disconnect(this._settingsSignalId);
            this._settingsSignalId = 0;
        }
        this._settings = null;
        this._provider = null;
        this._messages = [];
        this._chatStore = null;
        this._chatSessionId = null;
        Logger.info(Tag.Extension, 'Mei extension disabled');
    }

    /* ── Provider factory ─────────────────────────────── */

    private _createProvider(): Provider {
        const session = this._soupSession!;
        const providerId = this._settings!.get_string('provider') as ProviderId;
        const configsJson = this._settings!.get_string('provider-configs');
        let parsedConfigs: Record<string, StoredProviderConfig> = {};
        try {
            parsedConfigs = parseProviderConfigs(configsJson);
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to parse provider-configs: ${e}`);
        }
        const providerConfig = parsedConfigs[providerId] || {};

        const config: ProviderConfig = {
            url: providerConfig.url || '',
            model: providerConfig.modelName || '',
            apiKey: providerConfig.apiKey || '',
            mode: providerConfig.mode || '',
            thinking: providerConfig.thinking || '',
            reasoningEffort: providerConfig.reasoningEffort || '',
        };

        switch (providerId) {
            case 'llamacpp':
                return new LlamaCppProvider(session, config);
            case 'openai':
                return new OpenAIProvider(session, config);
            case 'groq':
                return new GroqProvider(session, config);
            case 'mistral':
                return new MistralProvider(session, config);
            case 'openrouter':
                return new OpenRouterProvider(session, config);
            case 'deepseek':
                return new DeepSeekProvider(session, config);
            case 'custom':
                return new CustomProvider(session, config);
            case 'opencode':
                return new OpenCodeProvider(session, config);
            case 'anthropic':
                return new AnthropicProvider(session, config);
            case 'gemini':
                return new GeminiProvider(session, config);
            case 'ollama':
            default:
                return new OllamaProvider(session, config);
        }
    }

    /* ── Chat logic ───────────────────────────────────── */

    private _saveCurrentSession(): void {
        if (!this._chatStore) return;

        if (this._messages.length === 0) {
            if (this._chatSessionId) {
                this._chatStore.deleteChat(this._chatSessionId);
                this._chatSessionId = null;
            }
            return;
        }

        if (!this._chatSessionId) {
            this._chatSessionId = ChatStore.generateId();
        }

        const session: ChatSession = {
            id: this._chatSessionId,
            title: ChatStore.generateTitle(this._messages),
            messages: [...this._messages],
            createdAt: Date.now(),
            updatedAt: Date.now(),
        };

        // If the store already has this session, preserve the createdAt timestamp
        const existing = this._chatStore.getChat(this._chatSessionId);
        if (existing) {
            session.createdAt = existing.createdAt;
        }

        this._chatStore.saveChat(session);
    }

    private _onNewChat(): void {
        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
            if (this._messages.length > 0 && this._messages[this._messages.length - 1].role === 'user') {
                this._messages.pop();
                this._saveCurrentSession();
            }
        }
        this._messages = [];
        this._chatSessionId = null;
        this._popup?.clearMessages();
        this._popup?.hideError();
    }

    private _onCancel(): void {
        if (this._cancellable) {
            this._cancellable.cancel();
            Logger.info(Tag.Extension, 'Request cancelled by user via stop button');
        }
        this._indicator?.stopGlint();
        this._popup?.setLoading(false);
    }

    private _onHistoryRequested(): void {
        if (!this._chatStore) return;
        const chats = this._chatStore.loadChats();
        const summaries = chats.map(c => ({ id: c.id, title: c.title }));
        this._popup?.showHistoryList(summaries);
    }

    private _onLoadChat(id: string): void {
        if (!this._chatStore) return;
        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
        }
        const session = this._chatStore.getChat(id);
        if (session) {
            this._chatSessionId = session.id;
            this._messages = [...session.messages];
            this._popup?.showHistory(this._messages);
        }
    }

    private _onDeleteChat(id: string): void {
        if (!this._chatStore) return;
        this._chatStore.deleteChat(id);
        if (this._chatSessionId === id) {
            this._onNewChat(); // Clear current view if we deleted the active chat
        }
    }

    private _onSend(text: string): void {
        if (this._cancellable) {
            Logger.warn(Tag.Extension, 'Ignoring send while a request is already active');
            return;
        }

        Logger.debug(Tag.Extension, `User message: ${Logger.truncate(text, 100)}`);
        this._popup?.hideError();
        this._messages.push({ role: 'user', content: text });
        this._saveCurrentSession();

        if (this._popup?.isExpanded) {
            this._popup.showHistory(this._messages);
        } else {
            this._popup?.clearMessages();
            this._popup?.close();
        }
        this._indicator?.startGlint();

        this._fetchResponse();
    }

    private async _fetchResponse(): Promise<void> {
        if (!this._soupSession || !this._provider) return;

        const provider = this._provider;
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;
        Logger.info(Tag.Extension, `Fetching response from ${provider.name}`);

        this._popup?.setLoading(true);

        try {
            let streamedContent = '';
            let streamedThinking = '';
            const shouldStream = Boolean(this._popup?.isExpanded);
            const reply = await provider.sendMessage(
                this._messages,
                cancellable,
                shouldStream
                    ? {
                        stream: true,
                        onUpdate: (update: StreamUpdate) => {
                            if (cancellable.is_cancelled()) return;
                            streamedContent += update.contentDelta || '';
                            streamedThinking += update.thinkingDelta || '';
                            this._popup?.showStreamingResponse(streamedContent, streamedThinking);
                        },
                    }
                    : undefined
            );

            this._popup?.setLoading(false);

            if (cancellable.is_cancelled()) {
                Logger.warn(Tag.Extension, `Discarding cancelled ${provider.name} response`);
                return;
            }

            this._messages.push({ role: 'assistant', content: reply.content, thinking: reply.thinking });
            this._saveCurrentSession();
            this._messagesBackup = null;
            this._indicator?.stopGlint();

            if (this._popup?.isExpanded) {
                this._popup.showHistory(this._messages);
            } else {
                this._popup?.showMessage('assistant', reply.content);
                this._popup?.open();
            }
            Logger.info(Tag.Extension, `Response received (${reply.content.length} chars)`);
        } catch (e: unknown) {
            this._popup?.setLoading(false);

            if (!cancellable.is_cancelled()) {
                this._indicator?.stopGlint();
                const errMsg = `⚠ Could not reach ${provider.name}. ${getErrorMessage(e)}`;

                if (this._messagesBackup) {
                    this._messages = this._messagesBackup;
                    this._messagesBackup = null;
                    this._saveCurrentSession();
                    if (this._popup?.isExpanded) {
                        this._popup.showHistory(this._messages);
                    }
                    this._popup?.showError(errMsg);
                    this._popup?.open();
                } else {
                    // Remove the user message that caused the error
                    if (this._messages.length > 0 && this._messages[this._messages.length - 1].role === 'user') {
                        this._messages.pop();
                        this._saveCurrentSession();
                    }

                    if (this._popup?.isExpanded) {
                        this._popup.showHistory(this._messages);
                    } else {
                        // In small popup, we just open and show the error, no chat history
                        this._popup?.open();
                    }
                    this._popup?.showError(errMsg);
                }
                Logger.error(Tag.Extension, `${provider.name} request failed`, e);
            } else {
                Logger.warn(Tag.Extension, `Request to ${provider.name} was cancelled`);
                if (this._messagesBackup) {
                    this._messages = this._messagesBackup;
                    this._messagesBackup = null;
                } else {
                    if (this._messages.length > 0 && this._messages[this._messages.length - 1].role === 'user') {
                        this._messages.pop();
                    }
                }
                this._saveCurrentSession();

                if (this._popup?.isExpanded) {
                    this._popup.showHistory(this._messages);
                } else {
                    this._popup?.showMessage('assistant', getLastAssistantContent(this._messages));
                }
            }
        } finally {
            if (this._cancellable === cancellable) {
                this._cancellable = null;
            }
        }
    }

    private _onReload(index: number): void {
        if (index < 0 || index >= this._messages.length || this._messages[index].role !== 'assistant') {
            Logger.warn(Tag.Extension, `Ignoring invalid reload index: ${index}`);
            return;
        }

        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
        }

        Logger.debug(Tag.Extension, `Reload message at index ${index}`);
        this._messagesBackup = [...this._messages];
        this._messages.splice(index);
        this._saveCurrentSession();
        this._popup?.hideError();

        if (this._popup?.isExpanded) {
            this._popup.showHistory(this._messages);
        } else {
            this._popup?.showMessage('assistant', getLastAssistantContent(this._messages));
        }

        this._indicator?.startGlint();
        this._fetchResponse();
    }
}

function parseProviderConfigs(json: string): Record<string, StoredProviderConfig> {
    const parsed = JSON.parse(json || '{}') as unknown;
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return {};
    }

    const configs: Record<string, StoredProviderConfig> = {};
    for (const [provider, value] of Object.entries(parsed)) {
        if (typeof value !== 'object' || value === null || Array.isArray(value)) continue;
        const source = value as Record<string, unknown>;
        configs[provider] = {
            url: typeof source.url === 'string' ? source.url : '',
            modelName: typeof source.modelName === 'string' ? source.modelName : '',
            apiKey: typeof source.apiKey === 'string' ? source.apiKey : '',
            mode: typeof source.mode === 'string' ? source.mode : '',
            thinking: typeof source.thinking === 'string' ? source.thinking : '',
            reasoningEffort: typeof source.reasoningEffort === 'string' ? source.reasoningEffort : '',
        };
    }
    return configs;
}

function getLastAssistantContent(messages: ChatMessage[]): string {
    for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant') {
            return messages[i].content;
        }
    }
    return '';
}

function getErrorMessage(error: unknown): string {
    if (error instanceof Error) return error.message;
    if (typeof error === 'string') return error;
    return '';
}
