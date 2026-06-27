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

export interface ChatSummary {
    id: string;
    title: string;
}

export class ChatPopup {
    private _menu: PopupMenu.PopupMenu;
    private _container: St.BoxLayout;
    private _scrollView: St.ScrollView;
    private _messageBox: St.BoxLayout;
    private _entry: St.Entry;
    private _askBtn: St.Button;
    private _spinner!: Animation.Spinner;
    private _loadingBubble?: St.BoxLayout;
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

    // Layout view managers
    private _chatView!: St.BoxLayout;
    private _topBar!: St.BoxLayout;
    private _clearBtn!: St.Button;
    private _newChatBtn!: St.Button;
    private _historyBtn!: St.Button;
    private _errorContainer!: St.BoxLayout;
    private _errorMessage: string = '';
    private _historyView!: St.BoxLayout;
    private _historyTopBar!: St.BoxLayout;
    private _backBtn!: St.Button;
    private _historyTitle!: St.Label;
    private _historyScrollView!: St.ScrollView;
    private _historyListBox!: St.BoxLayout;

    private _hasMessages: boolean = false;
    private _isHistoryView: boolean = false;

    /** Called when the user sends a message. */
    onSend: ((text: string) => void) | null = null;

    /** Called when the user clicks the stop button to cancel request. */
    onCancel: (() => void) | null = null;

    /** Called when the settings icon is clicked. */
    onOpenSettings: (() => void) | null = null;

    /** Called when the popup is expanded or restored. */
    onToggleExpand: ((isExpanded: boolean) => void) | null = null;

    /** Called when the user clicks the reload icon on an AI response. */
    onReload: ((index: number) => void) | null = null;

    /** Called when the user requests to clear the current chat (new chat). */
    onNewChat: (() => void) | null = null;

    /** Called when the user requests to show the history list. */
    onHistoryRequested: (() => void) | null = null;

    /** Called when a chat session is selected from the history list to load. */
    onLoadChat: ((id: string) => void) | null = null;

    /** Called when a chat session is deleted from the history list. */
    onDeleteChat: ((id: string) => void) | null = null;

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
        this._menu.box.add_style_class_name('mei-menu-box');

        this._popupItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        this._popupItem.add_style_class_name('mei-popup-item');
        this._menu.addMenuItem(this._popupItem);

        this._container = new St.BoxLayout({
            vertical: true,
            style_class: 'mei-container',
            width: CHAT_WIDTH,
        });
        this._popupItem.add_child(this._container);

        /* ── Chat View (wraps topBar + contentBox) ────── */
        this._chatView = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
        });

        /* ── Header bar ──────────────────────────────── */
        this._topBar = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-top-bar'
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
        this._topBar.add_child(this._copyBtn);
        this._addButtonClickScaleEffect(this._copyBtn);

        // Spacer to push action buttons to the far right
        const spacer = new St.Widget({
            x_expand: true,
        });
        this._topBar.add_child(spacer);

        // Clear button (small popup only — starts new chat)
        this._clearBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: new St.Icon({
                icon_name: 'edit-clear-all-symbolic',
                icon_size: 14,
            }),
            visible: true,
        });
        this._clearBtn.connect('clicked', () => {
            if (!this._hasMessages) return;
            this.onNewChat?.();
        });
        this._topBar.add_child(this._clearBtn);
        this._addButtonClickScaleEffect(this._clearBtn);

        // New Chat / Edit button (big popup only)
        this._newChatBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: new St.Icon({
                icon_name: 'document-edit-symbolic',
                icon_size: 14,
            }),
            visible: false,
        });
        this._newChatBtn.connect('clicked', () => {
            if (!this._hasMessages) return;
            this.onNewChat?.();
        });
        this._topBar.add_child(this._newChatBtn);
        this._addButtonClickScaleEffect(this._newChatBtn);

        // History button (big popup only)
        this._historyBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: new St.Icon({
                icon_name: 'document-open-recent-symbolic',
                icon_size: 14,
            }),
            visible: false,
        });
        this._historyBtn.connect('clicked', () => {
            this.onHistoryRequested?.();
        });
        this._topBar.add_child(this._historyBtn);
        this._addButtonClickScaleEffect(this._historyBtn);

        // Expand Icon & Button
        this._expandIcon = new St.Icon({
            icon_name: 'chat-symbolic',
            icon_size: 14,
        });
        this._expandBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: this._expandIcon,
        });
        this._expandBtn.connect('clicked', () => {
            this.toggleExpand();
        });
        this._topBar.add_child(this._expandBtn);
        this._addButtonClickScaleEffect(this._expandBtn);

        // Settings Icon
        this._settingsBtn = new St.Button({
            style_class: 'mei-icon-btn',
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
        this._topBar.add_child(this._settingsBtn);
        this._chatView.add_child(this._topBar);

        /* ── Content Box (Fading container) ───────────── */
        this._contentBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
        });

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
            style_class: 'mei-message-box',
        });
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
        ct.x_expand = true;
        ct.y_expand = true;
        ct.x_align = Clutter.ActorAlign.FILL;
        ct.y_align = Clutter.ActorAlign.FILL;

        ct.connect('key-focus-in', () => this._startCursorBlink());
        ct.connect('key-focus-out', () => this._stopCursorBlink());
        ct.connect('text-changed', () => {
            this._resetCursorBlink();
            this._queueInputLayoutUpdate('cursor');
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

        // Intercept clicks on the St.Entry padding/margin area (empty space to
        // the right of short lines). Transform the click coordinates into the
        // ClutterText actor's own coordinate space and use coords_to_position()
        // to place the cursor at the nearest character.
        this._entry.connect('button-press-event', (_actor: any, event: Clutter.Event) => {
            const [ex, ey] = event.get_coords();
            const [ok, lx, ly] = ct.transform_stage_point(ex, ey);
            if (ok) {
                const pos = ct.coords_to_position(lx, ly);
                ct.grab_key_focus();
                ct.set_cursor_position(pos);
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
        this._askBtn.connect('clicked', () => {
            if (this._isLoading) {
                this.onCancel?.();
            } else {
                this._handleSend();
            }
        });
        this._contentBox.add_child(this._askBtn);
        this._addButtonClickScaleEffect(this._askBtn);

        /* ── Error pill (hidden by default) ───────────── */
        this._errorContainer = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-error-pill',
            visible: false,
        });
        this._contentBox.add_child(this._errorContainer);

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

        this._chatView.add_child(this._contentBox);
        this._container.add_child(this._chatView);

        /* ── History View ────────────────────────────────── */
        this._historyView = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
            visible: false,
        });

        this._historyTopBar = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-top-bar',
        });

        this._backBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            child: new St.Icon({
                icon_name: 'go-previous-symbolic',
                icon_size: 14,
            }),
        });
        this._backBtn.connect('clicked', () => this.hideHistoryList());
        this._historyTopBar.add_child(this._backBtn);
        this._addButtonClickScaleEffect(this._backBtn);

        // Centered "History" heading label
        this._historyTitle = new St.Label({
            text: 'History',
            style_class: 'mei-history-header-title',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._historyTopBar.add_child(this._historyTitle);

        // Dummy right spacer of matching size (22px) for perfect centering
        const rightSpacer = new St.Widget({
            width: 22,
        });
        this._historyTopBar.add_child(rightSpacer);

        this._historyView.add_child(this._historyTopBar);

        this._historyScrollView = new St.ScrollView({
            style_class: 'mei-scroll',
            x_expand: true,
            y_expand: true,
            overlay_scrollbars: true,
        });
        this._historyScrollView.set_policy(
            St.PolicyType.NEVER,
            St.PolicyType.AUTOMATIC
        );
        this._historyScrollView.set_style(`max-height: ${this._contentMaxHeight}px;`);

        this._historyListBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-history-list',
        });
        this._historyScrollView.set_child(this._historyListBox);
        this._historyView.add_child(this._historyScrollView);

        this._container.add_child(this._historyView);

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
            this._hasMessages = false;
            return;
        }
        this._hasMessages = true;

        const bubble = new St.Label({
            style_class: role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai',
            x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
            x_expand: role === 'assistant',
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

    private _animateHeightChange(changeFn: () => void): void {
        const fromHeight = this._container.get_height();
        this._container.set_height(fromHeight);

        changeFn();

        GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            const containerWidth = this._container.get_width();
            let targetHeight = 0;
            
            if (this._isHistoryView) {
                const [, toHeight] = this._historyView.get_preferred_height(containerWidth);
                const [, topBarHeight] = this._historyTopBar.get_preferred_height(containerWidth);
                targetHeight = toHeight + topBarHeight + 20; // 10px top + 10px bottom margin
            } else {
                const [, toHeight] = this._chatView.get_preferred_height(containerWidth);
                const [, topBarHeight] = this._topBar.get_preferred_height(containerWidth);
                targetHeight = toHeight + topBarHeight + 20; // 10px top + 10px bottom margin
            }

            this._container.ease({
                height: targetHeight,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => {
                    this._container.set_height(-1);
                    if (!this._isHistoryView) {
                        this._queueInputLayoutUpdate('cursor');
                    }
                }
            });
            return GLib.SOURCE_REMOVE;
        });
    }

    /** Clear the message area and hide it. */
    clearMessages(): void {
        this._animateHeightChange(() => {
            this._messageBox.destroy_all_children();
            this._scrollView.visible = false;
            this._copyBtn.visible = false;
            this._hasMessages = false;
            this._resetCopyState();
        });
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
                x_expand: role === 'assistant',
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
        this._copyBtn.visible = false;
        this._hasMessages = messages.length > 0;

        this._queueHistoryScrollToBottom();
    }

    toggleExpand(): void {
        this._isExpanded = !this._isExpanded;

        if (this._isExpanded) {
            this._container.add_style_class_name('expanded');
        } else {
            this._container.remove_style_class_name('expanded');
        }

        // Toggle button visibility based on mode
        this._clearBtn.visible = !this._isExpanded;
        this._newChatBtn.visible = this._isExpanded;
        this._historyBtn.visible = this._isExpanded;

        // If collapsing while in history view, go back to chat first
        if (!this._isExpanded && this._isHistoryView) {
            this._chatView.visible = true;
            this._chatView.opacity = 255;
            this._historyView.visible = false;
            this._isHistoryView = false;
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
            // 1. Change Ask Button to Stop Button
            this._askBtn.set_label('Stop');
            this._askBtn.add_style_class_name('loading');
            this._askBtn.reactive = true; // MUST BE REACTIVE to be clickable!

            // 2. Add AI loading bubble to message box
            this._loadingBubble = new St.BoxLayout({
                style_class: 'mei-bubble-ai',
                x_align: Clutter.ActorAlign.START,
                x_expand: false,
            });
            this._reparentSpinner(this._loadingBubble);
            this._spinner.play();
            this._spinner.visible = true;
            this._messageBox.add_child(this._loadingBubble);
            this._scrollView.visible = true;
            this._hasMessages = true;

            // Auto-scroll to bottom
            GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                const adjustment = this._scrollView.vscroll.adjustment;
                adjustment.value = adjustment.upper - adjustment.page_size;
                return GLib.SOURCE_REMOVE;
            });
        } else {
            this._askBtn.remove_style_class_name('loading');
            this._askBtn.set_label('Ask');
            this._askBtn.reactive = true;

            // Workaround for Clutter hover/scale sticking when child is replaced during interaction
            this._askBtn.scale_x = 1.0;
            this._askBtn.scale_y = 1.0;
            this._askBtn.sync_hover();

            // Safely clean up spinner — detach from whatever parent it's in
            this._spinner.stop();
            this._spinner.visible = false;
            const spinnerParent = this._spinner.get_parent();
            if (spinnerParent) {
                if (spinnerParent instanceof St.Button) {
                    spinnerParent.set_child(null);
                } else {
                    spinnerParent.remove_child(this._spinner);
                }
            }
            this._contentBox.add_child(this._spinner);

            // Safely clean up loading bubble — it may already be destroyed
            // by showHistory/clearMessages calling destroy_all_children()
            if (this._loadingBubble) {
                const bubbleParent = this._loadingBubble.get_parent();
                if (bubbleParent) {
                    bubbleParent.remove_child(this._loadingBubble);
                    this._loadingBubble.destroy();
                }
                this._loadingBubble = undefined;
            }
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

    /* ── Error pill ──────────────────────────────────── */

    /** Show an error pill below the Ask button. */
    showError(message: string): void {
        this._errorMessage = message;
        this._errorContainer.destroy_all_children();

        // Row: warning icon + error text
        const row = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-error-row',
        });

        const icon = new St.Icon({
            icon_name: 'dialog-warning-symbolic',
            icon_size: 14,
            y_align: Clutter.ActorAlign.START,
        });
        row.add_child(icon);

        const label = new St.Label({
            text: message,
            x_expand: true,
            style_class: 'mei-error-text',
        });
        label.clutter_text.set_line_wrap(true);
        label.clutter_text.set_line_wrap_mode(0);
        label.clutter_text.set_ellipsize(0);
        row.add_child(label);

        this._errorContainer.add_child(row);

        // Copy Error button
        const copyBtn = new St.Button({
            label: 'Copy Error',
            style_class: 'mei-error-copy-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
        });
        copyBtn.connect('clicked', () => {
            St.Clipboard.get_default().set_text(
                St.ClipboardType.CLIPBOARD,
                this._errorMessage
            );
            copyBtn.set_label('Copied');
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
                if (copyBtn.get_parent()) copyBtn.set_label('Copy Error');
                return GLib.SOURCE_REMOVE;
            });
        });
        this._errorContainer.add_child(copyBtn);
        this._addButtonClickScaleEffect(copyBtn);

        this._errorContainer.visible = true;
        this._applyErrorTheme();
    }

    /** Hide the error pill. */
    hideError(): void {
        this._errorContainer.visible = false;
        this._errorContainer.destroy_all_children();
        this._errorMessage = '';
    }

    /* ── History list panel ──────────────────────────── */

    /**
     * Populate and show the history panel (big popup only).
     * Fades out the chat view and fades in the history list.
     */
    showHistoryList(items: ChatSummary[]): void {
        // Populate list
        this._historyListBox.destroy_all_children();

        if (items.length === 0) {
            const emptyLabel = new St.Label({
                text: 'No saved chats',
                style_class: 'mei-history-empty',
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            this._historyListBox.add_child(emptyLabel);
        } else {
            for (const item of items) {
                const row = new St.BoxLayout({
                    x_expand: true,
                    style_class: 'mei-history-item-row',
                });

                const titleBtn = new St.Button({
                    label: item.title || 'Untitled',
                    style_class: 'mei-history-title-btn',
                    x_expand: true,
                    x_align: Clutter.ActorAlign.FILL,
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                });
                titleBtn.connect('clicked', () => {
                    this.hideHistoryList();
                    this.onLoadChat?.(item.id);
                });
                row.add_child(titleBtn);
                this._addButtonClickScaleEffect(titleBtn);

                const deleteBtn = new St.Button({
                    style_class: 'mei-history-delete-btn',
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                    child: new St.Icon({
                        icon_name: 'user-trash-symbolic',
                        icon_size: 14,
                    }),
                });
                deleteBtn.connect('clicked', () => {
                    row.ease({
                        opacity: 0,
                        duration: 150,
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                        onComplete: () => {
                            row.destroy();
                        },
                    });
                    this.onDeleteChat?.(item.id);
                });
                row.add_child(deleteBtn);
                this._addButtonClickScaleEffect(deleteBtn);

                this._historyListBox.add_child(row);
            }
        }

        this._applyHistoryTheme();

        // Transition: Fade out chat → animate height → fade in history
        this._chatView.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                // 1. Freeze container at current height BEFORE anything changes
                const fromHeight = this._container.get_height();
                this._container.set_height(fromHeight);

                // 2. Swap views while height is frozen — no visual change
                this._chatView.visible = false;
                this._historyView.visible = true;
                this._historyView.opacity = 0;

                // 3. Query the preferred height without releasing the pin
                const containerWidth = this._container.get_width();
                const [, toHeight] = this._historyView.get_preferred_height(containerWidth);
                // Add top-bar height + spacing to get full container target
                const [, topBarHeight] = this._historyTopBar.get_preferred_height(containerWidth);
                const targetHeight = toHeight + topBarHeight + 20; // 10px top + 10px bottom margin

                // 4. Animate height — container stays pinned, only ease changes it
                this._container.ease({
                    height: targetHeight,
                    duration: 200,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    onComplete: () => {
                        this._container.set_height(-1); // Release pin
                        this._historyView.ease({
                            opacity: 255,
                            duration: 150,
                            mode: Clutter.AnimationMode.EASE_IN_QUAD,
                        });
                        this._isHistoryView = true;
                    },
                });
            },
        });
    }

    /** Hide the history panel and show the chat view. */
    hideHistoryList(): void {
        if (!this._isHistoryView) return;

        // Transition: Fade out history → animate height → fade in chat
        this._historyView.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                // 1. Freeze container at current height BEFORE anything changes
                const fromHeight = this._container.get_height();
                this._container.set_height(fromHeight);

                // 2. Swap views while height is frozen — no visual change
                this._historyView.visible = false;
                this._chatView.visible = true;
                this._chatView.opacity = 0;

                // 3. Query the preferred height without releasing the pin
                const containerWidth = this._container.get_width();
                const [, toHeight] = this._chatView.get_preferred_height(containerWidth);
                // Add top-bar height + spacing to get full container target
                const [, topBarHeight] = this._topBar.get_preferred_height(containerWidth);
                const targetHeight = toHeight + topBarHeight + 20; // 10px top + 10px bottom margin

                // 4. Animate height — container stays pinned, only ease changes it
                this._container.ease({
                    height: targetHeight,
                    duration: 200,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    onComplete: () => {
                        this._container.set_height(-1); // Release pin
                        this._chatView.ease({
                            opacity: 255,
                            duration: 150,
                            mode: Clutter.AnimationMode.EASE_IN_QUAD,
                        });
                        this._isHistoryView = false;
                        this._queueInputLayoutUpdate('cursor');
                    },
                });
            },
        });
    }

    /* ── Private ──────────────────────────────────────── */

    private _handleSend(): void {
        if (this._isLoading) return;
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
            this._entry.get_width()
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
        const iconStyle = `color: ${iconColor};`;
        this._settingsBtn.set_style(iconStyle);
        this._expandBtn.set_style(iconStyle);
        this._clearBtn.set_style(iconStyle);
        this._newChatBtn.set_style(iconStyle);
        this._historyBtn.set_style(iconStyle);
        this._backBtn.set_style(iconStyle);

        // Apply theme color to History Title
        const fg = this._themeManager.isDark ? '#ffffff' : '#000000';
        this._historyTitle.set_style(`color: ${fg}; font-weight: bold; font-size: 14px;`);

        this._applyErrorTheme();
        this._applyHistoryTheme();
    }

    private _applyErrorTheme(): void {
        if (!this._errorContainer || !this._errorContainer.visible) return;

        const isDark = this._themeManager.isDark;
        const bg = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        const fg = isDark ? '#ffffff' : '#000000';

        this._errorContainer.set_style(`background-color: ${bg}; color: ${fg};`);
    }

    private _applyHistoryTheme(): void {
        if (!this._historyListBox) return;

        const isDark = this._themeManager.isDark;
        const fg = isDark ? '#ffffff' : '#000000';
        const bg = 'rgba(128, 128, 128, 0.15)'; // Hover background color applied permanently
        const iconColor = isDark ? '#a0a0a0' : '#666666';

        for (const child of this._historyListBox.get_children()) {
            if (child instanceof St.Label) {
                // Empty label
                child.set_style(`color: ${iconColor};`);
            } else if (child instanceof St.BoxLayout) {
                // History item row
                const buttons = child.get_children();
                if (buttons.length >= 2) {
                    const titleBtn = buttons[0] as St.Button;
                    const deleteBtn = buttons[1] as St.Button;
                    titleBtn.set_style(`color: ${fg}; background-color: ${bg};`);
                    deleteBtn.set_style(`color: ${iconColor}; background-color: ${bg};`);
                }
            }
        }
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
