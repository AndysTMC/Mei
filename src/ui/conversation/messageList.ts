/**
 * The scrolling list of messages. Compact mode shows the latest message (or a card waiting on the
 * person) alone; expanded mode shows the whole conversation, with the agent's cards in place, and
 * Copy, Read aloud, ↻ and an info panel under each reply. While Mei answers, a
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
import type { Attachment } from '../../runtime/protocol.js';
import { addClickScale, copyToClipboard, wrapLabel } from '../effects.js';
import { createMessageInfoPanel, styleMessageInfoPanel } from '../messageInfoPanel.js';
import { createMessageActor, formatThinkingPreview, type MessageRole, type RenderedMessageActor } from '../messageRenderer.js';
import type { SourceSet } from '../sources.js';
import { outcomeLine } from '../../runtime/timeline.js';
import type { ReplyDetails } from '../../runtime/timeline.js';
import { checksPanel, stepsPanel } from './cards.js';
import type { ListedItem } from './timelineView.js';

export interface ListedMessage {
    /** The message's id, where it has one (Read aloud follows it). */
    id?: string;
    role: string;
    content: string;
    thinking?: string;
    metadata?: ChatMessageMetadata;
    /** Plain text above the bubble, e.g. what "Ask about this" attached (never rendered as markdown). */
    note?: string;
    /** What the note names, when it can be opened on the large page. */
    attachment?: Attachment;
    /** A reply's steps and checks, behind its footer's icons. */
    details?: ReplyDetails;
    /** An interrupted reply, which Regenerate continues (the only reply it works for yet). */
    resumable?: boolean;
}

export interface MessageListHost {
    /** Run `change`, animating the popup's height to fit what it changed. */
    animateHeight(change: () => void): void;
    isDark(): boolean;
    onReload(index: number): void;
    /** Voice is set up: replies offer Read aloud. */
    canReadAloud(): boolean;
    /** Read a reply out, or stop reading it. */
    onReadAloud(messageId: string, text: string): void;
    /** The person clicked what a sent message carried. */
    onOpenAttachment(attachment: Attachment): void;
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
    /** In Live, the bar under the buttons says Mei is working: no spinner as well. */
    private _live = false;
    private _hasMessages = false;
    /** Each shown reply's Read aloud button, by message id; and the reply being read. */
    private readonly _readButtons = new Map<string, St.Button>();
    private _reading: string | null = null;
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

    setExpanded(expanded: boolean): void {
        this._expanded = expanded;
    }

    /** The conversation or its latest reply, each reply with its details, optionally fading in the last one. */
    showItems(items: ListedItem[], fadeLastAssistant = false): void {
        if (this._loading) this._removeBubble();
        this._box.destroy_all_children();
        this._readButtons.clear();
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

    /** The reply Read aloud is reading (its button shows Stop), or none. */
    setReading(messageId: string | null): void {
        const was = this._reading;
        this._reading = messageId;
        for (const id of [was, messageId]) {
            const button = id ? this._readButtons.get(id) : undefined;
            if (button) showReading(button, id === messageId);
        }
    }

    clear(): void {
        this._box.destroy_all_children();
        this._readButtons.clear();
        this.actor.visible = false;
        this._hasMessages = false;
    }

    /** Live on or off: while on, the loading spinner stays hidden (the Live bar shows Mei working). */
    setLive(live: boolean): void {
        if (this._live === live) return;
        this._live = live;
        if (this._loading) this._attachBubble();
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
        if (message.note) container.add_child(this._note(message.note, message.attachment, role));
        container.add_child(this._messageActor(role, message.content).actor);
        const cut = role === 'assistant' ? message.metadata?.cut : undefined;
        if (cut) container.add_child(new St.Label({ text: CUT_NOTE[cut], style_class: 'mei-msg-note' }));
        const details = role === 'assistant' ? message.details : undefined;
        const panels: FooterPanel[] = [];
        if (details && (details.steps.length || details.notes.length))
            panels.push({ icon: 'view-list-bullet-symbolic', label: 'Steps', panel: stepsPanel(details) });
        if (details?.outcome)
            panels.push({ icon: CHECKS_ICON[outcomeLine(details.outcome).tone], label: 'Checks', panel: checksPanel(details.outcome) });
        if (role === 'assistant' && this._expanded) // the small popup keeps to the answer
            panels.push({ icon: 'dialog-information-symbolic', label: 'Info', panel: createMessageInfoPanel(message.metadata, this._host.isDark()) });
        container.add_child(this._footer(role, message.content, index, panels, Boolean(message.resumable), message.id));
        for (const { panel } of panels) {
            panel.visible = false;
            container.add_child(panel);
        }
        return container;
    }

    /** What a message carried, above it; a button to the large page when it can be opened. */
    private _note(text: string, attachment: Attachment | undefined, role: MessageRole): St.Widget {
        const x_align = role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START;
        if (!attachment) return new St.Label({ text, style_class: 'mei-msg-note', x_align });
        const button = new St.Button({ label: text, style_class: 'mei-msg-note mei-msg-note-link', x_align, can_focus: true,
            reactive: true, track_hover: true, accessible_name: `Open ${text}`, accessible_role: Atk.Role.LINK });
        button.connect('clicked', () => this._host.onOpenAttachment(attachment));
        return button;
    }

    /** Under a message: Copy; under a reply Steps, Checks and Info, each opening its panel below (one
     * at a time), and Regenerate where it works. Labels show on hover or focus. */
    private _footer(role: MessageRole, text: string, index: number, panels: FooterPanel[], resumable: boolean,
        messageId?: string): St.BoxLayout {
        const bar = new St.BoxLayout({
            style_class: role === 'user' ? 'mei-action-bar' : 'mei-action-bar reply',
            x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
        });
        const copy = footerButton('edit-copy-symbolic', 'Copy');
        copy.connect('clicked', () => {
            copyToClipboard(text);
            const icon = footerIcon(copy);
            icon.icon_name = 'object-select-symbolic';
            this._sources.timeout(COPIED_FOR_MS, () => {
                icon.icon_name = 'edit-copy-symbolic';
                return GLib.SOURCE_REMOVE;
            });
        });
        bar.add_child(copy);
        if (role !== 'assistant') return bar;

        if (messageId && this._host.canReadAloud()) {
            const read = footerButton(READ_ICON, 'Read aloud');
            read.connect('clicked', () => this._host.onReadAloud(messageId, text));
            this._readButtons.set(messageId, read);
            if (this._reading === messageId) showReading(read, true);
            bar.add_child(read);
        }

        if (resumable) {
            const reload = footerButton('view-refresh-symbolic', 'Regenerate');
            reload.connect('clicked', () => this._host.onReload(index));
            bar.add_child(reload);
        }
        const toggles = panels.map(({ icon, label, panel }) => {
            const button = footerButton(icon, label);
            button.connect('clicked', () => this._openPanel(panel, button, toggles));
            bar.add_child(button);
            return { button, panel };
        });
        return bar;
    }

    /** Open this panel (closing the reply's others), or close it if open. */
    private _openPanel(panel: St.Widget, button: St.Button, group: { button: St.Button; panel: St.Widget }[]): void {
        const show = !panel.visible;
        this._host.animateHeight(() => {
            for (const other of group) {
                const on = show && other.panel === panel;
                if (on) other.button.add_style_class_name('selected');
                else other.button.remove_style_class_name('selected');
                other.panel.remove_all_transitions();
                other.panel.visible = on;
                showLabel(other.button, on || other.button.hover);
            }
            if (show) {
                panel.opacity = 0;
                panel.ease({ opacity: 255, duration: 120, mode: Clutter.AnimationMode.EASE_IN_QUAD });
            }
        });
        button.accessible_name = `${show ? 'Hide' : 'Show'} ${footerLabel(button).text.toLowerCase()}`;
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
            this._bubble = new St.BoxLayout({ style_class: 'mei-bubble-ai', x_align: Clutter.ActorAlign.START, x_expand: false,
                visible: !this._live }); // only a spinner: nothing to show in Live
            this._bubble.add_child(this._spinner);
            this._spinner.x_expand = this._spinner.y_expand = true;
        }
        if (this._live) {
            this._spinner.stop();
            this._spinner.visible = false;
        } else {
            this._spinner.play();
            this._spinner.visible = true;
        }
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

interface FooterPanel {
    icon: string;
    label: string;
    panel: St.Widget;
}

const CHECKS_ICON: Record<string, string> = {
    checked: 'checkbox-checked-symbolic', unchecked: 'checkbox-symbolic', problem: 'dialog-warning-symbolic',
};

/** An icon whose label slides out beside it on hover or keyboard focus. */
function footerButton(iconName: string, label: string): St.Button {
    const box = new St.BoxLayout({ y_align: Clutter.ActorAlign.CENTER });
    box.add_child(new St.Icon({ icon_name: iconName, icon_size: 12, y_align: Clutter.ActorAlign.CENTER }));
    box.add_child(new St.Label({ text: label, visible: false, style_class: 'mei-action-label', y_align: Clutter.ActorAlign.CENTER }));
    const button = new St.Button({
        style_class: 'mei-action-btn', can_focus: true, reactive: true, track_hover: true, child: box,
        accessible_name: label, accessible_role: Atk.Role.PUSH_BUTTON,
    });
    const sync = () => showLabel(button, button.hover || button.has_key_focus() || button.has_style_class_name('selected'));
    button.connect('notify::hover', sync);
    button.connect('key-focus-in', sync);
    button.connect('key-focus-out', sync);
    addClickScale(button);
    return button;
}

/** Under a reply the model stopped early: it isn't the whole answer. */
const CUT_NOTE = {
    length: 'Cut short: the model reached its length limit.',
    filtered: 'Stopped by the model’s safety filter.',
};

const READ_ICON = 'audio-speakers-symbolic';
const STOP_READING_ICON = 'media-playback-stop-symbolic';

/** Read aloud's button: Stop while its reply is being read. */
function showReading(button: St.Button, reading: boolean): void {
    const name = reading ? 'Stop reading' : 'Read aloud';
    footerIcon(button).icon_name = reading ? STOP_READING_ICON : READ_ICON;
    footerLabel(button).text = name;
    button.accessible_name = name;
}

function footerIcon(button: St.Button): St.Icon {
    return (button.child as St.BoxLayout).get_child_at_index(0) as St.Icon;
}

function footerLabel(button: St.Button): St.Label {
    return (button.child as St.BoxLayout).get_child_at_index(1) as St.Label;
}

function showLabel(button: St.Button, show: boolean): void {
    const label = footerLabel(button);
    if (label.visible === show) return;
    label.remove_all_transitions();
    label.visible = show;
    if (show) {
        label.opacity = 0;
        label.ease({ opacity: 255, duration: 120, mode: Clutter.AnimationMode.EASE_OUT_QUAD });
    }
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
