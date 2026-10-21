/**
 * The message box and the Ask button. The input grows with its text up to a maximum height, then
 * scrolls, keeping the cursor in view. Enter sends; Shift+Enter adds a line. While Mei works, a
 * message sent joins the task in progress (the runtime steers it, §8.1), and in compact mode the
 * Ask button becomes Stop.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Atk from 'gi://Atk';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import St from 'gi://St';

import { addClickScale } from '../effects.js';
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
}

export class Composer {
    readonly actor = new St.BoxLayout({ vertical: true, x_expand: true });
    readonly entry: St.Entry;
    readonly askButton: St.Button;
    private readonly _scroll: St.ScrollView;
    private _loading = false;
    private _expanded = false;
    private _layoutId = 0;
    private _scrollId = 0;
    private _blinkId = 0;
    private _scrollAfterLayout: InputScrollTarget = 'none';
    private _scrollAfterIdle: InputScrollTarget = 'none';

    constructor(private readonly _sources: SourceSet, private readonly _maxHeight: number,
        private readonly _actions: ComposerActions) {
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
        this.actor.add_child(this.askButton);
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
