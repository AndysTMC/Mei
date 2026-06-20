/**
 * Chat popup — the dropdown panel containing messages, input, and buttons.
 *
 * Layout (top to bottom):
 *   ┌─────────────────────────────────┐
 *   │ [settings ⚙ icon, top-right]   │
 *   │ scrollable message area         │
 *   │ [Copy] button (if reply exists) │
 *   │ text input                      │
 *   │ [Ask] button                    │
 *   └─────────────────────────────────│
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import St from 'gi://St';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Animation from 'resource:///org/gnome/shell/ui/animation.js';

import { parseMarkdown } from './markdown.js';
import { ThemeManager, type ThemedWidgets } from '../utils/theme.js';
import { Logger, Tag } from '../utils/logger.js';

const CHAT_WIDTH = 350;
const INPUT_MIN_HEIGHT = 22;
type InputScrollTarget = 'none' | 'top' | 'cursor' | 'bottom';
const INPUT_SCROLL_PRIORITY: Record<InputScrollTarget, number> = {
    none: 0,
    top: 1,
    cursor: 2,
    bottom: 3,
};

export class ChatPopup {
    private _menu: PopupMenu.PopupMenu;
    private _container: St.BoxLayout;
    private _scrollView: St.ScrollView;
    private _messageBox: St.BoxLayout;
    private _entry: St.Entry;
    private _askBtn: St.Button;
    private _spinner!: Animation.Spinner;
    private _isLoading = false;
    private _copyBtn: St.Button;
    private _settingsBtn: St.Button;
    private _popupItem: PopupMenu.PopupBaseMenuItem;
    private _themeManager: ThemeManager;
    private _themeSignalId: number = 0;
    private _lastReply: string | null = null;
    private _focusTimeoutId: number = 0;
    private _blinkTimeoutId: number = 0;
    private _copyTimeoutId: number = 0;
    private _historyScrollTimeoutId: number = 0;
    private _inputLayoutTimeoutId: number = 0;
    private _inputScrollTimeoutId: number = 0;
    private _inputScrollTargetAfterLayout: InputScrollTarget = 'none';
    private _inputScrollTargetAfterIdle: InputScrollTarget = 'none';
    private _isExpanded: boolean = false;
    private _expandBtn!: St.Button;
    private _expandIcon!: St.Icon;
    private _contentBox!: St.BoxLayout;
    private _inputScrollView!: St.ScrollView;
    private _contentMaxHeight: number;
    private _inputMaxHeight: number;

    /** Called when the user sends a message. */
    onSend: ((text: string) => void) | null = null;

    /** Called when the settings icon is clicked. */
    onOpenSettings: (() => void) | null = null;

    /** Called when the popup is expanded or restored. */
    onToggleExpand: ((isExpanded: boolean) => void) | null = null;

    /** Called when the user clicks the reload icon on an AI response. */
    onReload: ((index: number) => void) | null = null;

    constructor(anchor: St.Widget, themeManager: ThemeManager) {
        this._themeManager = themeManager;

        const monitor = Main.layoutManager.primaryMonitor;
        const screenHeight = monitor ? monitor.height : 1080;
        this._contentMaxHeight = Math.round(screenHeight * 0.60);
        this._inputMaxHeight = Math.round(screenHeight * 0.20);

        /* ── Popup menu ───────────────────────────────── */
        this._menu = new PopupMenu.PopupMenu(anchor, 0.5, St.Side.TOP);
        this._menu.actor.add_style_class_name('mei-popup');
        Main.uiGroup.add_child(this._menu.actor);
        Main.panel.menuManager.addMenu(this._menu);
        this._menu.close();

        /* Auto-focus input on open */
        (this._menu as any).connect('open-state-changed', (_menu: any, isOpen: boolean) => {
            Logger.debug(Tag.UI, `Popup ${isOpen ? 'opened' : 'closed'}`);
            if (isOpen) {
                this._clearFocusTimeout();
                this._focusTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                    this._focusTimeoutId = 0;
                    this._entry?.grab_key_focus();
                    this._queueInputLayoutUpdate('cursor');
                    return GLib.SOURCE_REMOVE;
                });
            } else {
                this._clearFocusTimeout();
                this._stopCursorBlink();
                this._resetCopyState();
            }
        });

        /* ── Popup content ────────────────────────────── */
        this._menu.box.style = 'padding: 0; margin: 0;';

        this._popupItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        this._popupItem.style = 'padding: 0; margin: 0;';
        this._menu.addMenuItem(this._popupItem);

        this._container = new St.BoxLayout({
            vertical: true,
            style_class: 'mei-container',
            width: CHAT_WIDTH,
        });
        this._popupItem.add_child(this._container);

        /* ── Header bar (Copy left, Settings right) ───── */
        const topBar = new St.BoxLayout({
            x_expand: true,
        });

        // Copy Button (text only)
        this._copyBtn = new St.Button({
            label: 'Copy',
            style_class: 'mei-copy-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            visible: false,
        });
        this._copyBtn.connect('clicked', () => {
            if (this._lastReply) {
                St.Clipboard.get_default().set_text(
                    St.ClipboardType.CLIPBOARD,
                    this._lastReply
                );

                if (this._copyTimeoutId !== 0) {
                    GLib.source_remove(this._copyTimeoutId);
                    this._copyTimeoutId = 0;
                }

                this._copyBtn.set_label('Copied');

                this._copyTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
                    this._copyBtn.set_label('Copy');
                    this._copyTimeoutId = 0;
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        topBar.add_child(this._copyBtn);
        this._addButtonClickScaleEffect(this._copyBtn);

        // Spacer to push settings button to the far right
        const spacer = new St.Widget({
            x_expand: true,
        });
        topBar.add_child(spacer);

        // Expand Icon & Button
        this._expandIcon = new St.Icon({
            icon_name: 'chat-symbolic',
            icon_size: 14,
        });
        this._expandBtn = new St.Button({
            style_class: 'mei-expand-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: this._expandIcon,
        });
        this._expandBtn.connect('clicked', () => {
            this.toggleExpand();
        });
        topBar.add_child(this._expandBtn);
        this._addButtonClickScaleEffect(this._expandBtn);

        // Settings Icon
        this._settingsBtn = new St.Button({
            style_class: 'mei-settings-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: new St.Icon({
                icon_name: 'emblem-system-symbolic',
                icon_size: 14,
            }),
        });
        this._settingsBtn.connect('clicked', () => {
            this._menu.close();
            this.onOpenSettings?.();
        });
        topBar.add_child(this._settingsBtn);
        this._container.add_child(topBar);

        /* ── Content Box (Fading container) ───────────── */
        this._contentBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
        });
        this._container.add_child(this._contentBox);

        /* ── Message area (scrollable, max 60vh) ──────── */
        this._scrollView = new St.ScrollView({
            style_class: 'mei-scroll',
            x_expand: true,
            visible: false,
            overlay_scrollbars: true,
        });
        this._scrollView.set_policy(
            St.PolicyType.NEVER,
            St.PolicyType.AUTOMATIC
        );
        this._scrollView.set_style(`max-height: ${this._contentMaxHeight}px;`);

        this._messageBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });
        (this._messageBox as any).spacing = 8;
        this._scrollView.set_child(this._messageBox);
        this._contentBox.add_child(this._scrollView);

        /* ── Input ────────────────────────────────────── */
        this._entry = new St.Entry({
            hint_text: 'Ask Mei anything…',
            can_focus: true,
            x_expand: true,
            style_class: 'mei-input',
        });

        const ct = this._entry.clutter_text;
        ct.set_single_line_mode(false);
        ct.set_line_wrap(true);
        ct.set_line_wrap_mode(0); // WORD_CHAR
        ct.cursor_visible = true;

        ct.connect('key-focus-in', () => this._startCursorBlink());
        ct.connect('key-focus-out', () => this._stopCursorBlink());
        ct.connect('text-changed', () => {
            this._resetCursorBlink();
            this._queueInputLayoutUpdate('bottom');
        });
        ct.connect('cursor-changed', () => this._queueInputLayoutUpdate('cursor'));

        ct.connect('key-press-event', (_actor: any, event: Clutter.Event) => {
            const key = event.get_key_symbol();
            if (key === Clutter.KEY_Return || key === Clutter.KEY_KP_Enter) {
                const state = event.get_state();
                if ((state & Clutter.ModifierType.SHIFT_MASK) === 0) {
                    this._handleSend();
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        });

        const inputBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });
        inputBox.add_child(this._entry);

        this._inputScrollView = new St.ScrollView({
            style_class: 'mei-input-scroll',
            x_expand: true,
            overlay_scrollbars: true,
        });
        this._inputScrollView.set_policy(
            St.PolicyType.NEVER,
            St.PolicyType.AUTOMATIC
        );
        this._inputScrollView.set_style(`max-height: ${this._inputMaxHeight}px;`);
        this._inputScrollView.set_child(inputBox);
        this._contentBox.add_child(this._inputScrollView);
        this._queueInputLayoutUpdate();

        /* ── Ask button ───────────────────────────────── */
        this._askBtn = new St.Button({
            label: 'Ask',
            style_class: 'mei-ask-btn',
            can_focus: true,
            x_expand: true,
            reactive: true,
            track_hover: true,
        });
        this._askBtn.connect('clicked', () => this._handleSend());
        this._contentBox.add_child(this._askBtn);
        this._addButtonClickScaleEffect(this._askBtn);

        this._spinner = new Animation.Spinner(16, {
            animate: false,
            hideOnStop: true,
        });
        this._spinner.x_align = Clutter.ActorAlign.CENTER;
        this._spinner.y_align = Clutter.ActorAlign.CENTER;
        this._spinner.x_expand = true;
        this._spinner.y_expand = true;
        this._spinner.visible = false;
        this._contentBox.add_child(this._spinner);

        /* ── Apply theme ──────────────────────────────── */
        this._applyTheme();
        this._themeSignalId = this._themeManager.onThemeChanged(() => this._applyTheme());
    }

    /* ── Public API ───────────────────────────────────── */

    get isExpanded(): boolean {
        return this._isExpanded;
    }

    open(): void {
        this._menu.open();
    }

    close(): void {
        this._menu.close();
    }

    toggle(): void {
        this._menu.toggle();
    }

    /**
     * Display a message bubble in the scroll area.
     * Assistant messages are rendered with Pango markup.
     */
    showMessage(role: 'user' | 'assistant', text: string): void {
        this._messageBox.destroy_all_children();

        if (!text) {
            this._scrollView.visible = false;
            this._copyBtn.visible = false;
            return;
        }

        const bubble = new St.Label({
            style_class: role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai',
            x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
        });
        bubble.clutter_text.set_line_wrap(true);
        bubble.clutter_text.set_line_wrap_mode(0);
        bubble.clutter_text.set_ellipsize(0);

        if (role === 'assistant') {
            bubble.clutter_text.use_markup = true;
            try {
                bubble.clutter_text.set_markup(parseMarkdown(text));
            } catch (_e) {
                Logger.warn(Tag.UI, 'Pango markup parse failed, falling back to plain text');
                bubble.clutter_text.use_markup = false;
                bubble.clutter_text.set_text(text);
            }
            this._lastReply = text;
            this._copyBtn.visible = !this._isExpanded && text.length > 0;
        } else {
            bubble.clutter_text.set_text(text);
            this._copyBtn.visible = false;
        }

        this._messageBox.add_child(bubble);
        this._scrollView.visible = true;
    }

    /** Clear the message area and hide it. */
    clearMessages(): void {
        this._messageBox.destroy_all_children();
        this._scrollView.visible = false;
        this._copyBtn.visible = false;
        this._resetCopyState();
    }

    /**
     * Display the full chat history in the scroll area.
     * Assistant messages are rendered with Pango markup, and user messages are aligned to the right.
     */
    showHistory(messages: { role: string, content: string }[]): void {
        this._messageBox.destroy_all_children();

        for (let i = 0; i < messages.length; i++) {
            const msg = messages[i];
            const role = msg.role;
            const text = msg.content;

            const msgContainer = new St.BoxLayout({
                vertical: true,
                x_expand: true,
                style_class: 'mei-msg-container',
            });

            const bubble = new St.Label({
                style_class: role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai',
                x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
            });
            bubble.clutter_text.set_line_wrap(true);
            bubble.clutter_text.set_line_wrap_mode(0);
            bubble.clutter_text.set_ellipsize(0);

            if (role === 'assistant') {
                bubble.clutter_text.use_markup = true;
                try {
                    bubble.clutter_text.set_markup(parseMarkdown(text));
                } catch (_e) {
                    bubble.clutter_text.use_markup = false;
                    bubble.clutter_text.set_text(text);
                }
            } else {
                bubble.clutter_text.set_text(text);
            }

            msgContainer.add_child(bubble);

            // Action buttons bar below each message
            const actionBar = new St.BoxLayout({
                style_class: 'mei-action-bar',
                x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
            });

            // Copy button
            const copyIcon = new St.Icon({
                icon_name: 'edit-copy-symbolic',
                icon_size: 12,
            });
            const copyBtn = new St.Button({
                style_class: 'mei-action-btn',
                can_focus: true,
                reactive: true,
                track_hover: true,
                child: copyIcon,
            });
            copyBtn.connect('clicked', () => {
                St.Clipboard.get_default().set_text(
                    St.ClipboardType.CLIPBOARD,
                    text
                );
                copyIcon.icon_name = 'object-select-symbolic';
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
                    copyIcon.icon_name = 'edit-copy-symbolic';
                    return GLib.SOURCE_REMOVE;
                });
            });
            actionBar.add_child(copyBtn);
            this._addButtonClickScaleEffect(copyBtn);

            // Reload button (only for assistant/AI messages)
            if (role === 'assistant') {
                const reloadIcon = new St.Icon({
                    icon_name: 'view-refresh-symbolic',
                    icon_size: 12,
                });
                const reloadBtn = new St.Button({
                    style_class: 'mei-action-btn',
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                    child: reloadIcon,
                });
                reloadBtn.connect('clicked', () => {
                    this.onReload?.(i);
                });
                actionBar.add_child(reloadBtn);
                this._addButtonClickScaleEffect(reloadBtn);
            }

            msgContainer.add_child(actionBar);
            this._messageBox.add_child(msgContainer);
        }

        this._scrollView.visible = messages.length > 0;
        this._copyBtn.visible = false; // Never show top copy button in history (big) mode

        this._queueHistoryScrollToBottom();
    }

    toggleExpand(): void {
        this._isExpanded = !this._isExpanded;

        if (this._isExpanded) {
            this._container.add_style_class_name('expanded');
        } else {
            this._container.remove_style_class_name('expanded');
        }

        // 1. Fade out the content smoothly
        this._contentBox.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                const targetWidth = this._isExpanded ? 650 : CHAT_WIDTH;

                // Update settings/expand icon and copy button visibility
                this._expandIcon.icon_name = this._isExpanded
                    ? 'bolt-symbolic'
                    : 'chat-symbolic';

                // Notify extension to refresh rendering (via onToggleExpand)
                this.onToggleExpand?.(this._isExpanded);

                // 2. Animate the container size
                this._container.ease({
                    width: targetWidth,
                    duration: 200,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    onComplete: () => {
                        this._queueInputLayoutUpdate('cursor');

                        // 3. Fade the content back in
                        this._contentBox.ease({
                            opacity: 255,
                            duration: 150,
                            mode: Clutter.AnimationMode.EASE_IN_QUAD,
                        });
                    }
                });
            }
        });
    }

    /** Sets the loading state of the ask button. */
    setLoading(loading: boolean): void {
        if (this._isLoading === loading) return;
        this._isLoading = loading;

        if (loading) {
            this._askBtn.set_label('');
            this._reparentSpinner(this._askBtn);
            this._spinner.play();
            this._askBtn.reactive = false;
        } else {
            this._spinner.stop();
            this._reparentSpinner(null);
            this._spinner.visible = false;
            this._reparentSpinner(this._contentBox);
            this._askBtn.set_label('Ask');
            this._askBtn.reactive = true;
        }
    }

    private _reparentSpinner(newParent: St.Widget | St.Button | null): void {
        const parent = this._spinner.get_parent();
        if (parent) {
            if (parent instanceof St.Button) {
                parent.set_child(null);
            } else {
                parent.remove_child(this._spinner);
            }
        }
        if (newParent) {
            if (newParent instanceof St.Button) {
                newParent.set_child(this._spinner);
            } else {
                newParent.add_child(this._spinner);
            }
        }
    }

    /* ── Private ──────────────────────────────────────── */

    private _handleSend(): void {
        const text = this._entry.get_text().trim();
        if (!text) return;
        this._entry.set_text('');
        this._queueInputLayoutUpdate('top');
        this.onSend?.(text);
    }

    private _clearFocusTimeout(): void {
        if (this._focusTimeoutId !== 0) {
            GLib.source_remove(this._focusTimeoutId);
            this._focusTimeoutId = 0;
        }
    }

    private _clearInputTimeouts(): void {
        if (this._inputLayoutTimeoutId !== 0) {
            GLib.source_remove(this._inputLayoutTimeoutId);
            this._inputLayoutTimeoutId = 0;
        }

        if (this._inputScrollTimeoutId !== 0) {
            GLib.source_remove(this._inputScrollTimeoutId);
            this._inputScrollTimeoutId = 0;
        }

        this._inputScrollTargetAfterLayout = 'none';
        this._inputScrollTargetAfterIdle = 'none';
    }

    private _queueInputLayoutUpdate(scrollTarget: InputScrollTarget = 'none'): void {
        if (INPUT_SCROLL_PRIORITY[scrollTarget] > INPUT_SCROLL_PRIORITY[this._inputScrollTargetAfterLayout]) {
            this._inputScrollTargetAfterLayout = scrollTarget;
        }

        if (this._inputLayoutTimeoutId !== 0) return;

        this._inputLayoutTimeoutId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            const scrollTarget = this._inputScrollTargetAfterLayout;
            this._inputLayoutTimeoutId = 0;
            this._inputScrollTargetAfterLayout = 'none';
            this._updateInputLayout(scrollTarget);
            return GLib.SOURCE_REMOVE;
        });
    }

    private _updateInputLayout(scrollTarget: InputScrollTarget): void {
        const allocatedWidth = Math.max(
            this._inputScrollView.get_width(),
            this._entry.get_width(),
            this._container.get_width() - 20,
            CHAT_WIDTH
        );
        const width = Math.max(1, Math.floor(allocatedWidth));
        const [, naturalHeight] = this._entry.clutter_text.get_preferred_height(width);
        const contentHeight = Math.max(INPUT_MIN_HEIGHT, Math.ceil(naturalHeight));
        const viewportHeight = Math.min(contentHeight, this._inputMaxHeight);

        this._entry.set_height(contentHeight);
        this._inputScrollView.set_height(viewportHeight);

        switch (scrollTarget) {
            case 'bottom':
            case 'cursor':
                this._queueScrollInput(scrollTarget);
                break;
            case 'top':
                this._inputScrollView.get_vadjustment().set_value(0);
                break;
            case 'none':
                break;
        }
    }

    private _queueScrollInput(scrollTarget: 'cursor' | 'bottom'): void {
        if (INPUT_SCROLL_PRIORITY[scrollTarget] > INPUT_SCROLL_PRIORITY[this._inputScrollTargetAfterIdle]) {
            this._inputScrollTargetAfterIdle = scrollTarget;
        }

        if (this._inputScrollTimeoutId !== 0) return;

        this._inputScrollTimeoutId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            const scrollTarget = this._inputScrollTargetAfterIdle;
            this._inputScrollTimeoutId = 0;
            this._inputScrollTargetAfterIdle = 'none';

            if (scrollTarget === 'bottom') {
                this._scrollInputToBottom();
            } else if (scrollTarget === 'cursor') {
                this._scrollInputToCursor();
            }

            return GLib.SOURCE_REMOVE;
        });
    }

    private _getInputScrollMaxValue(): number {
        const adj = this._inputScrollView.get_vadjustment();
        const pageSize = adj.get_page_size() || this._inputScrollView.get_height();
        return Math.max(adj.get_lower(), adj.get_upper() - pageSize);
    }

    private _scrollInputToBottom(): void {
        this._inputScrollView.get_vadjustment().set_value(this._getInputScrollMaxValue());
    }

    private _scrollInputToCursor(): void {
        const ct = this._entry.clutter_text;
        const rect = ct.get_cursor_rect();
        const adj = this._inputScrollView.get_vadjustment();
        const pageSize = adj.get_page_size() || this._inputScrollView.get_height();
        const lower = adj.get_lower();
        const maxValue = this._getInputScrollMaxValue();
        const cursorY = rect.get_y();
        const cursorHeight = Math.max(1, rect.get_height());
        const padding = 2;
        let value = adj.get_value();

        if (cursorY - padding < value) {
            value = cursorY - padding;
        } else if (cursorY + cursorHeight + padding > value + pageSize) {
            value = cursorY + cursorHeight + padding - pageSize;
        }

        adj.set_value(Math.max(lower, Math.min(value, maxValue)));
    }

    private _queueHistoryScrollToBottom(): void {
        if (this._historyScrollTimeoutId !== 0) {
            GLib.source_remove(this._historyScrollTimeoutId);
            this._historyScrollTimeoutId = 0;
        }

        this._historyScrollTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
            this._historyScrollTimeoutId = 0;
            const adj = this._scrollView.get_vadjustment();
            const maxValue = Math.max(adj.get_lower(), adj.get_upper() - adj.get_page_size());
            adj.set_value(maxValue);
            return GLib.SOURCE_REMOVE;
        });
    }

    private _applyTheme(): void {
        const widgets: ThemedWidgets = {
            menuBox: this._menu.box,
            popupItem: this._popupItem as unknown as St.Widget,
            container: this._container,
            entry: this._entry,
            askBtn: this._askBtn,
            copyBtn: this._copyBtn,
        };
        this._themeManager.applyTheme(widgets);

        // Icons are gray so they're visible but not bright white/black
        const iconColor = this._themeManager.isDark ? '#a0a0a0' : '#666666';
        const iconStyle = `background-color: transparent; border: none; padding: 2px; width: 22px; height: 22px; color: ${iconColor};`;
        this._settingsBtn.set_style(iconStyle);
        this._expandBtn.set_style(iconStyle);
    }

    private _startCursorBlink(): void {
        if (this._blinkTimeoutId) return;
        const ct = this._entry.clutter_text;
        ct.cursor_visible = true;
        this._blinkTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            ct.cursor_visible = !ct.cursor_visible;
            return GLib.SOURCE_CONTINUE;
        });
    }

    private _stopCursorBlink(): void {
        if (this._blinkTimeoutId) {
            GLib.source_remove(this._blinkTimeoutId);
            this._blinkTimeoutId = 0;
        }
        this._entry.clutter_text.cursor_visible = false;
    }

    private _resetCursorBlink(): void {
        if (this._blinkTimeoutId) {
            GLib.source_remove(this._blinkTimeoutId);
            this._blinkTimeoutId = 0;
        }
        const ct = this._entry.clutter_text;
        ct.cursor_visible = true;
        this._blinkTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            ct.cursor_visible = !ct.cursor_visible;
            return GLib.SOURCE_CONTINUE;
        });
    }

    private _addButtonClickScaleEffect(button: St.Button): void {
        button.connect('button-press-event', () => {
            button.set_pivot_point(0.5, 0.5);
            button.ease({
                scaleX: 0.95,
                scaleY: 0.95,
                duration: 80,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
            return Clutter.EVENT_PROPAGATE;
        });

        const restoreScale = () => {
            button.ease({
                scaleX: 1.0,
                scaleY: 1.0,
                duration: 80,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            });
        };

        button.connect('button-release-event', () => {
            restoreScale();
            return Clutter.EVENT_PROPAGATE;
        });

        button.connect('clicked', () => {
            restoreScale();
        });

        button.connect('leave-event', () => {
            restoreScale();
            return Clutter.EVENT_PROPAGATE;
        });
    }

    private _resetCopyState(): void {
        if (this._copyTimeoutId !== 0) {
            GLib.source_remove(this._copyTimeoutId);
            this._copyTimeoutId = 0;
        }
        this._copyBtn.set_label('Copy');
    }

    /* ── Cleanup ──────────────────────────────────────── */

    destroy(): void {
        if (this._themeSignalId !== 0) {
            this._themeManager.disconnect(this._themeSignalId);
            this._themeSignalId = 0;
        }
        this._clearFocusTimeout();
        this._clearInputTimeouts();
        if (this._historyScrollTimeoutId !== 0) {
            GLib.source_remove(this._historyScrollTimeoutId);
            this._historyScrollTimeoutId = 0;
        }
        this._stopCursorBlink();
        this._resetCopyState();
        if (this._menu) {
            Main.panel.menuManager.removeMenu(this._menu);
            Main.uiGroup.remove_child(this._menu.actor);
            this._menu.destroy();
        }
    }
}
