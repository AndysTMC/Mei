/**
 * OpenAI AI provider.
 *
 * Works with the official OpenAI API and Bearer-authenticated compatible
 * Chat Completions endpoints.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { createTokenUsage, getNumberAtPath, parseJsonObject, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions, type TokenUsage } from './types.js';
import { getDeepSeekReasoningEffort, getDeepSeekThinking } from './catalog.js';
import { buildDeepSeekChatBody, buildOpenAIChatBody } from './openaiPayload.js';
import { extractOpenAIResponseParts, OpenAIStreamNormalizer } from './openaiResponse.js';
import { buildBearerHeaders, buildFireworksHeaders, buildNvidiaHeaders } from './openaiHeaders.js';

export class OpenAICompatibleProvider implements Provider {
    readonly name: string;
    readonly defaultUrl: string;

    private _session: Soup.Session;
    protected _url: string;
    protected _model: string;
    protected _apiKey: string;
    private _defaultHeaders: Readonly<Record<string, string>>;

    constructor(
        session: Soup.Session,
        config: ProviderConfig,
        name: string,
        url: string,
        defaultHeaders: Readonly<Record<string, string>> = {}
    ) {
        this.name = name;
        this.defaultUrl = url;
        this._session = session;
        this._url = config.url || url;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        this._defaultHeaders = defaultHeaders;
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = this._buildBody(messages);

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        const headers = this._buildHeaders();

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

        const response = extractOpenAIResponseParts(json);
        const content = response.content.trim() || '(no response)';
        const thinking = response.thinking.trim() || undefined;
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content, thinking, usage: parseOpenAIUsage(json) };
    }

    protected _buildBody(messages: ChatMessage[]): Record<string, unknown> {
        return buildOpenAIChatBody(this._model, messages);
    }

    protected _buildHeaders(): Record<string, string> {
        return {
            ...this._defaultHeaders,
            ...buildBearerHeaders(this._apiKey),
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
        let usage: TokenUsage | undefined;
        const streamBody = { ...body, stream: true };
        const normalizer = new OpenAIStreamNormalizer();

        const applyUpdate = (contentDelta: string, thinkingDelta: string): void => {
            if (!contentDelta && !thinkingDelta) return;
            content += contentDelta;
            thinking += thinkingDelta;
            options.onUpdate?.({ contentDelta, thinkingDelta });
        };

        await postJsonSse(
            this._session,
            this._url,
            streamBody,
            headers,
            cancellable,
            data => {
                const parsed = parseJsonObject(data);
                if (!parsed) return;
                usage = parseOpenAIUsage(parsed) ?? usage;
                const update = normalizer.consume(parsed);
                applyUpdate(update.contentDelta ?? '', update.thinkingDelta ?? '');
            }
        );
        const tail = normalizer.flush();
        applyUpdate(tail.contentDelta ?? '', tail.thinkingDelta ?? '');

        return {
            content: content.trim() || '(no response)',
            thinking: thinking.trim() || undefined,
            usage,
        };
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

    protected override _buildBody(messages: ChatMessage[]): Record<string, unknown> {
        return buildDeepSeekChatBody(this._model, messages, this._thinking, this._reasoningEffort);
    }
}

export class FireworksProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'Fireworks AI', 'https://api.fireworks.ai/inference/v1/chat/completions');
    }

    protected override _buildHeaders(): Record<string, string> {
        return buildFireworksHeaders(this._apiKey);
    }
}

export class NvidiaProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'NVIDIA NIM', 'https://integrate.api.nvidia.com/v1/chat/completions');
    }

    protected override _buildHeaders(): Record<string, string> {
        return buildNvidiaHeaders(this._apiKey);
    }
}

export class GitHubCopilotProvider extends OpenAICompatibleProvider {
    constructor(session: Soup.Session, config: ProviderConfig) {
        super(session, config, 'GitHub Models', 'https://models.github.ai/inference/chat/completions');
    }

    protected override _buildHeaders(): Record<string, string> {
        return {
            ...super._buildHeaders(),
            Accept: 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10',
        };
    }

    override async sendMessage(
        _messages: ChatMessage[],
        _cancellable: Gio.Cancellable,
        _options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        throw new Error('GitHub Models retired on July 30, 2026. Choose another cloud provider.');
    }
}

function parseOpenAIUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['usage', 'prompt_tokens']) ?? getNumberAtPath(root, ['usage', 'input_tokens']),
        getNumberAtPath(root, ['usage', 'completion_tokens']) ?? getNumberAtPath(root, ['usage', 'output_tokens']),
        getNumberAtPath(root, ['usage', 'total_tokens'])
    );
}
