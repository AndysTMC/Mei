/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ChatMessage } from './types.js';

export interface GeminiContentBody {
    contents: Array<{ role: string; parts: Array<{ text: string }> }>;
    systemInstruction?: { parts: Array<{ text: string }> };
}

export function buildGeminiContentBody(messages: ChatMessage[]): GeminiContentBody {
    let systemInstruction: GeminiContentBody['systemInstruction'];
    const contents: GeminiContentBody['contents'] = [];

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

    return systemInstruction ? { contents, systemInstruction } : { contents };
}
