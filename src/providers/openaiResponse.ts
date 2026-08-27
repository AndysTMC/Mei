/**
 * Normalization for OpenAI-compatible response and stream variants.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { StreamUpdate } from './types.js';

export interface OpenAIResponseParts {
    content: string;
    thinking: string;
}

type JsonRecord = Record<string, unknown>;

const REASONING_TAG_NAMES = [
    'think',
    'thinking',
    'reasoning',
    'thought',
    'reasoning_scratchpad',
] as const;

const OPEN_TAGS = REASONING_TAG_NAMES.map(name => `<${name}>`);
const CLOSE_TAGS = REASONING_TAG_NAMES.map(name => `</${name}>`);
const ALL_TAGS = [...OPEN_TAGS, ...CLOSE_TAGS];
const MAX_TAG_LENGTH = Math.max(...ALL_TAGS.map(tag => tag.length));

export function extractOpenAIResponseParts(root: unknown): OpenAIResponseParts {
    const choice = firstChoice(root);
    const message = asRecord(choice?.message);
    if (!choice) return { content: '', thinking: '' };

    const contentParts = extractTypedContent(message?.content);
    const inline = splitCompleteEmbeddedReasoning(contentParts.content);
    const fallbackText = typeof choice.text === 'string' ? choice.text : '';
    const thinking = joinUniqueParagraphs([
        ...extractStructuredReasoning(message),
        ...contentParts.thinking,
        ...inline.thinking,
    ]);

    return {
        content: inline.content || (contentParts.content ? '' : fallbackText),
        thinking,
    };
}

export class OpenAIStreamNormalizer {
    private _embedded = new EmbeddedReasoningStream();
    private _thinking = '';

    consume(root: unknown): StreamUpdate {
        const choice = firstChoice(root);
        const delta = asRecord(choice?.delta);
        if (!choice) return { contentDelta: '', thinkingDelta: '' };

        const contentParts = extractTypedContent(delta?.content);
        const legacyText = typeof choice.text === 'string' ? choice.text : '';
        const embedded = this._embedded.feed(contentParts.content || legacyText);
        const rawThinking = joinUniqueParagraphs([
            ...extractStructuredReasoning(delta, true),
            ...contentParts.thinking,
            embedded.thinking,
        ], true);
        const thinkingDelta = separateGluedReasoningBlocks(this._thinking, rawThinking);
        this._thinking += thinkingDelta;

        return {
            contentDelta: embedded.content,
            thinkingDelta,
        };
    }

    flush(): StreamUpdate {
        const embedded = this._embedded.flush();
        const thinkingDelta = separateGluedReasoningBlocks(this._thinking, embedded.thinking);
        this._thinking += thinkingDelta;
        return {
            contentDelta: embedded.content,
            thinkingDelta,
        };
    }
}

/** Preserve markdown paragraph boundaries dropped by some Chat Completions relays. */
export function separateGluedReasoningBlocks(previous: string, delta: string): string {
    if (!previous || !delta || !delta.startsWith('**') || previous.at(-1)?.match(/\s/)) {
        return delta;
    }
    if (!delta.slice(2).includes('**')) return delta;
    return `\n\n${delta}`;
}

function firstChoice(root: unknown): JsonRecord | null {
    const record = asRecord(root);
    const choices = record?.choices;
    return Array.isArray(choices) ? asRecord(choices[0]) : null;
}

function asRecord(value: unknown): JsonRecord | null {
    return typeof value === 'object' && value !== null && !Array.isArray(value)
        ? value as JsonRecord
        : null;
}

function extractTypedContent(value: unknown): { content: string; thinking: string[] } {
    if (typeof value === 'string') return { content: value, thinking: [] };
    if (!Array.isArray(value)) return { content: '', thinking: [] };

    let content = '';
    const thinking: string[] = [];
    for (const part of value) {
        const item = asRecord(part);
        if (!item) continue;
        const type = typeof item.type === 'string' ? item.type.toLowerCase() : '';
        const isThinking = type.includes('thinking') || type.includes('reasoning');
        if (isThinking) {
            const text = firstString(item, ['thinking', 'reasoning', 'summary', 'text', 'content']);
            if (text) thinking.push(text);
            continue;
        }

        const text = firstString(item, ['text', 'content', 'output_text']);
        if (text) content += text;
    }
    return { content, thinking };
}

function extractStructuredReasoning(message: JsonRecord | null, preserveWhitespace = false): string[] {
    if (!message) return [];
    const parts: string[] = [];
    for (const key of ['reasoning', 'reasoning_content', 'thinking']) {
        const value = message[key];
        if (typeof value === 'string' && (preserveWhitespace ? value.length > 0 : value.trim().length > 0)) {
            parts.push(value);
        }
    }

    const details = message.reasoning_details;
    if (Array.isArray(details)) {
        for (const detail of details) {
            const item = asRecord(detail);
            const text = item ? firstString(item, ['summary', 'thinking', 'content', 'text']) : '';
            if (text) parts.push(text);
        }
    }
    return uniqueStrings(parts, preserveWhitespace);
}

function firstString(record: JsonRecord, keys: readonly string[]): string {
    for (const key of keys) {
        const value = record[key];
        if (typeof value === 'string' && value) return value;
    }
    return '';
}

function joinUniqueParagraphs(parts: readonly string[], preserveWhitespace = false): string {
    return uniqueStrings(parts, preserveWhitespace).join('\n\n');
}

function uniqueStrings(parts: readonly string[], preserveWhitespace = false): string[] {
    const unique: string[] = [];
    for (const part of parts) {
        if (!part || (!preserveWhitespace && !part.trim()) || unique.includes(part)) continue;
        unique.push(part);
    }
    return unique;
}

function splitCompleteEmbeddedReasoning(text: string): { content: string; thinking: string[] } {
    if (!text) return { content: '', thinking: [] };
    const thinking: string[] = [];
    const tagNames = REASONING_TAG_NAMES.join('|');
    const paired = new RegExp(`<(${tagNames})>([\\s\\S]*?)<\\/\\1>`, 'gi');
    let content = text.replace(paired, (_match: string, _name: string, body: string) => {
        if (body.trim()) thinking.push(body.trim());
        return '';
    });

    const unclosed = new RegExp(`(^|\\n)([ \\t]*)<(${tagNames})>`, 'i').exec(content);
    if (unclosed?.index !== undefined) {
        const bodyStart = unclosed.index + unclosed[0].length;
        const body = content.slice(bodyStart);
        if (body.trim()) thinking.push(body.trim());
        content = content.slice(0, unclosed.index + (unclosed[1]?.length ?? 0));
    }
    return { content: stripOrphanCloseTags(content), thinking };
}

class EmbeddedReasoningStream {
    private _buffer = '';
    private _insideTag: string | null = null;
    private _atLineBoundary = true;

    feed(text: string): { content: string; thinking: string } {
        if (!text) return { content: '', thinking: '' };
        let buffer = this._buffer + text;
        this._buffer = '';
        let content = '';
        let thinking = '';

        while (buffer) {
            if (this._insideTag) {
                const closeTag = `</${this._insideTag}>`;
                const closeIndex = buffer.toLowerCase().indexOf(closeTag);
                if (closeIndex < 0) {
                    const held = maxPartialTagSuffix(buffer, [closeTag]);
                    thinking += held ? buffer.slice(0, -held) : buffer;
                    this._buffer = held ? buffer.slice(-held) : '';
                    return { content, thinking };
                }
                thinking += buffer.slice(0, closeIndex);
                buffer = buffer.slice(closeIndex + closeTag.length);
                this._insideTag = null;
                continue;
            }

            const pair = findClosedPair(buffer);
            const open = findBoundaryOpen(buffer, this._atLineBoundary);
            if (pair && (!open || pair.start <= open.start)) {
                const preceding = stripOrphanCloseTags(buffer.slice(0, pair.start));
                content += preceding;
                this._updateBoundary(preceding);
                thinking += pair.thinking;
                buffer = buffer.slice(pair.end);
                continue;
            }
            if (open) {
                const preceding = stripOrphanCloseTags(buffer.slice(0, open.start));
                content += preceding;
                this._updateBoundary(preceding);
                this._insideTag = open.name;
                buffer = buffer.slice(open.start + open.length);
                continue;
            }

            const held = maxPartialTagSuffix(buffer, ALL_TAGS);
            const visible = stripOrphanCloseTags(held ? buffer.slice(0, -held) : buffer);
            content += visible;
            this._updateBoundary(visible);
            this._buffer = held ? buffer.slice(-held) : '';
            return { content, thinking };
        }

        return { content, thinking };
    }

    flush(): { content: string; thinking: string } {
        const insideTag = this._insideTag !== null;
        const tail = insideTag ? '' : stripOrphanCloseTags(this._buffer);
        this._buffer = '';
        this._insideTag = null;
        this._atLineBoundary = true;
        return { content: tail, thinking: '' };
    }

    private _updateBoundary(text: string): void {
        if (!text) return;
        const lastNewline = text.lastIndexOf('\n');
        if (lastNewline >= 0) {
            this._atLineBoundary = text.slice(lastNewline + 1).trim().length === 0;
        } else if (text.trim()) {
            this._atLineBoundary = false;
        }
    }
}

function findClosedPair(buffer: string): { start: number; end: number; thinking: string } | null {
    const lower = buffer.toLowerCase();
    let best: { start: number; end: number; thinking: string } | null = null;
    for (const name of REASONING_TAG_NAMES) {
        const openTag = `<${name}>`;
        const closeTag = `</${name}>`;
        const start = lower.indexOf(openTag);
        if (start < 0) continue;
        const close = lower.indexOf(closeTag, start + openTag.length);
        if (close < 0) continue;
        const pair = {
            start,
            end: close + closeTag.length,
            thinking: buffer.slice(start + openTag.length, close),
        };
        if (!best || pair.start < best.start) best = pair;
    }
    return best;
}

function findBoundaryOpen(
    buffer: string,
    atLineBoundary: boolean
): { start: number; length: number; name: string } | null {
    const lower = buffer.toLowerCase();
    let best: { start: number; length: number; name: string } | null = null;
    for (const name of REASONING_TAG_NAMES) {
        const tag = `<${name}>`;
        let searchFrom = 0;
        while (searchFrom < buffer.length) {
            const start = lower.indexOf(tag, searchFrom);
            if (start < 0) break;
            const preceding = buffer.slice(0, start);
            const lastNewline = preceding.lastIndexOf('\n');
            const boundary = lastNewline >= 0
                ? preceding.slice(lastNewline + 1).trim().length === 0
                : atLineBoundary && preceding.trim().length === 0;
            if (boundary) {
                const match = { start, length: tag.length, name };
                if (!best || match.start < best.start) best = match;
                break;
            }
            searchFrom = start + 1;
        }
    }
    return best;
}

function maxPartialTagSuffix(buffer: string, tags: readonly string[]): number {
    const lower = buffer.toLowerCase();
    const maxCheck = Math.min(lower.length, MAX_TAG_LENGTH - 1);
    for (let length = maxCheck; length > 0; length--) {
        const suffix = lower.slice(-length);
        if (tags.some(tag => tag.length > length && tag.startsWith(suffix))) return length;
    }
    return 0;
}

function stripOrphanCloseTags(text: string): string {
    if (!text.toLowerCase().includes('</')) return text;
    const tagNames = REASONING_TAG_NAMES.join('|');
    return text.replace(new RegExp(`<\\/(?:${tagNames})>[ \\t\\r\\n]*`, 'gi'), '');
}
