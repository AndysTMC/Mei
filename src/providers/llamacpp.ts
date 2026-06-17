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

import { postJson } from '../utils/http.js';
import type { ChatMessage, Provider, ProviderConfig } from './types.js';

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
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string> {
        const body = {
            model: this._model,
            messages,
        };

        const json = await postJson(
            this._session,
            this._url,
            body,
            {},
            cancellable
        );

        return json?.choices?.[0]?.message?.content?.trim() || '(no response)';
    }
}
