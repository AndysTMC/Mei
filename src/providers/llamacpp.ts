/**
 * llama.cpp AI provider.
 *
 * Connects to a local llama.cpp server using the OpenAI-compatible
 * /v1/chat/completions endpoint.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag } from '../utils/logger.js';
import { getStringAtPath, parseJsonObject, toApiMessages, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions } from './types.js';

export class LlamaCppProvider implements Provider {
    readonly name = 'llama.cpp';
    readonly defaultUrl = 'http://127.0.0.1:8080/v1/chat/completions';

    private _session: Soup.Session;
    private _url: string;
    private _model: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._url = config.url || this.defaultUrl;
        this._model = config.model;
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
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        if (options.stream) {
            let content = '';
            const streamBody = { ...body, stream: true };
            await postJsonSse(
                this._session,
                this._url,
                streamBody,
                {},
                cancellable,
                data => {
                    const parsed = parseJsonObject(data);
                    if (!parsed) return;
                    const contentDelta = getStringAtPath(parsed, ['choices', 0, 'delta', 'content']) ?? '';
                    if (!contentDelta) return;
                    content += contentDelta;
                    options.onUpdate?.({ contentDelta });
                }
            );
            return { content: content.trim() || '(no response)' };
        }

        const json = await postJson(
            this._session,
            this._url,
            body,
            {},
            cancellable
        );

        const content = getStringAtPath(json, ['choices', 0, 'message', 'content'])?.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return { content };
    }
}
