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
import type { ChatMessage, Provider, ProviderConfig } from './types.js';

export class OpenAIProvider implements Provider {
    readonly name = 'OpenAI';
    readonly defaultUrl = 'https://api.openai.com/v1/chat/completions';

    private _session: Soup.Session;
    private _url: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._url = config.url || this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string> {
        const body = {
            model: this._model,
            messages,
        };

        const headers: Record<string, string> = {
            'Authorization': `Bearer ${this._apiKey}`,
        };

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        return json?.choices?.[0]?.message?.content?.trim() || '(no response)';
    }
}
