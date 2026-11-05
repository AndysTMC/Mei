/**
 * St actors for parsed blocks: selectable text (Ctrl+C copies the selection), code with a copy
 * button, tables with Markdown/text/CSV copy, and Open/Copy chips for links.
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

import { stripPangoTags } from '../messageText.js';
import { extractLinks, inlineMarkup, sanitizeUrl, type LinkTarget } from './links.js';
import type {
    CodeBlock, InlineAlignment, ListBlock, MessageBlock, MessageModel, MessageRendererOptions, ParagraphBlock, TableBlock,
} from './types.js';

const COPY_FEEDBACK_TIMEOUT_MS = 1600;
const COMPACT_TABLE_CONTENT_WIDTH = 300;
const EXPANDED_TABLE_CONTENT_WIDTH = 610;
const MAX_LINK_ACTIONS = 4;
const SELECTION_COLOR = makeColor('#cfc4a6cc');
const SELECTED_TEXT_COLOR = makeColor('#171717ff');

export function fillMessageActor(actor: St.BoxLayout, model: MessageModel, options: MessageRendererOptions): void {
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
            : item.number !== undefined ? `${item.number}.`
                : block.type === 'orderedList' && item.depth === undefined ? `${index + 1}.` : '•';
        const row = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-md-list-row',
        });
        if (item.depth) row.set_style(`margin-left: ${Math.min(item.depth, 4) * 22}px;`);
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

function formatCodeForDisplay(code: string, options: MessageRendererOptions): string {
    if (!options.showLineNumbers) return code;
    return code.split('\n').map((line, index) => `${String(index + 1).padStart(4, ' ')}  ${line}`).join('\n');
}
