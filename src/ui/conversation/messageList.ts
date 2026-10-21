/**
 * The scrolling list of messages. Compact mode shows the latest message (or a card waiting on the
 * person) alone; expanded mode shows the whole conversation, with the agent's cards in place, and
 * Copy, ↻ and an info panel under each reply. While Mei answers, a
 * loading bubble sits at the end: a spinner in compact mode; in expanded mode the streamed answer,
 * with any thinking shown above it and folded away once the answer starts.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Animation from 'resource:///org/gnome/shell/ui/animation.js';

import type { ChatMessageMetadata } from '../../providers/types.js';
import { addClickScale, copyToClipboard, wrapLabel } from '../effects.js';
import { createMessageInfoPanel, styleMessageInfoPanel } from '../messageInfoPanel.js';
import { createMessageActor, formatThinkingPreview, type MessageRole, type RenderedMessageActor } from '../messageRenderer.js';
import type { SourceSet } from '../sources.js';
import type { ListedItem } from './timelineView.js';

export interface ListedMessage {
    role: string;
    content: string;
    thinking?: string;
    metadata?: ChatMessageMetadata;
    /** Plain text above the bubble, e.g. what "Ask about this" attached (never rendered as markdown). */
    note?: string;
}

export interface MessageListHost {
    /** Run `change`, animating the popup's height to fit what it changed. */
    animateHeight(change: () => void): void;
    isDark(): boolean;
    onReload(index: number): void;
}

const STREAM_RENDER_MS = 50;
const SCROLL_SETTLE_MS = 33;
const COPIED_FOR_MS = 1500;
const NEAR_BOTTOM_PX = 20;

/** The expanded loading bubble's parts, updated as the reply streams in. */
interface StreamingBubble {
    header: St.BoxLayout;
    title: St.Label;
    toggle: St.Button;
    details: St.Label;
    answerBox: St.BoxLayout;
    answer?: RenderedMessageActor;
}

export class MessageList {
    readonly actor: St.ScrollView;
    private readonly _box = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-message-box' });
    private readonly _spinner: Animation.Spinner;
    private _expanded = false;
    private _loading = false;
    private _hasMessages = false;
    private _lastReply = '';
    private _bubble?: St.BoxLayout;
    private _streaming?: StreamingBubble;
    private _thinkingOpen = true;
    private _thinkingAutoClosed = false;
    private _pending = { content: '', thinking: '' };
    private _renderId = 0;
    private _scrollId = 0;
    private _scrollTarget: 'top' | 'bottom' = 'bottom';

    constructor(private readonly _sources: SourceSet, maxHeight: number, private readonly _host: MessageListHost) {
        this.actor = new St.ScrollView({ style_class: 'mei-scroll', x_expand: true, visible: false, overlay_scrollbars: true });
        this.actor.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this.actor.set_style(`max-height: ${maxHeight}px;`);
        this.actor.set_child(this._box);
        this._spinner = new Animation.Spinner(16, { animate: false, hideOnStop: true });
        this._spinner.x_align = this._spinner.y_align = Clutter.ActorAlign.CENTER;
        this._spinner.visible = false;
    }

    get hasMessages(): boolean {
        return this._hasMessages;
    }

    /** The latest reply shown in compact mode (for the header's Copy), or ''. */
    get lastReply(): string {
        return this._lastReply;
    }

    setExpanded(expanded: boolean): void {
        this._expanded = expanded;
    }

    /** Compact mode: the latest message alone. */
    showMessage(role: 'user' | 'assistant', text: string): void {
        this._box.destroy_all_children();
        this._lastReply = role === 'assistant' ? text : '';
        this._hasMessages = text.length > 0;
        this.actor.visible = this._hasMessages;
        if (!text) return;
        this._box.add_child(this._messageActor(role, text).actor);
        this._queueScroll('top');
    }

    /** Compact mode: a card that waits on the person (an approval or a question), alone. */
    showCard(build: () => St.Widget): void {
        if (this._loading) this._removeBubble();
        this._box.destroy_all_children();
        this._lastReply = '';
        this._box.add_child(build());
        this._hasMessages = true;
        this.actor.visible = true;
        this._queueScroll('top');
    }

    /** Expanded mode: the whole conversation with its cards, optionally fading in the last reply. */
    showItems(items: ListedItem[], fadeLastAssistant = false): void {
        if (this._loading) this._removeBubble();
        this._box.destroy_all_children();
        this._lastReply = '';
        items.forEach((item, position) => {
            if (item.kind === 'card') {
                this._box.add_child(item.build());
                return;
            }
            const { message, index } = item;
            if (!isRenderableRole(message.role)) return;
            const fade = fadeLastAssistant && message.role === 'assistant' && position === items.length - 1;
            const container = this._listedMessage(message, index);
            if (fade) container.opacity = 0;
            this._box.add_child(container);
            if (fade) {
                this._sources.idle(() => {
                    if (container.get_parent())
                        container.ease({ opacity: 255, duration: 320, mode: Clutter.AnimationMode.EASE_IN_OUT_QUAD });
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        if (this._loading) this._attachBubble();
        this._hasMessages = items.length > 0 || this._loading;
        this.actor.visible = this._hasMessages;
        this._queueScroll('bottom');
    }

    clear(): void {
        this._box.destroy_all_children();
        this.actor.visible = false;
        this._hasMessages = false;
        this._lastReply = '';
    }

    setLoading(loading: boolean): void {
        if (this._loading === loading) return;
        this._loading = loading;
        if (loading) {
            this._thinkingOpen = true;
            this._thinkingAutoClosed = false;
            this._attachBubble();
            this._sources.idle(() => {
                const adj = this.actor.get_vadjustment();
                adj.value = adj.upper - adj.page_size;
                return GLib.SOURCE_REMOVE;
            }, GLib.PRIORITY_DEFAULT);
        } else {
            this._spinner.stop();
            this._spinner.visible = false;
            this._removeBubble();
            this._thinkingAutoClosed = false;
        }
    }

    /** The reply so far. Renders at most every STREAM_RENDER_MS. */
    showStreaming(content: string, thinking: string): void {
        this._pending = { content, thinking };
        if (this._renderId) return;
        this._renderId = this._sources.timeout(STREAM_RENDER_MS, () => {
            this._renderId = 0;
            this._renderStreaming(this._pending.content, this._pending.thinking);
            return GLib.SOURCE_REMOVE;
        });
    }

    applyTheme(): void {
        const isDark = this._host.isDark();
        const visit = (actor: Clutter.Actor): void => {
            if (actor instanceof St.Widget && actor.has_style_class_name('mei-message-info-panel'))
                styleMessageInfoPanel(actor, isDark);
            actor.get_children().forEach(visit);
        };
        visit(this._box);
    }

    destroy(): void {
        this.setLoading(false);
        this._spinner.destroy();
    }

    // ── Messages ─────────────────────────────────────────────────────────────

    private _messageActor(role: MessageRole, text: string): RenderedMessageActor {
        const rendered = createMessageActor(text, { role, compact: !this._expanded });
        rendered.actor.x_align = role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START;
        rendered.actor.x_expand = role === 'assistant';
        return rendered;
    }

    private _listedMessage(message: ListedMessage, index: number): St.BoxLayout {
        const role = message.role as MessageRole;
        const container = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-msg-container' });
        if (role === 'assistant' && this._expanded && message.thinking)
            container.add_child(thinkingBlock(message.thinking));
        if (message.note) {
            container.add_child(new St.Label({ text: message.note, style_class: 'mei-msg-note',
                x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START }));
        }
        container.add_child(this._messageActor(role, message.content).actor);
        const info = role === 'assistant' ? createMessageInfoPanel(message.metadata, this._host.isDark()) : null;
        container.add_child(this._actionBar(role, message.content, index, info));
        if (info) container.add_child(info);
        return container;
    }

    /** Copy for every message; ↻ and the info toggle for replies. */
    private _actionBar(role: MessageRole, text: string, index: number, info: St.BoxLayout | null): St.BoxLayout {
        const bar = new St.BoxLayout({
            style_class: 'mei-action-bar',
            x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
        });
        const copyIcon = actionIcon('edit-copy-symbolic');
        const copy = actionButton(copyIcon, `Copy ${role === 'user' ? 'message' : 'response'}`);
        copy.connect('clicked', () => {
            copyToClipboard(text);
            copyIcon.icon_name = 'object-select-symbolic';
            this._sources.timeout(COPIED_FOR_MS, () => {
                copyIcon.icon_name = 'edit-copy-symbolic';
                return GLib.SOURCE_REMOVE;
            });
        });
        bar.add_child(copy);
        if (role !== 'assistant') return bar;

        const reload = actionButton(actionIcon('view-refresh-symbolic'), 'Regenerate response');
        reload.connect('clicked', () => this._host.onReload(index));
        bar.add_child(reload);
        const infoGlyph = new St.Label({ text: 'i', style_class: 'mei-info-glyph', x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER });
        const infoToggle = actionButton(infoGlyph, 'Show response information', 'mei-info-btn');
        infoToggle.connect('clicked', () => {
            if (info) this._toggleInfo(info, infoToggle);
        });
        bar.add_child(infoToggle);
        return bar;
    }

    private _toggleInfo(panel: St.BoxLayout, button: St.Button): void {
        const show = !panel.visible;
        button.accessible_name = show ? 'Hide response information' : 'Show response information';
        if (show) button.add_style_class_name('selected');
        else button.remove_style_class_name('selected');
        this._host.animateHeight(() => {
            panel.remove_all_transitions();
            panel.opacity = show ? 0 : 255;
            panel.visible = show;
            if (show) panel.ease({ opacity: 255, duration: 120, mode: Clutter.AnimationMode.EASE_IN_QUAD });
        });
    }

    private _queueScroll(target: 'top' | 'bottom'): void {
        this._scrollTarget = target;
        if (this._scrollId) return;
        this._scrollId = this._sources.timeout(SCROLL_SETTLE_MS, () => {
            this._scrollId = 0;
            const adj = this.actor.get_vadjustment();
            adj.set_value(this._scrollTarget === 'top'
                ? adj.get_lower()
                : Math.max(adj.get_lower(), adj.get_upper() - adj.get_page_size()));
            return GLib.SOURCE_REMOVE;
        });
    }

    // ── The loading bubble ───────────────────────────────────────────────────

    private _attachBubble(): void {
        this._removeBubble();
        if (this._expanded) {
            this._streaming = this._streamingBubble();
            this._bubble = new St.BoxLayout({ vertical: true, style_class: 'mei-streaming-bubble', x_expand: true });
            for (const part of [this._streaming.header, this._streaming.details, this._streaming.answerBox])
                this._bubble.add_child(part);
            this._spinner.x_expand = this._spinner.y_expand = false;
        } else {
            this._bubble = new St.BoxLayout({ style_class: 'mei-bubble-ai', x_align: Clutter.ActorAlign.START, x_expand: false });
            this._bubble.add_child(this._spinner);
            this._spinner.x_expand = this._spinner.y_expand = true;
        }
        this._spinner.play();
        this._spinner.visible = true;
        this._box.add_child(this._bubble);
        this.actor.visible = true;
        this._hasMessages = true;
    }

    private _streamingBubble(): StreamingBubble {
        const header = new St.BoxLayout({ style_class: 'mei-thinking-header', x_expand: false, x_align: Clutter.ActorAlign.START });
        header.add_child(this._spinner);
        const title = new St.Label({ text: 'Thinking', visible: false, style_class: 'mei-thinking-title',
            y_align: Clutter.ActorAlign.CENTER });
        header.add_child(title);
        const toggle = thinkingToggle(this._thinkingOpen);
        toggle.visible = false;
        const details = wrapLabel(new St.Label({ text: '', visible: false, x_expand: true, style_class: 'mei-thinking-details' }));
        toggle.connect('clicked', () => {
            this._thinkingOpen = !this._thinkingOpen;
            details.visible = this._thinkingOpen;
            toggle.set_label(this._thinkingOpen ? '⌃' : '⌄');
        });
        header.add_child(toggle);
        const answerBox = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-streaming-answer' });
        return { header, title, toggle, details, answerBox };
    }

    private _removeBubble(): void {
        this._renderId = this._sources.remove(this._renderId);
        this._pending = { content: '', thinking: '' };
        this._spinner.get_parent()?.remove_child(this._spinner);
        // Release the streamed answer first: it lives inside the bubble, and destroying the bubble
        // first leaves it disposed, so destroying it afterwards touches a dead object (Gjs-CRITICAL).
        this._streaming?.answer?.destroy();
        this._streaming = undefined;
        this._bubble?.destroy();
        this._bubble = undefined;
    }

    private _renderStreaming(content: string, thinking: string): void {
        const parts = this._streaming;
        if (!this._expanded || !parts) return;
        const adj = this.actor.get_vadjustment();
        const scrolled = adj.get_value();
        const wasNearBottom = scrolled >= adj.get_upper() - adj.get_page_size() - NEAR_BOTTOM_PX;
        const hasThinking = thinking.trim().length > 0;
        const hasContent = content.trim().length > 0;
        if (hasThinking && hasContent && !this._thinkingAutoClosed) {
            this._thinkingOpen = false; // fold the thinking away once, when the answer starts
            this._thinkingAutoClosed = true;
        }
        parts.header.visible = hasThinking || !hasContent;
        parts.title.visible = hasThinking;
        parts.details.set_text(hasThinking ? formatThinkingPreview(thinking.trim()) : '');
        parts.details.visible = hasThinking && this._thinkingOpen;
        parts.toggle.visible = hasThinking;
        parts.toggle.set_label(this._thinkingOpen ? '⌃' : '⌄');

        if (hasContent && !parts.answer) {
            parts.answer = createMessageActor(content, { role: 'assistant', compact: false, streaming: true });
            parts.answer.actor.x_expand = true;
            parts.answerBox.add_child(parts.answer.actor);
        } else if (hasContent) {
            parts.answer?.update(content, { streaming: true });
        } else if (parts.answer) {
            parts.answer.destroy();
            parts.answer = undefined;
        }

        this._sources.idle(() => {
            // Follow the end if the reader was there; otherwise keep their place.
            const bottom = Math.max(adj.get_lower(), adj.get_upper() - adj.get_page_size());
            adj.set_value(wasNearBottom ? bottom : Math.max(adj.get_lower(), Math.min(scrolled, bottom)));
            return GLib.SOURCE_REMOVE;
        }, GLib.PRIORITY_DEFAULT);
    }
}

function isRenderableRole(role: string): role is MessageRole {
    return role === 'user' || role === 'assistant';
}

function actionIcon(iconName: string): St.Icon {
    return new St.Icon({ icon_name: iconName, icon_size: 12, x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
}

function actionButton(child: St.Widget, accessibleName: string, extraClass = ''): St.Button {
    const button = new St.Button({
        style_class: `mei-action-btn${extraClass ? ` ${extraClass}` : ''}`,
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: accessibleName,
        accessible_role: Atk.Role.PUSH_BUTTON,
        child,
    });
    addClickScale(button);
    return button;
}

function thinkingToggle(open: boolean): St.Button {
    return new St.Button({
        label: open ? '⌃' : '⌄',
        style_class: 'mei-thinking-toggle',
        can_focus: true,
        reactive: true,
        track_hover: true,
        accessible_name: 'Toggle thinking details',
        accessible_role: Atk.Role.PUSH_BUTTON,
    });
}

/** A finished reply's thinking, folded under a "Thinking" header. */
function thinkingBlock(thinking: string): St.BoxLayout {
    const box = new St.BoxLayout({ vertical: true, x_expand: true, style_class: 'mei-thinking-block' });
    const header = new St.BoxLayout({ x_expand: false, x_align: Clutter.ActorAlign.START, style_class: 'mei-thinking-header' });
    header.add_child(new St.Label({ text: 'Thinking', style_class: 'mei-thinking-block-title', y_align: Clutter.ActorAlign.CENTER }));
    const body = wrapLabel(new St.Label({ text: formatThinkingPreview(thinking), visible: false, x_expand: true,
        style_class: 'mei-thinking-details' }));
    const toggle = thinkingToggle(false);
    toggle.connect('clicked', () => {
        body.visible = !body.visible;
        toggle.set_label(body.visible ? '⌃' : '⌄');
    });
    header.add_child(toggle);
    box.add_child(header);
    box.add_child(body);
    return box;
}
