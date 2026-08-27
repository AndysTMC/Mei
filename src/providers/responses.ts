/**
 * OpenAI Responses API transport.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { getStringAtPath, parseJsonObject, type ChatMessage, type ChatResponse, type Provider, type SendMessageOptions, type TokenUsage } from './types.js';
import { parseResponsesResult, parseResponsesUsage } from './responsesPayload.js';

export class ResponsesProvider implements Provider {
    readonly name: string;
    readonly defaultUrl: string;

    constructor(
        private _session: Soup.Session,
        private _model: string,
        private _apiKey: string,
        name: string,
        url: string,
        private _headers: Readonly<Record<string, string>> = {}
    ) {
        this.name = name;
        this.defaultUrl = url;
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = {
            model: this._model,
            input: messages.map(({ role, content }) => ({
                role: role === 'system' ? 'developer' : role,
                content,
            })),
        };
        const headers = {
            ...this._headers,
            ...(this._apiKey ? { Authorization: `Bearer ${this._apiKey}` } : {}),
        };

        if (!options.stream) {
            return parseResponsesResult(await postJson(this._session, this.defaultUrl, body, headers, cancellable));
        }

        let content = '';
        let thinking = '';
        let usage: TokenUsage | undefined;
        await postJsonSse(
            this._session,
            this.defaultUrl,
            { ...body, stream: true },
            headers,
            cancellable,
            data => {
                const event = parseJsonObject(data);
                if (!event) return;
                const type = getStringAtPath(event, ['type']);
                const delta = getStringAtPath(event, ['delta']) ?? '';
                const contentDelta = type === 'response.output_text.delta' ? delta : '';
                const thinkingDelta = type === 'response.reasoning_summary_text.delta' ? delta : '';
                if (type === 'response.completed') usage = parseResponsesUsage(event);
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
}
