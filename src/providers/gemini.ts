/**
 * Google Gemini AI provider.
 *
 * Uses the Gemini REST API (generateContent endpoint).
 * API docs: https://ai.google.dev/api/generate-content
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import type { ChatMessage, Provider, ProviderConfig } from './types.js';

export class GeminiProvider implements Provider {
    readonly name = 'Gemini';
    readonly defaultUrl = 'https://generativelanguage.googleapis.com/v1beta';

    private _session: Soup.Session;
    private _baseUrl: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._baseUrl = config.url || this.defaultUrl;
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._baseUrl} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable
    ): Promise<string> {
        // Gemini uses 'user' and 'model' roles (not 'assistant').
        // System messages are passed via systemInstruction.
        let systemInstruction: { parts: { text: string }[] } | undefined;
        const contents: Array<{ role: string; parts: Array<{ text: string }> }> = [];

        for (const msg of messages) {
            if (msg.role === 'system') {
                systemInstruction = { parts: [{ text: msg.content }] };
            } else {
                contents.push({
                    role: msg.role === 'assistant' ? 'model' : 'user',
                    parts: [{ text: msg.content }],
                });
            }
        }

        const body: Record<string, unknown> = { contents };
        if (systemInstruction) {
            body.systemInstruction = systemInstruction;
        }

        Logger.debug(Tag.Provider, `${this.name} sending ${contents.length} message(s)${systemInstruction ? ' + system instruction' : ''}`);

        const url = `${this._baseUrl}/models/${this._model}:generateContent?key=${this._apiKey}`;

        const json = await postJson(
            this._session,
            url,
            body,
            {},
            cancellable
        );

        const reply = json?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() ||
            '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(reply, 500)}`);
        return reply;
    }
}
