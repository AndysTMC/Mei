/**
 * Google Gemini AI provider.
 *
 * Uses the Gemini REST API (generateContent endpoint).
 * API docs: https://ai.google.dev/api/generate-content
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';

import { postJson, postJsonSse } from '../utils/http.js';
import { Logger, Tag, maskKey } from '../utils/logger.js';
import { createTokenUsage, getNumberAtPath, parseJsonObject, type ChatMessage, type ChatResponse, type Provider, type ProviderConfig, type SendMessageOptions, type TokenUsage } from './types.js';
import { buildGeminiContentBody, buildGeminiGenerateUrl } from './geminiPayload.js';

export class GeminiProvider implements Provider {
    readonly name = 'Gemini';
    readonly defaultUrl = 'https://generativelanguage.googleapis.com/v1beta';

    private _session: Soup.Session;
    private _baseUrl: string;
    private _model: string;
    private _apiKey: string;

    constructor(session: Soup.Session, config: ProviderConfig) {
        this._session = session;
        this._baseUrl = stripTrailingSlash(config.url || this.defaultUrl);
        this._model = config.model;
        this._apiKey = config.apiKey ?? '';
        Logger.info(Tag.Provider, `Created ${this.name} → ${this._baseUrl} (model: ${this._model}, key: ${maskKey(this._apiKey)})`);
    }

    async sendMessage(
        messages: ChatMessage[],
        cancellable: Gio.Cancellable,
        options: SendMessageOptions = {}
    ): Promise<ChatResponse> {
        const body = buildGeminiContentBody(messages, supportsThoughtSummaries(this._model));

        Logger.debug(Tag.Provider, `${this.name} sending ${body.contents.length} message(s)${body.systemInstruction ? ' + system instruction' : ''}`);

        const url = buildGeminiGenerateUrl(this._baseUrl, this._model, false);
        const headers: Record<string, string> = this._apiKey ? { 'x-goog-api-key': this._apiKey } : {};

        if (options.stream) {
            let content = '';
            let thinking = '';
            let usage: TokenUsage | undefined;
            const streamUrl = buildGeminiGenerateUrl(this._baseUrl, this._model, true);
            await postJsonSse(
                this._session,
                streamUrl,
                body,
                headers,
                cancellable,
                data => {
                    const parsed = parseJsonObject(data);
                    if (!parsed) return;
                    usage = parseGeminiUsage(parsed) ?? usage;
                    const delta = extractGeminiResponse(parsed);
                    const contentDelta = delta.content;
                    const thinkingDelta = delta.thinking ?? '';
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
            url,
            body,
            headers,
            cancellable
        );

        const response = extractGeminiResponse(json);
        const content = response.content.trim() || '(no response)';
        Logger.debug(Tag.Provider, `${this.name} reply: ${Logger.truncate(content, 500)}`);
        return {
            content,
            thinking: response.thinking?.trim() || undefined,
            usage: parseGeminiUsage(json),
        };
    }
}

function parseGeminiUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['usageMetadata', 'promptTokenCount']),
        getNumberAtPath(root, ['usageMetadata', 'candidatesTokenCount']),
        getNumberAtPath(root, ['usageMetadata', 'totalTokenCount'])
    );
}

function extractGeminiResponse(root: unknown): ChatResponse {
    if (typeof root !== 'object' || root === null || Array.isArray(root)) return { content: '' };
    const candidates = (root as Record<string, unknown>).candidates;
    if (!Array.isArray(candidates)) return { content: '' };

    let contentText = '';
    let thinkingText = '';
    for (const candidate of candidates) {
        if (typeof candidate !== 'object' || candidate === null || Array.isArray(candidate)) continue;
        const content = (candidate as Record<string, unknown>).content;
        if (typeof content !== 'object' || content === null || Array.isArray(content)) continue;
        const parts = (content as Record<string, unknown>).parts;
        if (!Array.isArray(parts)) continue;
        for (const part of parts) {
            if (typeof part !== 'object' || part === null || Array.isArray(part)) continue;
            const item = part as Record<string, unknown>;
            if (typeof item.text !== 'string') continue;
            if (item.thought === true) thinkingText += item.text;
            else contentText += item.text;
        }
    }
    return { content: contentText, thinking: thinkingText || undefined };
}

function supportsThoughtSummaries(model: string): boolean {
    return /^gemini-(?:2\.5|3(?:\.|-))/.test(model.toLowerCase());
}

function stripTrailingSlash(url: string): string {
    return url.replace(/\/+$/, '');
}
