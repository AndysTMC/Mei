/**
 * OpenAI AI provider.
 *
 * Works with the official OpenAI API and any compatible endpoint
 * (Azure OpenAI, Together AI, Groq, etc.).
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import type { ChatMessage, Provider, ProviderConfig } from './types.js';

export class OpenAICompatibleProvider implements Provider {
    readonly name: string;
    readonly defaultUrl: string;

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;

    constructor(
        session: Soup.Session,
        config: ProviderConfig,
        name: string,
        url: string
    ) {
        this.name = name;
        this.defaultUrl = url;
        this._session = session;
        this._url = url;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string> {
        const body = {
            model: this._model,
            messages,
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        const headers: Record<string, string> = {
            'Authorization': `Bearer ${this._apiKey}`,
        };

        // OpenRouter requires an extra header for origin/referer optionally, but we can just use Bearer.

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        const reply = json?.choices?.[0]?.message?.content?.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(reply, 500)}`);
        return reply;
    }
}

export class OpenAIProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'OpenAI', 'https://api.openai.com/v1/chat/completions');
    }
}

export class GroqProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'Groq', 'https://api.groq.com/openai/v1/chat/completions');
    }
}

export class MistralProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'Mistral', 'https://api.mistral.ai/v1/chat/completions');
    }
}

export class OpenRouterProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'OpenRouter', 'https://openrouter.ai/api/v1/chat/completions');
    }
}

export class DeepSeekProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'DeepSeek', 'https://api.deepseek.com/chat/completions');
    }
}

export class CustomProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'Custom', config.url || 'http://127.0.0.1:8080/v1/chat/completions');
    }
}

export class OpenCodeProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'OpenCode', 'https://opencode.ai/zen/go/v1/chat/completions');
    }
}
