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

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { getStringAtPath, parseJsonObject, toApiMessages, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions } from './types.js';
import {
    getDeepSeekReasoningEffort,
    getDeepSeekThinking,
    getOpenCodeChatCompletionsUrl,
    getOpenCodeMode,
} from './catalog.js';

export class OpenAICompatibleProvider implements Provider {
    readonly name: string;
    readonly defaultUrl: string;

    private _session: Soup.Session;
    private _url: string;
    protected _model: string;
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
        this._url = config.url || url;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = this._buildBody(messages);

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        const headers: Record<string, string> = {
            'Authorization': `Bearer ${this._apiKey}`,
        };

        // OpenRouter requires an extra header for origin/referer optionally, but we can just use Bearer.

        if (options.stream) {
            return this._sendStreaming(body, headers, cancellable, options);
        }

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        const content = getStringAtPath(json, ['choices', 0, 'message', 'content'])?.trim() || '(no response)';
        const thinking = getFirstStringAtPaths(json, [
            ['choices', 0, 'message', 'reasoning_content'],
            ['choices', 0, 'message', 'reasoning'],
            ['choices', 0, 'message', 'thinking'],
        ])?.trim();
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content, thinking };
    }

    protected _buildBody(messages: ChatMessage[]): Record<string, unknown> {
        return {
            model: this._model,
            messages: toApiMessages(messages),
        };
    }

    private async _sendStreaming(
        body: Record<string, unknown>,
        headers: Record<string, string>,
        cancellable: Gio.Cancellable,
        options: SendMessageOptions
    ): Promise<ChatResponse> {
        let content = '';
        let thinking = '';
        const streamBody = { ...body, stream: true };

        await postJsonSse(
            this._session,
            this._url,
            streamBody,
            headers,
            cancellable,
            data => {
                const parsed = parseJsonObject(data);
                if (!parsed) return;
                const contentDelta = getStringAtPath(parsed, ['choices', 0, 'delta', 'content']) ?? '';
                const thinkingDelta = getFirstStringAtPaths(parsed, [
                    ['choices', 0, 'delta', 'reasoning_content'],
                    ['choices', 0, 'delta', 'reasoning'],
                    ['choices', 0, 'delta', 'thinking'],
                ]) ?? '';
                if (!contentDelta && !thinkingDelta) return;
                content += contentDelta;
                thinking += thinkingDelta;
                options.onUpdate?.({ contentDelta, thinkingDelta });
            }
        );

        return {
            content: content.trim() || '(no response)',
            thinking: thinking.trim() || undefined,
        };
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
    private _thinking: string;
    private _reasoningEffort: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'DeepSeek', 'https://api.deepseek.com/chat/completions');
        this._thinking = getDeepSeekThinking(config.thinking);
        this._reasoningEffort = getDeepSeekReasoningEffort(config.reasoningEffort);
    }

    protected _buildBody(messages: ChatMessage[]): Record<string, unknown> {
        const body = super._buildBody(messages);
        if (this._thinking !== 'default') {
            body.thinking = {
                type: this._thinking,
                ...(this._thinking === 'enabled' ? { reasoning_effort: this._reasoningEffort } : {}),
            };
        }
        return body;
    }
}

export class CustomProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'Custom', config.url || 'http://127.0.0.1:8080/v1/chat/completions');
    }
}

export class OpenCodeProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        const mode = getOpenCodeMode(config.mode);
        super(session, config, `OpenCode ${mode === 'zen' ? 'Zen' : 'Go'}`, getOpenCodeChatCompletionsUrl(mode));
    }
}

function getFirstStringAtPaths(root: unknown, paths: readonly (readonly (string | number)[])[]): string | null {
    for (const path of paths) {
        const value = getStringAtPath(root, path);
        if (value !== null) return value;
    }
    return null;
}
