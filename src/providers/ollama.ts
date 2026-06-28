/**
 * Ollama AI provider.
 *
 * Connects to a local Ollama instance.
 * API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson } from '../utils/http.js';
import { Logger, Tag } from '../utils/logger.js';
import { getStringAtPath, type ChatMessage, type Provider, type ProviderConfig } from './types.js';

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
        cancellable: Gio.Cancellable
    ): Promise<string> {
        const body = {
            model: this._model,
            messages,
            stream: false,
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

        const headers: Record<string, string> = {};
        if (this._apiKey) {
            headers['Authorization'] = `Bearer ${this._apiKey}`;
        }

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        const reply = getStringAtPath(json, ['message', 'content'])?.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(reply, 500)}`);
        return reply;
    }
}
