/**
 * Ollama AI provider.
 *
 * Connects to a local Ollama instance.
 * API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonLines } from '../utils/http.js';
import { Logger, Tag } from '../utils/logger.js';
import { createTokenUsage, getNumberAtPath, getStringAtPath, parseJsonObject, toApiMessages, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions, type TokenUsage } from './types.js';

export class OllamaProvider implements Provider {
    readonly name = 'Ollama';
    readonly defaultUrl = 'http://127.0.0.1:11434/api/chat';

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._url = config.url || this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey || '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = {
            model: this._model,
            messages: toApiMessages(messages),
            stream: Boolean(options.stream),
            think: this._model.toLowerCase().includes('gpt-oss') ? 'medium' : true,
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        const headers: Record<string, string> = {};
        if (this._apiKey) {
            headers['Authorization'] = `Bearer ${this._apiKey}`;
        }

        if (options.stream) {
            let content = '';
            let thinking = '';
            let usage: TokenUsage | undefined;
            await postJsonLines(
                this._session,
                this._url,
                body,
                headers,
                cancellable,
                line => {
                    const parsed = parseJsonObject(line);
                    if (!parsed) return;
                    usage = parseOllamaUsage(parsed) ?? usage;
                    const contentDelta = getStringAtPath(parsed, ['message', 'content']) ?? '';
                    const thinkingDelta = getStringAtPath(parsed, ['message', 'thinking']) ?? '';
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

        const content = getStringAtPath(json, ['message', 'content'])?.trim() || '(no response)';
        const thinking = getStringAtPath(json, ['message', 'thinking'])?.trim();
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content, thinking, usage: parseOllamaUsage(json) };
    }
}

function parseOllamaUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['prompt_eval_count']),
        getNumberAtPath(root, ['eval_count']),
        null
    );
}
