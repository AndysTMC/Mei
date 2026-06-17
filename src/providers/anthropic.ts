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

import { postJson } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import type { ChatMessage, Provider, ProviderConfig } from './types.js';

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
        cancellable: Gio.Cancellable
    ): Promise<string> {
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

        const json = await postJson(
            this._session,
            this._url,
            body,
            headers,
            cancellable
        );

        const reply = json?.content?.[0]?.text?.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(reply, 500)}`);
        return reply;
    }
}
