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

import type { Provider, ProviderConfig, ProviderId, ChatMessage } from './providers/types.js';
import { OllamaProvider } from './providers/ollama.js';
import { LlamaCppProvider } from './providers/llamacpp.js';
import { OpenAIProvider, GroqProvider, MistralProvider, OpenRouterProvider, DeepSeekProvider, CustomProvider, OpenCodeProvider } from './providers/openai.js';
import { AnthropicProvider } from './providers/anthropic.js';
import { GeminiProvider } from './providers/gemini.js';

export default class MeiExtension extends Extension {
    private _indicator: MeiIndicator | null = null;
    private _popup: ChatPopup | null = null;
    private _themeManager: ThemeManager | null = null;
    private _soupSession: Soup.Session | null = null;
    private _cancellable: Gio.Cancellable | null = null;
    private _messages: ChatMessage[] = [];
    private _settings: Gio.Settings | null = null;
    private _provider: Provider | null = null;

    enable(): void {
        Logger.info(Tag.Extension, 'Enabling Mei extension');
        this._soupSession = new Soup.Session({ timeout: 300 });
        this._messages = [];
        this._settings = this.getSettings();

        /* ── Theme ──────────────────────────────────────── */
        this._themeManager = new ThemeManager();

        /* ── Provider ───────────────────────────────────── */
        this._provider = this._createProvider();

        /* ── Panel indicator ────────────────────────────── */
        this._indicator = new MeiIndicator();
        this._indicator.onClicked = () => this._popup?.toggle();
        this._indicator.onStopRequested = () => {
            if (this._cancellable) {
                this._cancellable.cancel();
                Logger.info(Tag.Extension, 'Request cancelled by user');
            }
            this._indicator?.stopGlint();
            this._popup?.open();
        };

        /* ── Chat popup ───────────────────────────────── */
        this._popup = new ChatPopup(this._indicator.actor, this._themeManager);
        this._popup.onSend = (text: string) => this._onSend(text);
        this._popup.onOpenSettings = () => this.openPreferences();

        /* ── Re-create provider when settings change ──── */
        this._settings.connect('changed', (_settings: Gio.Settings, key: string) => {
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

        this._settings = null;
        this._provider = null;
        this._messages = [];
        Logger.info(Tag.Extension, 'Mei extension disabled');
    }

    /* ── Provider factory ─────────────────────────────── */

    private _createProvider(): Provider {
        const session = this._soupSession!;
        const providerId = this._settings!.get_string('provider') as ProviderId;
        const configsJson = this._settings!.get_string('provider-configs');
        let parsedConfigs: Record<string, any> = {};
        try {
            parsedConfigs = JSON.parse(configsJson || '{}');
        } catch (e) {
            Logger.warn(Tag.Extension, `Failed to parse provider-configs: ${e}`);
        }
        const providerConfig = parsedConfigs[providerId] || {};

        const config: ProviderConfig = {
            url: providerConfig.url || '',
            model: providerConfig.modelName || '',
            apiKey: providerConfig.apiKey || '',
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

    private _onSend(text: string): void {
        Logger.debug(Tag.Extension, `User message: ${Logger.truncate(text, 100)}`);
        this._messages.push({ role: 'user', content: text });

        this._popup?.clearMessages();
        this._popup?.close();
        this._indicator?.startGlint();

        this._fetchResponse();
    }

    private async _fetchResponse(): Promise<void> {
        if (!this._soupSession || !this._provider) return;

        this._cancellable = new Gio.Cancellable();
        Logger.info(Tag.Extension, `Fetching response from ${this._provider.name}`);

        try {
            const reply = await this._provider.sendMessage(
                this._messages,
                this._cancellable
            );

            this._messages.push({ role: 'assistant', content: reply });
            this._indicator?.stopGlint();
            this._popup?.showMessage('assistant', reply);
            this._popup?.open();
            Logger.info(Tag.Extension, `Response received (${reply.length} chars)`);
        } catch (e: any) {
            if (!this._cancellable?.is_cancelled()) {
                this._indicator?.stopGlint();
                this._popup?.showMessage(
                    'assistant',
                    `⚠ Could not reach ${this._provider.name}.`
                );
                this._popup?.open();
                Logger.error(Tag.Extension, `${this._provider.name} request failed`, e);
            } else {
                Logger.warn(Tag.Extension, `Request to ${this._provider.name} was cancelled`);
            }
        }
    }
}
