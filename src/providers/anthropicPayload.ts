/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { ChatMessage } from './types.js';

export interface AnthropicMessagesBody {
    model: string;
    messages: Array<{ role: string; content: string }>;
    max_tokens: number;
    system?: string;
    thinking?: { type: 'adaptive'; display: 'summarized' };
}

export function buildAnthropicMessagesBody(
    model: string,
    messages: ChatMessage[],
    maxTokens = 4096,
    adaptiveThinking = false
): AnthropicMessagesBody {
    const systemPrompts: string[] = [];
    const filteredMessages: AnthropicMessagesBody['messages'] = [];

    for (const msg of messages) {
        if (msg.role === 'system') {
            systemPrompts.push(msg.content);
        } else {
            filteredMessages.push({
                role: msg.role,
                content: msg.content,
            });
        }
    }

    const systemPrompt = systemPrompts.join('\n\n');
    return {
        model,
        messages: filteredMessages,
        max_tokens: maxTokens,
        ...(systemPrompt ? { system: systemPrompt } : {}),
        ...(adaptiveThinking ? { thinking: { type: 'adaptive' as const, display: 'summarized' as const } } : {}),
    };
}
