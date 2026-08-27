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
    const normalizedModel = model.trim().toLowerCase();
    const supportsThinking = normalizedModel.startsWith('deepseek-v') &&
        !normalizedModel.startsWith('deepseek-v3');
    if (!supportsThinking) return body;

    if (thinking === 'enabled' || thinking === 'disabled') {
        body.thinking = { type: thinking };
        if (thinking === 'enabled') body.reasoning_effort = reasoningEffort;
    }
    return body;
}
