/**
 * Anthropic (Claude) AI provider.
 *
 * Uses the Anthropic Messages API.
 * API docs: https://docs.anthropic.com/en/api/messages
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { getStringAtPath, parseJsonObject, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions } from './types.js';

export class AnthropicProvider implements Provider {
    readonly name = 'Anthropic';
    readonly defaultUrl = 'https://api.anthropic.com/v1/messages';

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._url = this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        // Anthropic requires system messages to be passed separately,
        // not in the messages array.
        let systemPrompt: string | undefined;
        const filteredMessages: Array<{ role: string; content: string }> = [];

        for (const msg of messages) {
            if (msg.role === 'system') {
                systemPrompt = msg.content;
            } else {
                filteredMessages.push({
                    role: msg.role,
                    content: msg.content,
                });
            }
        }

        const body: Record<string, unknown> = {
            model: this._model,
            messages: filteredMessages,
            max_tokens: 4096,
        };

        if (systemPrompt) {
            body.system = systemPrompt;
        }

        Logger.debug(Tag.Provider, `${this.name} sending ${filteredMessages.length} message(s)${systemPrompt ? ' + system prompt' : ''}`);

        const headers: Record<string, string> = {
            'x-api-key': this._apiKey,
            'anthropic-version': '2023-06-01',
        };

        if (options.stream) {
            let content = '';
            let thinking = '';
            await postJsonSse(
                this._session,
                this._url,
                { ...body, stream: true },
                headers,
                cancellable,
                data => {
                    const parsed = parseJsonObject(data);
                    if (!parsed) return;
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
        return { content, thinking };
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
