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
import { Logger, Tag, maskKey } from '../utils/logger.js';
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
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._url} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string> {
        const body = {
            model: this._model,
            messages,
        };

        Logger.debug(Tag.Provider, `${this.name} sending ${messages.length} message(s)`);

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

        const reply = json?.choices?.[0]?.message?.content?.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(reply, 500)}`);
        return reply;
    }
}
