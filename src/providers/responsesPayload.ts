/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { createTokenUsage, getNumberAtPath, getStringAtPath, type ChatResponse, type TokenUsage } from './types.js';

export function parseResponsesResult(root: unknown): ChatResponse {
    const direct = getStringAtPath(root, ['output_text']);
    let content = direct ?? '';
    let thinking = '';
    if (typeof root === 'object' && root !== null && !Array.isArray(root)) {
        const output = (root as Record<string, unknown>).output;
        if (Array.isArray(output)) {
            for (const item of output) {
                if (typeof item !== 'object' || item === null || Array.isArray(item)) continue;
                const blocks = (item as Record<string, unknown>).content;
                if (!Array.isArray(blocks)) continue;
                for (const block of blocks) {
                    if (typeof block !== 'object' || block === null || Array.isArray(block)) continue;
                    const value = block as Record<string, unknown>;
                    if (value.type === 'output_text' && typeof value.text === 'string') content += value.text;
                    if (value.type === 'summary_text' && typeof value.text === 'string') thinking += value.text;
                }
            }
        }
    }
    return {
        content: content.trim() || '(no response)',
        thinking: thinking.trim() || undefined,
        usage: parseResponsesUsage(root),
    };
}

export function parseResponsesUsage(root: unknown): TokenUsage | undefined {
    return createTokenUsage(
        getNumberAtPath(root, ['usage', 'input_tokens']) ?? getNumberAtPath(root, ['response', 'usage', 'input_tokens']),
        getNumberAtPath(root, ['usage', 'output_tokens']) ?? getNumberAtPath(root, ['response', 'usage', 'output_tokens']),
        getNumberAtPath(root, ['usage', 'total_tokens']) ?? getNumberAtPath(root, ['response', 'usage', 'total_tokens'])
    );
}
