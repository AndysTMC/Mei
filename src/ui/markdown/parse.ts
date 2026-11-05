/**
 * Markdown → blocks. Line-based and forgiving: an unfinished fence while streaming stays a
 * code block marked as generating.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import type { HeadingBlock, InlineAlignment, ListBlock, MessageBlock, MessageRendererOptions, TableBlock } from './types.js';

export function stabilizeMarkdown(markdown: string, streaming: boolean): { text: string; streaming: boolean } {
    const normalized = markdown.replace(/\r\n?/g, '\n');
    if (!streaming) {
        return { text: normalized, streaming: false };
    }

    const fenceCount = (normalized.match(/(^|\n)(```|~~~)/g) ?? []).length;
    if (fenceCount % 2 !== 0) {
        return { text: normalized, streaming: true };
    }

    return { text: normalized, streaming };
}

export function parseMarkdownBlocks(markdown: string, options: MessageRendererOptions): MessageBlock[] {
    const blocks: MessageBlock[] = [];
    const lines = markdown.split('\n');
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];
        if (line.trim() === '') {
            i++;
            continue;
        }

        const fence = line.match(/^\s*(```|~~~)\s*([A-Za-z0-9_+.#-]*)\s*$/);
        if (fence) {
            const marker = fence[1];
            const language = fence[2] ?? '';
            const start = i;
            i++;
            const codeLines: string[] = [];
            let closed = false;
            while (i < lines.length) {
                if (new RegExp(`^\\s*${escapeRegExp(marker)}\\s*$`).test(lines[i])) {
                    closed = true;
                    i++;
                    break;
                }
                codeLines.push(lines[i]);
                i++;
            }

            const source = lines.slice(start, i).join('\n');
            const code = codeLines.join('\n');
            blocks.push({
                type: 'codeBlock',
                source,
                language,
                code,
                isStreaming: options.streaming === true && !closed,
                isDiagramSource: language.toLowerCase() === 'mermaid',
            });
            continue;
        }

        if (options.enableMath !== false && line.trim() === '$$') {
            const start = i;
            i++;
            const mathLines: string[] = [];
            let closed = false;
            while (i < lines.length) {
                if (lines[i].trim() === '$$') {
                    closed = true;
                    i++;
                    break;
                }
                mathLines.push(lines[i]);
                i++;
            }
            blocks.push({
                type: 'mathBlock',
                source: lines.slice(start, i).join('\n'),
                content: mathLines.join('\n'),
                isStreaming: options.streaming === true && !closed,
            });
            continue;
        }

        if (isTableStart(lines, i)) {
            const start = i;
            const header = splitTableRow(lines[i]);
            const alignments = splitTableRow(lines[i + 1]).map(parseAlignment);
            i += 2;
            const rows: string[][] = [];
            while (i < lines.length && isPipeRow(lines[i])) {
                rows.push(splitTableRow(lines[i]));
                i++;
            }
            const source = lines.slice(start, i).join('\n');
            blocks.push(createTableBlock(header, rows, alignments, source));
            continue;
        }

        const heading = line.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
            blocks.push({
                type: 'heading',
                source: line,
                level: heading[1].length as HeadingBlock['level'],
                text: heading[2],
            });
            i++;
            continue;
        }

        if (/^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
            blocks.push({ type: 'horizontalRule', source: line });
            i++;
            continue;
        }

        const footnote = line.match(/^\[\^([^\]]+)\]:\s*(.+)$/);
        if (footnote) {
            blocks.push({
                type: 'footnoteDef',
                source: line,
                id: footnote[1],
                text: footnote[2],
            });
            i++;
            continue;
        }

        const citation = line.match(/^\[(\d+)\]\s+(.+)$/);
        if (citation) {
            blocks.push({
                type: 'citation',
                source: line,
                id: citation[1],
                text: citation[2],
            });
            i++;
            continue;
        }

        if (/^\s*>/.test(line)) {
            const quoteLines: string[] = [];
            const start = i;
            while (i < lines.length && /^\s*>/.test(lines[i])) {
                quoteLines.push(lines[i].replace(/^\s*>\s?/, ''));
                i++;
            }
            blocks.push({
                type: 'blockquote',
                source: lines.slice(start, i).join('\n'),
                text: quoteLines.join('\n'),
            });
            continue;
        }

        if (/^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(line)) {
            const start = i;
            const ordered = /^\s*\d+[.)]\s+/.test(line);
            const items: ListBlock['items'] = [];
            const base = (line.match(/^\s*/)?.[0] ?? '').length;
            while (i < lines.length && /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(lines[i])) {
                const marker = lines[i].match(/^(\s*)(?:[-*+]|(\d+)[.)])\s+/)!;
                const itemText = lines[i].slice(marker[0].length);
                const task = itemText.match(/^\[([ xX])\]\s+(.+)$/);
                items.push({
                    text: task ? task[2] : itemText,
                    checked: task ? task[1].toLowerCase() === 'x' : undefined,
                    task: task !== null,
                    // Each item's own marker, so "2." after a paragraph is 2, and bullets under a
                    // numbered item stay bullets, one level in.
                    ...(marker[2] !== undefined ? { number: Number(marker[2]) } : {}),
                    depth: Math.max(0, Math.floor((marker[1].length - base) / 2)),
                });
                i++;
            }
            blocks.push({
                type: ordered ? 'orderedList' : 'unorderedList',
                source: lines.slice(start, i).join('\n'),
                items,
            });
            continue;
        }

        const paragraphLines: string[] = [];
        const start = i;
        while (i < lines.length && lines[i].trim() !== '' && !startsBlock(lines, i)) {
            paragraphLines.push(lines[i]);
            i++;
        }
        if (paragraphLines.length === 0) {
            paragraphLines.push(line);
            i++;
        }
        blocks.push({
            type: 'paragraph',
            source: lines.slice(start, i).join('\n'),
            text: paragraphLines.join('\n'),
        });
    }

    return blocks.length > 0 ? blocks : [{ type: 'paragraph', source: markdown, text: markdown }];
}

function createTableBlock(headers: string[], rows: string[][], alignments: InlineAlignment[], source: string): TableBlock {
    const normalizedAlignments = headers.map((_header, index) => alignments[index] ?? 'left');
    const normalizedRows = rows.map(row => headers.map((_header, index) => row[index] ?? ''));
    return {
        type: 'table',
        source,
        headers,
        rows: normalizedRows,
        alignments: normalizedAlignments,
        markdown: source,
        plainText: tableToPlainText(headers, normalizedRows),
        csv: tableToCsv(headers, normalizedRows),
    };
}

function startsBlock(lines: string[], index: number): boolean {
    const line = lines[index];
    return line.trim() === '' ||
        /^\s*(```|~~~)/.test(line) ||
        /^\s*#{1,6}\s+/.test(line) ||
        /^\s{0,3}(-{3,}|\*{3,}|_{3,})\s*$/.test(line) ||
        /^\s*>/.test(line) ||
        /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(line) ||
        /^\[\^([^\]]+)\]:\s+/.test(line) ||
        /^\[(\d+)\]\s+/.test(line) ||
        isTableStart(lines, index);
}

function isTableStart(lines: string[], index: number): boolean {
    if (index + 1 >= lines.length) return false;
    return isPipeRow(lines[index]) && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1]);
}

function isPipeRow(line: string): boolean {
    return line.includes('|') && line.trim().length > 1;
}

function splitTableRow(line: string): string[] {
    const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
    const cells: string[] = [];
    let cell = '';
    let escaped = false;

    for (const character of trimmed) {
        if (escaped) {
            cell += `\\${character}`;
            escaped = false;
            continue;
        }
        if (character === '\\') {
            escaped = true;
            continue;
        }
        if (character === '|') {
            cells.push(cell.trim());
            cell = '';
            continue;
        }
        cell += character;
    }

    if (escaped) {
        cell += '\\';
    }
    cells.push(cell.trim());
    return cells;
}

function parseAlignment(cell: string): InlineAlignment {
    const trimmed = cell.trim();
    if (trimmed.startsWith(':') && trimmed.endsWith(':')) return 'center';
    if (trimmed.endsWith(':')) return 'right';
    return 'left';
}

function tableToPlainText(headers: string[], rows: string[][]): string {
    const allRows = [headers, ...rows];
    const widths = headers.map((_header, index) =>
        Math.max(...allRows.map(row => (row[index] ?? '').length))
    );
    return allRows.map(row =>
        row.map((cell, index) => (cell ?? '').padEnd(widths[index] ?? 0)).join('  ')
    ).join('\n');
}

function tableToCsv(headers: string[], rows: string[][]): string {
    return [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\n');
}

function csvCell(value: string): string {
    const escaped = value.replace(/"/g, '""');
    return /[",\n]/.test(value) ? `"${escaped}"` : escaped;
}

function escapeRegExp(text: string): string {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
