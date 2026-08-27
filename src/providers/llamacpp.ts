/**
 * llama.cpp AI provider.
 *
 * Connects to a local llama.cpp server using the OpenAI-compatible
 * /v1/chat/completions endpoint.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { createTokenUsage, getNumberAtPath, getStringAtPath, getTextContentAtPath, parseJsonObject, toApiMessages, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions, type TokenUsage } from './types.js';

export class LlamaCppProvider implements Provider {
    readonly name = 'llama.cpp';
    readonly defaultUrl = 'http://127.0.0.1:8080/v1/chat/completions';

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._url = config.url || this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = {
            model: this._model,
            messages: toApiMessages(messages),
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);
        const headers: Record<string, string> = this._apiKey ? { Authorization: `Bearer ${this._apiKey}` } : {};

        if (options.stream) {
            let content = '';
            let thinking = '';
            let usage: TokenUsage | undefined;
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
                    usage = parseOpenAIStyleUsage(parsed) ?? usage;
                    const contentDelta = getTextContentAtPath(parsed, ['choices', 0, 'delta', 'content']) ?? '';
                    const thinkingDelta = getStringAtPath(parsed, ['choices', 0, 'delta', 'reasoning_content']) ??
                        getStringAtPath(parsed, ['choices', 0, 'delta', 'reasoning']) ?? '';
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

        const content = getTextContentAtPath(json, ['choices', 0, 'message', 'content'])?.trim() || '(no response)';
        const thinking = getStringAtPath(json, ['choices', 0, 'message', 'reasoning_content'])?.trim() ||
            getStringAtPath(json, ['choices', 0, 'message', 'reasoning'])?.trim();
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content, thinking, usage: parseOpenAIStyleUsage(json) };
    }
}

function parseOpenAIStyleUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['usage', 'prompt_tokens']) ?? getNumberAtPath(root, ['usage', 'input_tokens']),
        getNumberAtPath(root, ['usage', 'completion_tokens']) ?? getNumberAtPath(root, ['usage', 'output_tokens']),
        getNumberAtPath(root, ['usage', 'total_tokens'])
    );
}
