/**
 * Mei — AI assistant GNOME Shell extension.
 *
 * This is the main entry point. It wires up the panel indicator,
 * chat popup, theme manager, and the active AI provider.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import { MeiIndicator } from './panel/indicator.js';
import { ChatPopup } from './ui/chatPopup.js';
import { ThemeManager } from './utils/theme.js';
import { Logger, Tag } from './utils/logger.js';
import { ChatStore, ChatSession } from './utils/chatStore.js';

import type { ChatMessage, ChatMessageMetadata, Provider, ProviderConfig, ProviderId, StreamUpdate } from './providers/types.js';
import { getProviderLabel, getProviderType, PROVIDER_TYPE_LABELS } from './providers/catalog.js';
import { migratePlaintextApiKeys, resolveStoredProviderConfig } from './providers/apiKeys.js';
import { createEmptyProviderConfig, mergeMigratedApiKeyConfigs, parseProviderConfigs, type StoredProviderConfig } from './providers/configStore.js';
import { createRuntimeProvider, resolveProviderRuntime } from './providers/runtime.js';
import { resolveProviderId } from './providers/profiles.js';

interface ProviderBuildResult {
    provider: Provider;
    metadata: ChatMessageMetadata;
}

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
    private _providerRefreshTimeoutId: number = 0;
    private _providerRefreshSeq: number = 0;
    private _providerReadyPromise: Promise<void> | null = null;
    private _provider: Provider | null = null;
    private _providerMetadata: ChatMessageMetadata | null = null;
    private _chatStore: ChatStore | null = null;
    private _chatSessionId: string | null = null;
    private _isStreamingResponse = false;

    override enable(): void {
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
        this._providerReadyPromise = this._refreshProviderNow();

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
            this._syncIndicatorState();
        };
        this._popup.onOpenStateChanged = () => this._syncIndicatorState();
        this._syncIndicatorState();

        /* ── Re-create provider when settings change ──── */
        this._settingsSignalId = this._settings.connect('changed', (_settings: Gio.Settings, key: string) => {
            Logger.info(Tag.Extension, `Setting changed: ${key}`);
            this._queueProviderRefresh();
        });

        Logger.info(Tag.Extension, 'Mei extension enabled');
    }

    override disable(): void {
        Logger.info(Tag.Extension, 'Disabling Mei extension');
        const chatStore = this._chatStore;

        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
        }
        this._isStreamingResponse = false;
        this._popup?.setLoading(false);
        this._syncIndicatorState();

        this._popup?.destroy();
        this._popup = null;

        this._indicator?.destroy();
        this._indicator = null;

        this._themeManager?.destroy();
        this._themeManager = null;

        this._soupSession?.abort();
        this._soupSession = null;

        if (this._settings && this._settingsSignalId !== 0) {
            this._settings.disconnect(this._settingsSignalId);
            this._settingsSignalId = 0;
        }
        if (this._providerRefreshTimeoutId !== 0) {
            GLib.source_remove(this._providerRefreshTimeoutId);
            this._providerRefreshTimeoutId = 0;
        }
        this._providerRefreshSeq++;
        this._providerReadyPromise = null;
        this._settings = null;
        this._provider = null;
        this._providerMetadata = null;
        this._messages = [];
        this._chatStore = null;
        this._chatSessionId = null;
        void chatStore?.flush().catch(e => {
            Logger.error(Tag.Extension, 'Failed to flush chat history on disable', e);
        });
        Logger.info(Tag.Extension, 'Mei extension disabled');
    }

    /* ── Provider factory ─────────────────────────────── */

    private _queueProviderRefresh(): void {
        if (this._providerRefreshTimeoutId !== 0) {
            GLib.source_remove(this._providerRefreshTimeoutId);
        }

        this._providerRefreshTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this._providerRefreshTimeoutId = 0;
            if (!this._settings || !this._soupSession) return GLib.SOURCE_REMOVE;
            this._providerReadyPromise = this._refreshProviderNow();
            return GLib.SOURCE_REMOVE;
        });
    }

    private _flushQueuedProviderRefresh(): Promise<void> | null {
        if (this._providerRefreshTimeoutId !== 0) {
            GLib.source_remove(this._providerRefreshTimeoutId);
            this._providerRefreshTimeoutId = 0;
            this._providerReadyPromise = this._refreshProviderNow();
        }
        return this._providerReadyPromise;
    }

    private async _refreshProviderNow(): Promise<void> {
        const seq = ++this._providerRefreshSeq;
        try {
            const result = await this._createProvider();
            if (seq !== this._providerRefreshSeq || !this._settings || !this._soupSession) return;
            this._provider = result.provider;
            this._providerMetadata = result.metadata;
        } catch (e) {
            if (seq !== this._providerRefreshSeq) return;
            this._provider = null;
            this._providerMetadata = null;
            Logger.error(Tag.Extension, 'Failed to create provider', e);
        }
    }

    private async _createProvider(): Promise<ProviderBuildResult> {
        const session = this._soupSession!;
        const storedProviderId = this._settings!.get_string('provider');
        const providerId: ProviderId = resolveProviderId(storedProviderId) ?? 'openai';
        if (providerId !== storedProviderId) this._settings!.set_string('provider', providerId);
        const configsJson = this._settings!.get_string('provider-configs');
        let parsedConfigs: Record<string, StoredProviderConfig> = {};
        try {
            parsedConfigs = parseProviderConfigs(configsJson);
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to parse provider-configs: ${e}`);
        }
        const migrated = await migratePlaintextApiKeys(parsedConfigs);
        let effectiveConfigs = migrated.configs;
        if (migrated.changed && this._settings) {
            const currentConfigs = parseProviderConfigs(this._settings.get_string('provider-configs'));
            effectiveConfigs = mergeMigratedApiKeyConfigs(parsedConfigs, migrated.configs, currentConfigs);
            this._settings.set_string('provider-configs', JSON.stringify(effectiveConfigs));
        }

        const providerConfig = await resolveStoredProviderConfig(
            providerId,
            effectiveConfigs[providerId] || createEmptyProviderConfig()
        );

        const config: ProviderConfig = {
            url: providerConfig.url || '',
            model: providerConfig.modelName || '',
            apiKey: providerConfig.apiKey || '',
            mode: providerConfig.mode || '',
            thinking: providerConfig.thinking || '',
            reasoningEffort: providerConfig.reasoningEffort || '',
        };

        const provider = createRuntimeProvider(session, providerId, config);
        const runtime = resolveProviderRuntime(providerId, config);

        const providerType = getProviderType(this._settings!.get_string('provider-type'));
        const metadata: ChatMessageMetadata = {
            providerId,
            providerLabel: getProviderLabel(providerId),
            providerType: PROVIDER_TYPE_LABELS[providerType],
            model: config.model,
            endpoint: sanitizeEndpoint(runtime.url),
        };
        return { provider, metadata };
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
        this._isStreamingResponse = false;
        this._syncIndicatorState();
        this._popup?.setLoading(false);
        this._messagesBackup = null;
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
        this._isStreamingResponse = false;
        this._syncIndicatorState();
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
            this._isStreamingResponse = false;
            this._syncIndicatorState();
            this._popup?.setLoading(false);
        }
        const session = this._chatStore.getChat(id);
        if (session) {
            this._messagesBackup = null;
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
        this._isStreamingResponse = true;
        this._syncIndicatorState();

        this._fetchResponse();
    }

    private async _fetchResponse(): Promise<void> {
        if (!this._soupSession) return;

        let provider: Provider | null = null;
        let providerMetadata: ChatMessageMetadata | null = null;
        const cancellable = new Gio.Cancellable();
        this._cancellable = cancellable;
        this._isStreamingResponse = true;
        this._syncIndicatorState();
        const startedAt = Date.now();

        this._popup?.setLoading(true);

        try {
            await this._flushQueuedProviderRefresh();
            provider = this._provider;
            if (!provider) throw new Error('AI provider is not ready.');
            providerMetadata = this._providerMetadata ? { ...this._providerMetadata } : null;
            Logger.info(Tag.Extension, `Fetching response from ${provider.name}`);

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

            if (cancellable.is_cancelled()) {
                if (this._cancellable !== cancellable) {
                    Logger.warn(Tag.Extension, `Discarding stale cancelled ${provider.name} response`);
                    return;
                }
                this._popup?.setLoading(false);
                Logger.warn(Tag.Extension, `Discarding cancelled ${provider.name} response`);
                return;
            }

            this._popup?.setLoading(false);

            this._messages.push({
                role: 'assistant',
                content: reply.content,
                thinking: reply.thinking,
                metadata: {
                    ...(providerMetadata ?? {}),
                    durationMs: Date.now() - startedAt,
                    tokens: reply.usage,
                },
            });
            this._saveCurrentSession();
            this._messagesBackup = null;

            if (this._popup?.isExpanded) {
                this._popup.showHistory(this._messages, true);
            } else {
                this._popup?.showMessage('assistant', reply.content);
                this._popup?.open();
            }
            Logger.info(Tag.Extension, `Response received (${reply.content.length} chars)`);
        } catch (e: unknown) {
            if (cancellable.is_cancelled() && this._cancellable !== cancellable) {
                Logger.warn(Tag.Extension, `Ignoring stale cancelled request to ${provider?.name ?? 'AI provider'}`);
                return;
            }

            this._popup?.setLoading(false);

            if (!cancellable.is_cancelled()) {
                const providerName = provider?.name ?? 'AI provider';
                const errMsg = `⚠ Could not reach ${providerName}. ${getErrorMessage(e)}`;

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
                Logger.error(Tag.Extension, `${providerName} request failed`, e);
            } else {
                Logger.warn(Tag.Extension, `Request to ${provider?.name ?? 'AI provider'} was cancelled`);
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
                this._isStreamingResponse = false;
                this._syncIndicatorState();
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
            this._isStreamingResponse = false;
            this._syncIndicatorState();
            this._popup?.setLoading(false);
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

        this._isStreamingResponse = true;
        this._syncIndicatorState();
        this._fetchResponse();
    }

    private _syncIndicatorState(): void {
        if (!this._indicator) return;

        const isStreaming = this._isStreamingResponse;
        const popupOpen = Boolean(this._popup?.isOpen);
        const popupExpanded = Boolean(this._popup?.isExpanded);

        this._indicator.setStopControlVisible(isStreaming && popupOpen && !popupExpanded);
        this._indicator.setActivity(isStreaming && !popupOpen);
    }
}

function getLastAssistantContent(messages: ChatMessage[]): string {
    for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant') {
            return messages[i].content;
        }
    }
    return '';
}

function sanitizeEndpoint(url: string): string {
    const trimmed = url.trim();
    if (!trimmed) return '';

    const match = trimmed.match(/^([a-z][a-z0-9+.-]*:\/\/[^/?#]+)([^?#]*)/i);
    if (match) {
        return `${match[1]}${match[2] || ''}`;
    }
    return trimmed.split(/[?#]/)[0];
}

function getErrorMessage(error: unknown): string {
    if (error instanceof Error) return error.message;
    if (typeof error === 'string') return error;
    return '';
}
