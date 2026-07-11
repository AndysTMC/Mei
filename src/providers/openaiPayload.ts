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
