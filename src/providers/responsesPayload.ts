/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { createTokenUsage, getNumberAtPath, getStringAtPath, type ChatMessage, type ChatResponse, type TokenUsage } from './types.js';

export function buildResponsesBody(model: string, messages: ChatMessage[]): Record<string, unknown> {
    return {
        model,
        store: false,
        input: messages.map(({ role, content }) => ({
            role: role === 'system' ? 'developer' : role,
            content,
        })),
    };
}

export function parseResponsesResult(root: unknown): ChatResponse {
    const failure = getResponsesFailure(root);
    if (failure) throw new Error(failure);

    const direct = getStringAtPath(root, ['output_text']);
    let content = direct ?? '';
    let thinking = '';
    if (typeof root === 'object' && root !== null && !Array.isArray(root)) {
        const output = (root as Record<string, unknown>).output;
        if (Array.isArray(output)) {
            for (const item of output) {
                if (typeof item !== 'object' || item === null || Array.isArray(item)) continue;
                const value = item as Record<string, unknown>;
                const parsedContent = parseResponseBlocks(value.content);
                if (direct === null) content += parsedContent.content;
                thinking += parsedContent.thinking;
                thinking += parseResponseBlocks(value.summary).thinking;
            }
        }
    }
    const incomplete = getResponsesIncompleteReason(root);
    if (incomplete && !content.trim()) throw new Error(incomplete);
    if (incomplete) content = appendIncompleteNotice(content, incomplete);
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

export function getResponsesFailure(root: unknown): string | null {
    const status = getStringAtPath(root, ['status']) ?? getStringAtPath(root, ['response', 'status']);
    const type = getStringAtPath(root, ['type']);
    if (status !== 'failed' && type !== 'response.failed') return null;
    const message = getStringAtPath(root, ['error', 'message']) ??
        getStringAtPath(root, ['response', 'error', 'message']);
    return message?.trim() || 'Response generation failed.';
}

export function getResponsesIncompleteReason(root: unknown): string | null {
    const status = getStringAtPath(root, ['status']) ?? getStringAtPath(root, ['response', 'status']);
    const type = getStringAtPath(root, ['type']);
    if (status !== 'incomplete' && type !== 'response.incomplete') return null;
    const reason = getStringAtPath(root, ['incomplete_details', 'reason']) ??
        getStringAtPath(root, ['response', 'incomplete_details', 'reason']);
    return reason?.trim() ? `Response incomplete: ${reason.trim()}.` : 'Response generation was incomplete.';
}

function parseResponseBlocks(value: unknown): { content: string; thinking: string } {
    if (!Array.isArray(value)) return { content: '', thinking: '' };
    let content = '';
    let thinking = '';
    for (const block of value) {
        if (typeof block !== 'object' || block === null || Array.isArray(block)) continue;
        const item = block as Record<string, unknown>;
        if (item.type === 'output_text' && typeof item.text === 'string') content += item.text;
        if (item.type === 'refusal' && typeof item.refusal === 'string') content += item.refusal;
        if (item.type === 'summary_text' && typeof item.text === 'string') thinking += item.text;
    }
    return { content, thinking };
}

export function appendIncompleteNotice(content: string, reason: string): string {
    return `${content.trim()}\n\n[${reason}]`;
}
