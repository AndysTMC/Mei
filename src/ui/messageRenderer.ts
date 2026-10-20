/**
 * Messages as St actors: parse the Markdown (markdown/parse.ts), trim it to what the popup can
 * show (markdown/preview.ts), and render it (markdown/render.ts). Parses are cached.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import St from 'gi://St';

import { parseMarkdownBlocks, stabilizeMarkdown } from './markdown/parse.js';
import { appendPreviewOmissionNotice, blocksToPlainText, sanitizeBlocks } from './markdown/preview.js';
import { fillMessageActor } from './markdown/render.js';
import type { MessageModel, MessageRendererOptions } from './markdown/types.js';

export type * from './markdown/types.js';

export interface RenderedMessageActor {
    actor: St.BoxLayout;
    model: MessageModel;
    update(markdown: string, options?: Partial<MessageRendererOptions>): void;
    destroy(): void;
}

const MAX_PARSE_CACHE_ENTRIES = 100;
const MAX_CACHE_MARKDOWN_CHARS = 100000;
const MAX_PREVIEW_MARKDOWN_CHARS = 100000;
const MAX_THINKING_PREVIEW_CHARS = 50000;

const parseCache = new Map<string, MessageModel>();

export function renderMessageBlocks(
    markdown: string,
    options: MessageRendererOptions
): MessageModel {
    const cacheKey = options.streaming || markdown.length > MAX_CACHE_MARKDOWN_CHARS
        ? ''
        : `${options.role}:${options.allowImages ? 'img' : 'no-img'}:${options.enableMath ? 'math' : 'no-math'}:${markdown}`;

    if (cacheKey && parseCache.has(cacheKey)) {
        return parseCache.get(cacheKey)!;
    }

    const previewMarkdown = markdown.length > MAX_PREVIEW_MARKDOWN_CHARS
        ? markdown.slice(0, MAX_PREVIEW_MARKDOWN_CHARS)
        : markdown;
    const previewTruncated = previewMarkdown.length < markdown.length;
    const stabilized = stabilizeMarkdown(previewMarkdown, options.streaming ?? false);
    const blocks = appendPreviewOmissionNotice(sanitizeBlocks(parseMarkdownBlocks(stabilized.text, {
        ...options,
        streaming: stabilized.streaming,
    }), options), previewTruncated);

    const model: MessageModel = {
        role: options.role,
        originalMarkdown: markdown,
        stabilizedMarkdown: stabilized.text,
        plainText: blocksToPlainText(blocks),
        blocks,
        isStreaming: stabilized.streaming,
    };

    if (cacheKey) {
        if (parseCache.size >= MAX_PARSE_CACHE_ENTRIES) {
            const oldestKey = parseCache.keys().next().value;
            if (oldestKey) {
                parseCache.delete(oldestKey);
            }
        }
        parseCache.set(cacheKey, model);
    }

    return model;
}

export function formatThinkingPreview(thinking: string): string {
    if (thinking.length <= MAX_THINKING_PREVIEW_CHARS) return thinking;
    return `${thinking.slice(0, MAX_THINKING_PREVIEW_CHARS)}\n\n… thinking preview truncated for popup performance …`;
}

export function createMessageActor(
    markdown: string,
    options: MessageRendererOptions
): RenderedMessageActor {
    let currentOptions = options;
    let model = renderMessageBlocks(markdown, currentOptions);
    const actor = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: options.role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai mei-rendered-message',
    });

    const render = (nextModel: MessageModel, nextOptions: MessageRendererOptions): void => {
        actor.destroy_all_children();
        actor.style_class = nextOptions.role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai mei-rendered-message';
        fillMessageActor(actor, nextModel, nextOptions);
    };

    render(model, currentOptions);

    return {
        actor,
        get model() {
            return model;
        },
        update(markdown: string, nextOptions: Partial<MessageRendererOptions> = {}) {
            currentOptions = { ...currentOptions, ...nextOptions };
            model = renderMessageBlocks(markdown, currentOptions);
            render(model, currentOptions);
        },
        destroy() {
            actor.destroy_all_children();
            actor.destroy();
        },
    };
}
