/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ChatMessage } from './types.js';

export interface AnthropicMessagesBody {
    model: string;
    messages: Array<{ role: string; content: string }>;
    max_tokens: number;
    system?: string;
}

export function buildAnthropicMessagesBody(
    model: string,
    messages: ChatMessage[],
    maxTokens = 4096
): AnthropicMessagesBody {
    let systemPrompt: string | undefined;
    const filteredMessages: AnthropicMessagesBody['messages'] = [];

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

    return {
        model,
        messages: filteredMessages,
        max_tokens: maxTokens,
        ...(systemPrompt ? { system: systemPrompt } : {}),
    };
}
