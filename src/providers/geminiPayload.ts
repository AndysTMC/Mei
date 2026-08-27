/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ChatMessage } from './types.js';

export interface GeminiContentBody {
    contents: Array<{ role: string; parts: Array<{ text: string }> }>;
    systemInstruction?: { parts: Array<{ text: string }> };
    generationConfig?: { thinkingConfig: { includeThoughts: boolean } };
}

export function buildGeminiContentBody(messages: ChatMessage[], includeThoughts = false): GeminiContentBody {
    const systemParts: Array<{ text: string }> = [];
    const contents: GeminiContentBody['contents'] = [];

    for (const msg of messages) {
        if (msg.role === 'system') {
            systemParts.push({ text: msg.content });
        } else {
            contents.push({
                role: msg.role === 'assistant' ? 'model' : 'user',
                parts: [{ text: msg.content }],
            });
        }
    }

    return {
        contents,
        ...(systemParts.length > 0 ? { systemInstruction: { parts: systemParts } } : {}),
        ...(includeThoughts ? { generationConfig: { thinkingConfig: { includeThoughts: true } } } : {}),
    };
}

export function buildGeminiGenerateUrl(baseUrl: string, model: string, stream: boolean): string {
    const action = stream ? 'streamGenerateContent?alt=sse' : 'generateContent';
    return `${baseUrl.replace(/\/+$/, '')}/models/${encodeURIComponent(model)}:${action}`;
}
