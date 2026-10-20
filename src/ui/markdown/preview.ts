/**
 * What the popup shows of a parsed message: images reduced to text, very long code and lists
 * cut down, and an overall budget of actors so one huge reply can't stall the Shell. Copy
 * buttons keep the full text.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { sanitizeUrl } from './links.js';
import type { MessageBlock, MessageRendererOptions, ParagraphBlock, TableBlock } from './types.js';

const MAX_CODE_CHARS = 30000;
const MAX_RENDER_ACTOR_UNITS = 1000;
const MAX_RENDERED_TABLE_COLUMNS = 12;
const MAX_RENDERED_TABLE_ROWS = 40;
const RENDER_NOTICE_ACTOR_UNITS = 10;
const PREVIEW_OMISSION_TEXT = 'Additional content omitted from the popup preview for popup performance; copy the full response to view it.';

export function sanitizeBlocks(blocks: MessageBlock[], options: MessageRendererOptions): MessageBlock[] {
    const sanitized = blocks.flatMap(block => {
        if (block.type === 'paragraph') {
            return sanitizeParagraph(block, options);
        }
        if (block.type === 'codeBlock' && block.code.length > MAX_CODE_CHARS) {
            return [{
                ...block,
                fullCode: block.code,
                originalCharCount: block.code.length,
                code: `${block.code.slice(0, MAX_CODE_CHARS)}\n\n... preview truncated for popup performance; Copy keeps the full code ...`,
            }];
        }
        return [block];
    });
    return enforceRenderBudget(sanitized);
}

function enforceRenderBudget(blocks: MessageBlock[]): MessageBlock[] {
    const rendered: MessageBlock[] = [];
    let remaining = MAX_RENDER_ACTOR_UNITS - RENDER_NOTICE_ACTOR_UNITS;
    let truncated = false;

    for (const block of blocks) {
        const fitted = fitBlockToBudget(block, remaining);
        if (!fitted) {
            truncated = true;
            break;
        }

        rendered.push(fitted.block);
        remaining -= fitted.actorUnits;
        truncated ||= fitted.truncated;
    }

    if (rendered.length < blocks.length) truncated = true;
    if (truncated) {
        rendered.push({ type: 'paragraph', source: PREVIEW_OMISSION_TEXT, text: PREVIEW_OMISSION_TEXT });
    }

    return rendered;
}

export function appendPreviewOmissionNotice(blocks: MessageBlock[], truncated: boolean): MessageBlock[] {
    if (!truncated || blocks.some(block => block.source === PREVIEW_OMISSION_TEXT)) return blocks;
    return [
        ...blocks,
        { type: 'paragraph', source: PREVIEW_OMISSION_TEXT, text: PREVIEW_OMISSION_TEXT },
    ];
}

function fitBlockToBudget(
    block: MessageBlock,
    remaining: number
): { block: MessageBlock; actorUnits: number; truncated: boolean } | null {
    const baseActorUnits = 10;

    if (block.type === 'orderedList' || block.type === 'unorderedList') {
        const maxItems = Math.floor((remaining - baseActorUnits) / 2);
        if (maxItems < 1) return null;

        const itemCount = Math.min(block.items.length, maxItems);
        return {
            block: itemCount < block.items.length
                ? { ...block, items: block.items.slice(0, itemCount), originalItemCount: block.items.length }
                : block,
            actorUnits: baseActorUnits + itemCount * 2,
            truncated: itemCount < block.items.length,
        };
    }

    if (block.type === 'table') {
        const availableCellUnits = remaining - baseActorUnits;
        if (availableCellUnits < 2) return null;

        const columnCount = Math.min(
            block.headers.length,
            MAX_RENDERED_TABLE_COLUMNS,
            Math.floor(availableCellUnits / 2)
        );
        if (columnCount < 1) return null;

        const rowSlots = Math.floor(availableCellUnits / (columnCount * 2));
        const rowCount = Math.min(block.rows.length, MAX_RENDERED_TABLE_ROWS, Math.max(0, rowSlots - 1));
        const tableTruncated = columnCount < block.headers.length || rowCount < block.rows.length;
        const fittedTable: TableBlock = tableTruncated
            ? {
                ...block,
                headers: block.headers.slice(0, columnCount),
                rows: block.rows.slice(0, rowCount).map(row => row.slice(0, columnCount)),
                alignments: block.alignments.slice(0, columnCount),
                originalRowCount: block.rows.length,
                originalColumnCount: block.headers.length,
            }
            : block;

        return {
            block: fittedTable,
            actorUnits: baseActorUnits + (rowCount + 1) * columnCount * 2,
            truncated: tableTruncated,
        };
    }

    if (remaining < baseActorUnits) return null;
    return { block, actorUnits: baseActorUnits, truncated: false };
}

function sanitizeParagraph(block: ParagraphBlock, options: MessageRendererOptions): MessageBlock[] {
    const image = block.text.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (image) {
        const alt = image[1] || 'image';
        const url = sanitizeUrl(image[2]);
        if (options.allowImages && url) {
            return [{
                ...block,
                text: `Image: ${alt}\n${url}`,
            }];
        }
        return [{
            ...block,
            text: `Image omitted: ${alt}`,
        }];
    }
    return [block];
}

export function blocksToPlainText(blocks: MessageBlock[]): string {
    return blocks.map(block => {
        switch (block.type) {
            case 'paragraph':
            case 'heading':
            case 'blockquote':
                return block.text;
            case 'codeBlock':
                return block.code;
            case 'orderedList':
            case 'unorderedList':
                return block.items.map(item => item.text).join('\n');
            case 'table':
                return block.plainText;
            case 'footnoteDef':
                return `[^${block.id}]: ${block.text}`;
            case 'citation':
                return `[${block.id}] ${block.text}`;
            case 'mathBlock':
                return block.content;
            case 'horizontalRule':
                return '---';
        }
    }).join('\n\n');
}
