/**
 * Structured Markdown message renderer for the Shell popup.
 *
 * The renderer owns parsing/sanitization and produces St actors that the
 * existing popup can place in its message area.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import Cogl from 'gi://Cogl';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import {
    extractLinks as extractTextLinks,
    inlineMarkup as inlineTextMarkup,
    sanitizeUrl as sanitizeTextUrl,
    stripPangoTags,
    type LinkTarget,
} from './messageText.js';

export type MessageRole = 'user' | 'assistant' | 'system';

export type InlineAlignment = 'left' | 'center' | 'right';

export type MessageBlock =
    | ParagraphBlock
    | HeadingBlock
    | CodeBlock
    | BlockquoteBlock
    | ListBlock
    | TableBlock
    | HorizontalRuleBlock
    | FootnoteBlock
    | CitationBlock
    | MathBlock;

export interface MessageModel {
    role: MessageRole;
    originalMarkdown: string;
    stabilizedMarkdown: string;
    plainText: string;
    blocks: MessageBlock[];
    isStreaming: boolean;
}

interface BaseBlock {
    type: MessageBlock['type'];
    source: string;
}

export interface ParagraphBlock extends BaseBlock {
    type: 'paragraph';
    text: string;
}

export interface HeadingBlock extends BaseBlock {
    type: 'heading';
    level: 1 | 2 | 3 | 4 | 5 | 6;
    text: string;
}

export interface CodeBlock extends BaseBlock {
    type: 'codeBlock';
    language: string;
    code: string;
    fullCode?: string;
    originalCharCount?: number;
    isStreaming: boolean;
    isDiagramSource: boolean;
}

export interface BlockquoteBlock extends BaseBlock {
    type: 'blockquote';
    text: string;
}

export interface ListBlock extends BaseBlock {
    type: 'orderedList' | 'unorderedList';
    items: Array<{
        text: string;
        checked?: boolean;
        task: boolean;
    }>;
    originalItemCount?: number;
}

export interface TableBlock extends BaseBlock {
    type: 'table';
    headers: string[];
    rows: string[][];
    alignments: InlineAlignment[];
    markdown: string;
    plainText: string;
    csv: string;
    originalRowCount?: number;
    originalColumnCount?: number;
}

export interface HorizontalRuleBlock extends BaseBlock {
    type: 'horizontalRule';
}

export interface FootnoteBlock extends BaseBlock {
    type: 'footnoteDef';
    id: string;
    text: string;
}

export interface CitationBlock extends BaseBlock {
    type: 'citation';
    id: string;
    text: string;
}

export interface MathBlock extends BaseBlock {
    type: 'mathBlock';
    content: string;
    isStreaming: boolean;
}

export interface MessageRendererOptions {
    role: MessageRole;
    compact?: boolean;
    streaming?: boolean;
    allowImages?: boolean;
    enableMath?: boolean;
    showLineNumbers?: boolean;
}

export interface RenderedMessageActor {
    actor: St.BoxLayout;
    model: MessageModel;
    update(markdown: string, options?: Partial<MessageRendererOptions>): void;
    destroy(): void;
}

const COPY_FEEDBACK_TIMEOUT_MS = 1600;
const COMPACT_TABLE_CONTENT_WIDTH = 300;
const EXPANDED_TABLE_CONTENT_WIDTH = 610;
const MAX_LINK_ACTIONS = 4;
const MAX_CODE_CHARS = 30000;
const MAX_RENDER_ACTOR_UNITS = 1000;
const MAX_RENDERED_TABLE_COLUMNS = 12;
const MAX_RENDERED_TABLE_ROWS = 40;
const RENDER_NOTICE_ACTOR_UNITS = 10;
const MAX_PARSE_CACHE_ENTRIES = 100;
const MAX_CACHE_MARKDOWN_CHARS = 100000;
const MAX_PREVIEW_MARKDOWN_CHARS = 100000;
const MAX_THINKING_PREVIEW_CHARS = 50000;
const PREVIEW_OMISSION_TEXT = 'Additional content omitted from the popup preview for popup performance; copy the full response to view it.';
const SELECTION_COLOR = makeColor('#cfc4a6cc');
const SELECTED_TEXT_COLOR = makeColor('#171717ff');

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

function stabilizeMarkdown(markdown: string, streaming: boolean): { text: string; streaming: boolean } {
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

function parseMarkdownBlocks(markdown: string, options: MessageRendererOptions): MessageBlock[] {
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
            while (i < lines.length && /^\s*(?:[-*+]\s+|\d+[.)]\s+)/.test(lines[i])) {
                const itemText = lines[i].replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/, '');
                const task = itemText.match(/^\[([ xX])\]\s+(.+)$/);
                items.push({
                    text: task ? task[2] : itemText,
                    checked: task ? task[1].toLowerCase() === 'x' : undefined,
                    task: task !== null,
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

function fillMessageActor(actor: St.BoxLayout, model: MessageModel, options: MessageRendererOptions): void {
    for (const block of model.blocks) {
        actor.add_child(renderBlock(block, options));
    }

}

function renderBlock(block: MessageBlock, options: MessageRendererOptions): St.Widget {
    switch (block.type) {
        case 'heading':
            return makeMarkupLabel(inlineMarkup(block.text), `mei-md-heading mei-md-heading-${block.level}`);
        case 'paragraph':
            return renderParagraphBlock(block);
        case 'codeBlock':
            return renderCodeBlock(block, options);
        case 'blockquote':
            return renderCopyableTextBlock(block.text, block.source, 'mei-md-blockquote', 'Copy quote');
        case 'orderedList':
        case 'unorderedList':
            return renderListBlock(block);
        case 'table':
            return renderTableBlock(block, options);
        case 'horizontalRule':
            return new St.Widget({ style_class: 'mei-md-rule', x_expand: true });
        case 'footnoteDef':
            return renderCopyableTextBlock(`[^${block.id}]: ${block.text}`, block.source, 'mei-md-footnote', 'Copy footnote');
        case 'citation':
            return renderCopyableTextBlock(`[${block.id}] ${block.text}`, block.source, 'mei-md-citation', 'Copy citation');
        case 'mathBlock':
            return renderCopyableTextBlock(block.content, block.content, 'mei-md-math', 'Copy math');
    }
}

function renderParagraphBlock(block: ParagraphBlock): St.Widget {
    const links = extractLinks(block.text);
    if (links.length === 0) {
        return makeMarkupLabel(inlineMarkup(block.text), 'mei-md-paragraph');
    }

    const wrapper = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: 'mei-md-linkable-paragraph',
    });
    wrapper.add_child(makeMarkupLabel(inlineMarkup(block.text), 'mei-md-paragraph'));

    const actions = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-md-link-actions',
    });
    links.slice(0, MAX_LINK_ACTIONS).forEach((link, index) => {
        actions.add_child(makeOpenLinkButton(link, links.length > 1 ? index : null));
        actions.add_child(makeCopyButton(link.url, links.length > 1 ? `Copy link ${index + 1}` : 'Copy link'));
    });
    if (links.length > MAX_LINK_ACTIONS) {
        actions.add_child(makePlainLabel(`+${links.length - MAX_LINK_ACTIONS} more`, 'mei-md-link-overflow'));
    }
    wrapper.add_child(actions);
    return wrapper;
}

function renderCodeBlock(block: CodeBlock, options: MessageRendererOptions): St.Widget {
    const wrapper = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: block.isDiagramSource ? 'mei-md-code mei-md-diagram-source' : 'mei-md-code',
    });
    const header = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-md-code-header',
    });
    const language = block.isDiagramSource
        ? 'diagram source'
        : block.language || 'code';
    const copyText = block.fullCode ?? block.code;
    const truncated = typeof block.originalCharCount === 'number';
    header.add_child(new St.Label({
        text: block.isStreaming
            ? `${language} (generating)`
            : truncated
                ? `${language} (${block.originalCharCount} chars, preview)`
                : language,
        style_class: 'mei-md-code-language',
        x_expand: true,
    }));
    header.add_child(makeCopyButton(copyText, truncated ? 'Copy full code' : 'Copy code', 'Copy'));
    wrapper.add_child(header);

    const codeBox = new St.BoxLayout({
        style_class: 'mei-md-code-body',
        x_expand: true,
    });
    const label = makePlainLabel(formatCodeForDisplay(block.code, options), 'mei-md-code-text');
    codeBox.add_child(label);
    wrapper.add_child(codeBox);
    return wrapper;
}

function renderTableBlock(block: TableBlock, options: MessageRendererOptions): St.Widget {
    const wrapper = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: 'mei-md-table-wrapper',
    });
    const header = new St.BoxLayout({
        x_expand: true,
        style_class: 'mei-md-table-actions',
    });
    header.add_child(new St.Label({
        text: block.originalRowCount || block.originalColumnCount
            ? `table preview (${block.rows.length}/${block.originalRowCount ?? block.rows.length} rows, ${block.headers.length}/${block.originalColumnCount ?? block.headers.length} columns)`
            : 'table',
        style_class: 'mei-md-table-label',
        x_expand: true,
    }));
    header.add_child(makeCopyButton(block.markdown, 'Copy table as Markdown', 'MD'));
    header.add_child(makeCopyButton(block.plainText, 'Copy table as text', 'TXT'));
    header.add_child(makeCopyButton(block.csv, 'Copy table as CSV', 'CSV'));
    wrapper.add_child(header);

    const columnCount = Math.max(1, block.headers.length, ...block.rows.map(row => row.length));
    const cellWidth = getTableCellWidth(columnCount, options);
    const table = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: 'mei-md-table',
    });
    table.add_child(renderTableRow(block.headers, block.alignments, columnCount, cellWidth, true));
    for (const row of block.rows) {
        table.add_child(renderTableRow(row, block.alignments, columnCount, cellWidth, false));
    }
    wrapper.add_child(table);
    return wrapper;
}

function renderTableRow(
    cells: string[],
    alignments: InlineAlignment[],
    columnCount: number,
    cellWidth: number,
    header: boolean
): St.Widget {
    const row = new St.BoxLayout({
        x_expand: true,
        style_class: header ? 'mei-md-table-row mei-md-table-header' : 'mei-md-table-row',
    });
    for (let index = 0; index < columnCount; index++) {
        const alignment = alignments[index] ?? 'left';
        const label = makeMarkupLabel(inlineMarkup(cells[index] ?? ''), 'mei-md-table-cell');
        label.set_width(cellWidth);
        label.x_expand = false;
        label.x_align = Clutter.ActorAlign.FILL;
        label.clutter_text.set_line_alignment(toPangoAlignment(alignment));
        row.add_child(label);
    }
    return row;
}

function renderListBlock(block: ListBlock): St.Widget {
    const box = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: 'mei-md-list',
    });
    block.items.forEach((item, index) => {
        const prefix = item.task
            ? item.checked ? '[x]' : '[ ]'
            : block.type === 'orderedList' ? `${index + 1}.` : '•';
        const row = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-md-list-row',
        });
        row.add_child(new St.Label({
            text: prefix,
            style_class: 'mei-md-list-marker',
            y_align: Clutter.ActorAlign.START,
        }));
        row.add_child(makeMarkupLabel(inlineMarkup(item.text), 'mei-md-list-text'));
        box.add_child(row);
    });
    if (block.originalItemCount) {
        box.add_child(makePlainLabel(
            `${block.originalItemCount - block.items.length} more items omitted from the popup preview`,
            'mei-md-list-overflow'
        ));
    }
    return box;
}

function renderCopyableTextBlock(text: string, copyText: string, styleClass: string, copyLabel: string): St.Widget {
    const wrapper = new St.BoxLayout({
        vertical: true,
        x_expand: true,
        style_class: styleClass,
    });
    const top = new St.BoxLayout({
        x_expand: true,
    });
    top.add_child(makeMarkupLabel(inlineMarkup(text), 'mei-md-copyable-text'));
    top.add_child(makeCopyButton(copyText, copyLabel));
    wrapper.add_child(top);
    return wrapper;
}

function makeCopyButton(text: string, accessibleName: string, label?: string): St.Button {
    const styleClass = label ? 'mei-md-copy-chip' : 'mei-md-copy-icon';
    let feedbackTimeoutId = 0;
    const makeDefaultChild = (): St.Widget => label
        ? new St.Label({ text: label })
        : new St.Icon({ icon_name: 'edit-copy-symbolic', icon_size: 12 });
    const makeFeedbackChild = (): St.Widget => label
        ? new St.Label({ text: 'Copied' })
        : new St.Icon({ icon_name: 'object-select-symbolic', icon_size: 12 });
    const button = new St.Button({
        style_class: styleClass,
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: accessibleName,
        accessible_role: Atk.Role.PUSH_BUTTON,
        child: makeDefaultChild(),
    });
    button.connect('clicked', () => {
        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
        if (feedbackTimeoutId !== 0) {
            GLib.source_remove(feedbackTimeoutId);
            feedbackTimeoutId = 0;
        }
        button.style_class = `${styleClass} mei-md-copy-confirmed`;
        button.accessible_name = `${accessibleName} copied`;
        button.set_child(makeFeedbackChild());
        feedbackTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, COPY_FEEDBACK_TIMEOUT_MS, () => {
            feedbackTimeoutId = 0;
            button.style_class = styleClass;
            button.accessible_name = accessibleName;
            button.set_child(makeDefaultChild());
            return GLib.SOURCE_REMOVE;
        });
    });
    button.connect('destroy', () => {
        if (feedbackTimeoutId !== 0) {
            GLib.source_remove(feedbackTimeoutId);
            feedbackTimeoutId = 0;
        }
    });
    return button;
}

function makeOpenLinkButton(link: LinkTarget, index: number | null): St.Button {
    const label = index === null ? 'Open' : `Open ${index + 1}`;
    const button = new St.Button({
        label,
        style_class: 'mei-md-link-chip',
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: `Open link ${link.label}`,
        accessible_role: Atk.Role.LINK,
    });
    button.connect('clicked', () => openExternalLink(link.url));
    return button;
}

function makeMarkupLabel(markup: string, styleClass: string): St.Label {
    const label = new St.Label({
        style_class: styleClass,
        x_expand: true,
    });
    configureSelectableText(label);
    label.clutter_text.use_markup = true;
    try {
        label.clutter_text.set_markup(markup);
    } catch {
        label.clutter_text.use_markup = false;
        label.clutter_text.set_text(stripPangoTags(markup));
    }
    return label;
}

function makePlainLabel(text: string, styleClass: string): St.Label {
    const label = new St.Label({
        text,
        style_class: styleClass,
        x_expand: true,
    });
    return configureSelectableText(label);
}

function configureSelectableText(label: St.Label): St.Label {
    label.clutter_text.reactive = true;
    label.clutter_text.set_line_wrap(true);
    label.clutter_text.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);
    label.clutter_text.set_ellipsize(Pango.EllipsizeMode.NONE);
    label.clutter_text.set_editable(false);
    label.clutter_text.set_selectable(true);
    label.clutter_text.set_selection_color(SELECTION_COLOR);
    label.clutter_text.set_selected_text_color(SELECTED_TEXT_COLOR);
    label.clutter_text.connect('button-press-event', () => {
        label.clutter_text.grab_key_focus();
        return Clutter.EVENT_PROPAGATE;
    });
    label.clutter_text.connect('key-press-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
        if (!isCopyShortcut(event)) return Clutter.EVENT_PROPAGATE;

        const selection = getRealTextSelection(label.clutter_text);
        if (selection === null) return Clutter.EVENT_PROPAGATE;

        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, selection);
        return Clutter.EVENT_STOP;
    });
    return label;
}

function isCopyShortcut(event: Clutter.Event): boolean {
    const key = event.get_key_symbol();
    const state = event.get_state();
    return (key === Clutter.KEY_c || key === Clutter.KEY_C || key === Clutter.KEY_Copy) &&
        (state & Clutter.ModifierType.CONTROL_MASK) !== 0;
}

function getRealTextSelection(text: Clutter.Text): string | null {
    const cursorPosition = text.get_cursor_position();
    const selectionBound = text.get_selection_bound();
    if (selectionBound < 0 || cursorPosition === selectionBound) return null;

    const selection = text.get_selection();
    return selection.trim().length > 0 ? selection : null;
}

function makeColor(value: string): Cogl.Color | null {
    const [ok, color] = Cogl.Color.from_string(value);
    return ok ? color : null;
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

function sanitizeBlocks(blocks: MessageBlock[], options: MessageRendererOptions): MessageBlock[] {
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

function appendPreviewOmissionNotice(blocks: MessageBlock[], truncated: boolean): MessageBlock[] {
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

function blocksToPlainText(blocks: MessageBlock[]): string {
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

function inlineMarkup(text: string): string {
    return inlineTextMarkup(text, sanitizeUrl);
}

function extractLinks(text: string): LinkTarget[] {
    return extractTextLinks(text, sanitizeUrl);
}

function openExternalLink(url: string): void {
    const sanitized = sanitizeUrl(url);
    if (!sanitized) return;
    void Gio.app_info_launch_default_for_uri_async(sanitized, null, null).catch((error: unknown) => {
        console.warn(`[Mei] Failed to open link: ${error instanceof Error ? error.message : String(error)}`);
    });
}

function getTableCellWidth(columnCount: number, options: MessageRendererOptions): number {
    const availableWidth = options.compact ? COMPACT_TABLE_CONTENT_WIDTH : EXPANDED_TABLE_CONTENT_WIDTH;
    return Math.max(1, Math.floor(availableWidth / columnCount));
}

function toPangoAlignment(alignment: InlineAlignment): Pango.Alignment {
    if (alignment === 'right') return Pango.Alignment.RIGHT;
    if (alignment === 'center') return Pango.Alignment.CENTER;
    return Pango.Alignment.LEFT;
}

function sanitizeUrl(url: string): string | null {
    return sanitizeTextUrl(url, value => {
        try {
            GLib.Uri.parse(value, GLib.UriFlags.NONE);
            return true;
        } catch {
            return false;
        }
    });
}

function formatCodeForDisplay(code: string, options: MessageRendererOptions): string {
    if (!options.showLineNumbers) return code;
    return code.split('\n').map((line, index) => `${String(index + 1).padStart(4, ' ')}  ${line}`).join('\n');
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
