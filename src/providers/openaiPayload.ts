/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { toApiMessages, type ChatMessage } from './types.js';

export function buildOpenAIChatBody(
    model: string,
    messages: ChatMessage[]
): Record<string, unknown> {
    return {
        model,
        messages: toApiMessages(messages),
    };
}

export function buildDeepSeekChatBody(
    model: string,
    messages: ChatMessage[],
    thinking: string,
    reasoningEffort: string
): Record<string, unknown> {
    const body = buildOpenAIChatBody(model, messages);
    if (thinking !== 'default') {
        body.thinking = {
            type: thinking,
            ...(thinking === 'enabled' ? { reasoning_effort: reasoningEffort } : {}),
        };
    }
    return body;
}
