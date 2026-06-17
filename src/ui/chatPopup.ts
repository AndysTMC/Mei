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
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import { parseMarkdown } from './markdown.js';
import { ThemeManager, type ThemedWidgets } from '../utils/theme.js';

const CHAT_WIDTH = 350;

export class ChatPopup {
    private _menu: PopupMenu.PopupMenu;
    private _container: St.BoxLayout;
    private _scrollView: St.ScrollView;
    private _messageBox: St.BoxLayout;
    private _entry: St.Entry;
    private _askBtn: St.Button;
    private _copyBtn: St.Button;
    private _settingsBtn: St.Button;
    private _popupItem: PopupMenu.PopupBaseMenuItem;
    private _themeManager: ThemeManager;
    private _lastReply: string | null = null;

    /** Called when the user sends a message. */
    onSend: ((text: string) => void) | null = null;

    /** Called when the settings icon is clicked. */
    onOpenSettings: (() => void) | null = null;

    constructor(anchor: St.Widget, themeManager: ThemeManager) {
        this._themeManager = themeManager;

        /* ── Popup menu ───────────────────────────────── */
        this._menu = new PopupMenu.PopupMenu(anchor, 0.5, St.Side.TOP);
        this._menu.actor.add_style_class_name('mei-popup');
        Main.uiGroup.add_child(this._menu.actor);
        Main.panel.menuManager.addMenu(this._menu);
        this._menu.close();

        /* Auto-focus input on open */
        (this._menu as any).connect('open-state-changed', (_menu: any, isOpen: boolean) => {
            if (isOpen) {
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                    this._entry?.grab_key_focus();
                    return GLib.SOURCE_REMOVE;
                });
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

        /* ── Settings icon (top-right) ────────────────── */
        const topBar = new St.BoxLayout({
            x_expand: true,
            x_align: Clutter.ActorAlign.END,
        });

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

        /* ── Message area (scrollable, max 400px) ─────── */
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

        this._messageBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
        });
        this._scrollView.set_child(this._messageBox);
        this._container.add_child(this._scrollView);

        /* ── Copy button ──────────────────────────────── */
        this._copyBtn = new St.Button({
            label: 'Copy',
            style_class: 'mei-ask-btn',
            can_focus: true,
            x_expand: true,
            reactive: true,
            track_hover: true,
            visible: false,
        });
        this._copyBtn.set_style('background-color: #ffffff; color: #000000;');
        this._copyBtn.connect('clicked', () => {
            if (this._lastReply) {
                St.Clipboard.get_default().set_text(
                    St.ClipboardType.CLIPBOARD,
                    this._lastReply
                );
            }
        });
        this._container.add_child(this._copyBtn);

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
        this._container.add_child(this._entry);

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
        this._container.add_child(this._askBtn);

        /* ── Apply theme ──────────────────────────────── */
        this._applyTheme();
        this._themeManager.onThemeChanged(() => this._applyTheme());
    }

    /* ── Public API ───────────────────────────────────── */

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

        const bubble = new St.Label({
            style_class: role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai',
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
            this._lastReply = text;
            this._copyBtn.visible = true;
        } else {
            bubble.clutter_text.set_text(text);
        }

        this._messageBox.add_child(bubble);
        this._scrollView.visible = true;
    }

    /** Clear the message area and hide it. */
    clearMessages(): void {
        this._messageBox.destroy_all_children();
        this._scrollView.visible = false;
    }

    /* ── Private ──────────────────────────────────────── */

    private _handleSend(): void {
        const text = this._entry.get_text().trim();
        if (!text) return;
        this._entry.set_text('');
        this.onSend?.(text);
    }

    private _applyTheme(): void {
        const widgets: ThemedWidgets = {
            menuBox: this._menu.box,
            popupItem: this._popupItem as unknown as St.Widget,
            container: this._container,
            entry: this._entry,
            askBtn: this._askBtn,
        };
        this._themeManager.applyTheme(widgets);

        // Settings icon inherits text color
        const fg = this._themeManager.isDark ? '#ffffff' : '#000000';
        this._settingsBtn.set_style(
            `background-color: transparent; border: none; padding: 2px; color: ${fg};`
        );
    }

    /* ── Cleanup ──────────────────────────────────────── */

    destroy(): void {
        if (this._menu) {
            Main.panel.menuManager.removeMenu(this._menu);
            Main.uiGroup.remove_child(this._menu.actor);
            this._menu.destroy();
        }
    }
}
