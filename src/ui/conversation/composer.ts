/**
 * The message box with Ask, the mic, and voice. The input grows with its text up to a maximum
 * height, then scrolls, keeping the cursor in view. Enter sends; Shift+Enter adds a line. While Mei
 * works, a message sent joins the task in progress (the runtime steers it, §8.1), and in compact
 * mode the Ask button becomes Stop.
 *
 * The mic dictates: what's said goes into the box, to edit and send (Ask and voice hide meanwhile).
 * Voice is a conversation: talk, and Mei answers out loud; while it's on, the box shows what voice
 * is doing and what it heard, and only the voice button (now Stop) remains.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import type Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { addClickScale, wrapLabel } from '../effects.js';
import type { SourceSet } from '../sources.js';

export type InputScrollTarget = 'none' | 'top' | 'cursor' | 'bottom';

/** When several layout passes are queued, the strongest scroll request wins. */
const SCROLL_PRIORITY: Record<InputScrollTarget, number> = { none: 0, top: 1, cursor: 2, bottom: 3 };
const MIN_HEIGHT = 22;
const BLINK_MS = 500;
const CURSOR_MARGIN = 2;

export interface ComposerActions {
    onSend(text: string): void;
    onStop(): void;
    /** The mic: dictate into the box; again: done. */
    onDictate(): void;
    /** Voice: talk with Mei; again: stop. */
    onVoice(): void;
}

/** What the voice controls show: hidden (voice off), idle, dictating, or a conversation. */
export interface ComposerVoice {
    available: boolean;
    mode: 'idle' | 'dictating' | 'talking';
    /** While talking: what voice is doing ("Listening…") and what it heard. */
    status: string;
    transcript: string;
}

export class Composer {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true });
    readonly entry: St.Entry;
    readonly askButton: St.Button;
    readonly micButton: St.Button;
    readonly voiceButton: St.Button;
    private readonly _scroll: St.ScrollView;
    private readonly _voiceLine = new St.BoxLayout({ vertical: true, x_expand: true, visible: false, style_class: 'mei-voice-line' });
    private readonly _voiceStatus = new St.Label({ style_class: 'mei-voice-status' });
    private readonly _voiceHeard = wrapLabel(new St.Label({ style_class: 'mei-voice-heard', x_expand: true }));
    private _voiceMode: ComposerVoice['mode'] = 'idle';
    /** What was typed before dictation began; dictated words follow it. */
    private _dictationBase: string | null = null;
    private _loading = false;
    private _expanded = false;
    private _layoutId = 0;
    private _scrollId = 0;
    private _blinkId = 0;
    private _scrollAfterLayout: InputScrollTarget = 'none';
    private _scrollAfterIdle: InputScrollTarget = 'none';

    constructor(private readonly _sources: SourceSet, private readonly _maxHeight: number,
        private readonly _actions: ComposerActions, voiceIcon: Gio.Icon) {
        this.entry = new St.Entry({
            hint_text: 'Ask Mei anything…',
            can_focus: true,
            x_expand: true,
            style_class: 'mei-input',
            accessible_name: 'Message input',
        });
        this._configureText(this.entry.clutter_text);

        const inputBox = new St.BoxLayout({ vertical: true, x_expand: true });
        inputBox.add_child(this.entry);
        this._scroll = new St.ScrollView({ style_class: 'mei-input-scroll', x_expand: true, overlay_scrollbars: true });
        this._scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this._scroll.set_style(`max-height: ${_maxHeight}px;`);
        this._scroll.set_child(inputBox);
        this.actor.add_child(this._scroll);
        this._voiceLine.add_child(this._voiceStatus);
        this._voiceLine.add_child(this._voiceHeard);
        this.actor.add_child(this._voiceLine);

        this.askButton = new St.Button({
            label: 'Ask',
            style_class: 'mei-ask-btn',
            can_focus: true,
            x_expand: true,
            reactive: true,
            track_hover: true,
            accessible_name: 'Send message',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        this.askButton.connect('clicked', () => (this._loading && !this._expanded ? this._actions.onStop() : this._send()));
        addClickScale(this.askButton);
        this.micButton = voiceControl(new St.Icon({ icon_name: 'audio-input-microphone-symbolic', icon_size: 14 }), 'Dictate');
        this.micButton.connect('clicked', () => {
            if (this._voiceMode !== 'dictating') this._dictationBase = null;
            this._actions.onDictate();
        });
        this.voiceButton = voiceControl(new St.Icon({ gicon: voiceIcon, icon_size: 14 }), 'Talk with Mei');
        this.voiceButton.connect('clicked', () => this._actions.onVoice());
        const buttons = new St.BoxLayout({ x_expand: true, style_class: 'mei-composer-buttons' });
        buttons.add_child(this.askButton);
        buttons.add_child(this.micButton);
        buttons.add_child(this.voiceButton);
        this.actor.add_child(buttons);
        this.queueLayout();
    }

    focus(): void {
        this.entry.grab_key_focus();
        this.queueLayout('cursor');
    }

    /** Ask, or Stop while Mei works in compact mode (where there's no other way to stop). */
    setState(loading: boolean, expanded: boolean): void {
        this._loading = loading;
        this._expanded = expanded;
        const button = this.askButton;
        if (loading && !expanded) {
            button.set_label('Stop');
            button.accessible_name = 'Stop response';
            button.add_style_class_name('loading');
            button.reactive = true;
            return;
        }
        button.remove_style_class_name('loading');
        button.set_label('Ask');
        button.accessible_name = loading ? 'Send to the task in progress' : 'Send message';
        button.reactive = true;
        // Clutter can leave the click scale and hover stuck when the label changes mid-click.
        button.scale_x = button.scale_y = 1.0;
        button.sync_hover();
        this.entry.hint_text = loading ? 'Add to what Mei is doing…' : 'Ask Mei anything…';
    }

    /** Mic and voice show when voice is on; while one is in use, it takes the row. */
    setVoice(v: ComposerVoice): void {
        const dictating = v.mode === 'dictating';
        const talking = v.mode === 'talking';
        if (this._voiceMode === 'dictating' && !dictating) this._dictationBase = null;
        this._voiceMode = v.mode;
        this.askButton.visible = !dictating && !talking;
        this.micButton.visible = v.available && !talking;
        this.voiceButton.visible = v.available && !dictating;
        setActive(this.micButton, dictating, dictating ? 'Done dictating' : 'Dictate');
        setActive(this.voiceButton, talking, talking ? 'Stop talking with Mei' : 'Talk with Mei');
        this._scroll.visible = !talking;
        this._voiceLine.visible = talking;
        this._voiceStatus.text = v.status;
        this._voiceHeard.text = v.transcript;
        this._voiceHeard.visible = Boolean(v.transcript);
        if (!talking) this.queueLayout();
    }

    /** Dictated words so far (or final): after what was already typed, the cursor at the end. */
    dictate(text: string): void {
        if (this._dictationBase === null) {
            const typed = this.entry.get_text().trimEnd();
            this._dictationBase = typed ? `${typed} ` : '';
        }
        this.entry.set_text(this._dictationBase + text);
        this.entry.clutter_text.set_cursor_position(-1);
        this.queueLayout('cursor');
    }

    stopBlink(): void {
        this._blinkId = this._sources.remove(this._blinkId);
        this.entry.clutter_text.cursor_visible = false;
    }

    /** Re-measure the input after its text or width changed, then scroll as asked. */
    queueLayout(target: InputScrollTarget = 'none'): void {
        if (SCROLL_PRIORITY[target] > SCROLL_PRIORITY[this._scrollAfterLayout]) this._scrollAfterLayout = target;
        if (this._layoutId) return;
        this._layoutId = this._sources.idle(() => {
            this._layoutId = 0;
            const scrollTarget = this._scrollAfterLayout;
            this._scrollAfterLayout = 'none';
            this._layout(scrollTarget);
            return GLib.SOURCE_REMOVE;
        });
    }

    private _configureText(text: Clutter.Text): void {
        text.set_single_line_mode(false);
        text.set_line_wrap(true);
        text.set_line_wrap_mode(Pango.WrapMode.WORD);
        text.cursor_visible = true;
        text.x_expand = text.y_expand = true;
        text.x_align = text.y_align = Clutter.ActorAlign.FILL;
        text.connect('key-focus-in', () => this._startBlink());
        text.connect('key-focus-out', () => this.stopBlink());
        text.connect('text-changed', () => {
            this._startBlink(); // typing restarts the blink with the cursor shown
            this.queueLayout('cursor');
        });
        text.connect('cursor-changed', () => this.queueLayout('cursor'));
        text.connect('key-press-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
            const key = event.get_key_symbol();
            const shift = (event.get_state() & Clutter.ModifierType.SHIFT_MASK) !== 0;
            if ((key === Clutter.KEY_Return || key === Clutter.KEY_KP_Enter) && !shift) {
                this._sources.idle(() => {
                    this._send();
                    return GLib.SOURCE_REMOVE;
                });
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        // A click in the entry's padding (right of a short line) should still place the cursor.
        this.entry.connect('button-press-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
            const [x, y] = event.get_coords();
            const [ok, localX, localY] = text.transform_stage_point(x, y);
            if (ok) {
                text.grab_key_focus();
                text.set_cursor_position(text.coords_to_position(localX, localY));
            }
            return Clutter.EVENT_PROPAGATE;
        });
    }

    private _send(): void {
        const text = this.entry.get_text().trim();
        if (!text) return;
        this.entry.set_text('');
        this.queueLayout('top');
        this._actions.onSend(text);
    }

    private _startBlink(): void {
        this._sources.remove(this._blinkId);
        const text = this.entry.clutter_text;
        text.cursor_visible = true;
        this._blinkId = this._sources.timeout(BLINK_MS, () => {
            text.cursor_visible = !text.cursor_visible;
            return GLib.SOURCE_CONTINUE;
        });
    }

    private _layout(scrollTarget: InputScrollTarget): void {
        const width = Math.max(1, Math.floor(this.entry.get_width()));
        const [, natural] = this.entry.clutter_text.get_preferred_height(width);
        const contentHeight = Math.max(MIN_HEIGHT, Math.ceil(natural));
        this.entry.set_height(contentHeight);
        this._scroll.set_height(Math.min(contentHeight, this._maxHeight));
        if (scrollTarget === 'top') this._scroll.get_vadjustment().set_value(0);
        else if (scrollTarget !== 'none') this._queueScroll(scrollTarget);
    }

    private _queueScroll(target: 'cursor' | 'bottom'): void {
        if (SCROLL_PRIORITY[target] > SCROLL_PRIORITY[this._scrollAfterIdle]) this._scrollAfterIdle = target;
        if (this._scrollId) return;
        this._scrollId = this._sources.idle(() => {
            this._scrollId = 0;
            const scrollTarget = this._scrollAfterIdle;
            this._scrollAfterIdle = 'none';
            if (scrollTarget === 'bottom') this._scroll.get_vadjustment().set_value(this._maxScroll());
            else if (scrollTarget === 'cursor') this._scrollToCursor();
            return GLib.SOURCE_REMOVE;
        });
    }

    private _maxScroll(): number {
        const adj = this._scroll.get_vadjustment();
        const page = adj.get_page_size() || this._scroll.get_height();
        return Math.max(adj.get_lower(), adj.get_upper() - page);
    }

    private _scrollToCursor(): void {
        const rect = this.entry.clutter_text.get_cursor_rect();
        const adj = this._scroll.get_vadjustment();
        const page = adj.get_page_size() || this._scroll.get_height();
        const top = rect.get_y();
        const bottom = top + Math.max(1, rect.get_height());
        let value = adj.get_value();
        if (top - CURSOR_MARGIN < value) value = top - CURSOR_MARGIN;
        else if (bottom + CURSOR_MARGIN > value + page) value = bottom + CURSOR_MARGIN - page;
        adj.set_value(Math.max(adj.get_lower(), Math.min(value, this._maxScroll())));
    }
}

function voiceControl(icon: St.Icon, accessibleName: string): St.Button {
    const button = new St.Button({
        style_class: 'mei-mic-btn', can_focus: true, reactive: true, track_hover: true, visible: false,
        accessible_name: accessibleName, accessible_role: Atk.Role.PUSH_BUTTON, child: icon,
    });
    addClickScale(button);
    return button;
}

/** In use: the button widens and inverts, and pressing it again ends what it started. */
function setActive(button: St.Button, active: boolean, accessibleName: string): void {
    if (active) button.add_style_class_name('active');
    else button.remove_style_class_name('active');
    button.x_expand = active;
    button.accessible_name = accessibleName;
}
