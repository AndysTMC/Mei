/**
 * Anthropic (Claude) AI provider.
 *
 * Uses the Anthropic Messages API.
 * API docs: https://docs.anthropic.com/en/api/messages
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { createTokenUsage, getNumberAtPath, getStringAtPath, mergeTokenUsage, parseJsonObject, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions, type TokenUsage } from './types.js';
import { buildAnthropicMessagesBody } from './anthropicPayload.js';

export class AnthropicProvider implements Provider {
    readonly name: string;
    readonly defaultUrl: string;

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;
    private _bearerAuth: boolean;
    private _defaultHeaders: Readonly<Record<string, string>>;

    constructor(
        session: Soup.Session,
        config: ProviderConfig,
        name = 'Anthropic',
        defaultUrl = 'https://api.anthropic.com/v1/messages',
        bearerAuth = false,
        defaultHeaders: Readonly<Record<string, string>> = {}
    ) {
        this.name = name;
        this.defaultUrl = defaultUrl;
        this._session = session;
        this._url = config.url || this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        this._bearerAuth = bearerAuth;
        this._defaultHeaders = defaultHeaders;
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = buildAnthropicMessagesBody(
            this._model,
            messages,
            4096,
            supportsAdaptiveThinking(this._model)
        );

        Logger.debug(Tag.Provider, `${this.name} sending ${body.messages.length} message(s)${body.system ? ' + system prompt' : ''}`);

        const authHeaders: Record<string, string> = !this._apiKey
            ? {}
            : this._bearerAuth
                ? { Authorization: `Bearer ${this._apiKey}` }
                : { 'x-api-key': this._apiKey };
        const headers: Record<string, string> = {
            ...this._defaultHeaders,
            ...authHeaders,
            'anthropic-version': '2023-06-01',
        };

        if (options.stream) {
            let content = '';
            let thinking = '';
            let usage: TokenUsage | undefined;
            await postJsonSse(
                this._session,
                this._url,
                { ...body, stream: true },
                headers,
                cancellable,
                data => {
                    const parsed = parseJsonObject(data);
                    if (!parsed) return;
                    usage = mergeTokenUsage(usage, parseAnthropicUsage(parsed));
                    const deltaType = getStringAtPath(parsed, ['delta', 'type']);
                    const contentDelta = deltaType === 'text_delta'
                        ? getStringAtPath(parsed, ['delta', 'text']) ?? ''
                        : '';
                    const thinkingDelta = deltaType === 'thinking_delta'
                        ? getStringAtPath(parsed, ['delta', 'thinking']) ?? ''
                        : '';
                    if (!contentDelta && !thinkingDelta) return;
                    content += contentDelta;
                    thinking += thinkingDelta;
                    options.onUpdate?.({ contentDelta, thinkingDelta });
                }
            );
            return {
                content: content.trim() || '(no response)',
                thinking: thinking.trim() || undefined,
                usage,
            };
        }

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        const { content, thinking } = parseAnthropicContent(json);
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content, thinking, usage: parseAnthropicUsage(json) };
    }
}

function parseAnthropicContent(json: unknown): ChatResponse {
    if (typeof json !== 'object' || json === null || Array.isArray(json)) {
        return { content: '(no response)' };
    }
    const contentBlocks = (json as Record<string, unknown>).content;
    if (!Array.isArray(contentBlocks)) return { content: '(no response)' };

    let content = '';
    let thinking = '';
    for (const block of contentBlocks) {
        if (typeof block !== 'object' || block === null || Array.isArray(block)) continue;
        const item = block as Record<string, unknown>;
        if (item.type === 'text' && typeof item.text === 'string') content += item.text;
        if (item.type === 'thinking' && typeof item.thinking === 'string') thinking += item.thinking;
    }

    return {
        content: content.trim() || '(no response)',
        thinking: thinking.trim() || undefined,
    };
}

function parseAnthropicUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['usage', 'input_tokens']) ??
            getNumberAtPath(root, ['message', 'usage', 'input_tokens']),
        getNumberAtPath(root, ['usage', 'output_tokens']),
        null
    );
}

function supportsAdaptiveThinking(model: string): boolean {
    const id = model.toLowerCase();
    return /(?:opus-4-[678]|sonnet-4-6|fable-5|sonnet-5|mythos-5)/.test(id);
}
