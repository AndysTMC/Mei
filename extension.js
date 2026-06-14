/* extension.js
 *
 * Mei – AI assistant GNOME Shell extension.
 * Minimal chat popup powered by local Ollama.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Soup from 'gi://Soup?version=3.0';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const OLLAMA_URL = 'http://127.0.0.1:11434/api/chat';
const OLLAMA_MODEL = 'gemma4';
const CHAT_WIDTH = 350;

export default class MeiExtension extends Extension {
    enable() {
        this._messages = [];
        this._soupSession = new Soup.Session({ timeout: 300 });
        this._cancellable = null;
        this._glintActive = false;

        /* ── Theme ────────────────────────────────────── */
        this._ifaceSettings = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
        this._isDark = this._ifaceSettings.get_string('color-scheme') === 'prefer-dark';
        this._schemeSignalId = this._ifaceSettings.connect('changed::color-scheme', () => {
            this._isDark = this._ifaceSettings.get_string('color-scheme') === 'prefer-dark';
            this._applyTheme();
        });

        /* ── Panel: "Mei" text label ──────────────────── */
        this._meiLabel = new St.Label({
            text: 'Mei',
            style_class: 'mei-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._button = new St.Button({
            style_class: 'mei-panel-button',
            child: this._meiLabel,
            reactive: true,
            can_focus: true,
            track_hover: true,
        });
        Main.panel._centerBox.insert_child_at_index(this._button, -1);

        // The stop functionality is now integrated into the main button hover.

        /* ── Popup menu ───────────────────────────────── */
        this._menu = new PopupMenu.PopupMenu(this._button, 0.5, St.Side.TOP);
        this._menu.actor.add_style_class_name('mei-popup');
        Main.uiGroup.add_child(this._menu.actor);
        Main.panel.menuManager.addMenu(this._menu);
        this._menu.close();

        this._button.connect('clicked', () => {
            if (this._glintActive) {
                if (this._cancellable) {
                    this._cancellable.cancel();
                }
                this._stopGlint();
                this._menu.open();
                return;
            }
            this._menu.toggle();
        });

        this._button.connect('notify::hover', () => {
            if (this._glintActive) {
                if (this._button.hover) {
                    this._meiLabel.set_text('⏹');
                    this._meiLabel.remove_style_class_name('mei-panel-label');
                    this._meiLabel.add_style_class_name('mei-stop-hover-text');
                    global.display.set_cursor(Clutter.Cursor.HAND1);
                } else {
                    this._meiLabel.set_text('Mei');
                    this._meiLabel.remove_style_class_name('mei-stop-hover-text');
                    this._meiLabel.add_style_class_name('mei-panel-label');
                    global.display.set_cursor(Clutter.Cursor.DEFAULT);
                }
            } else {
                global.display.set_cursor(Clutter.Cursor.DEFAULT);
            }
        });

        /* Auto-focus on open */
        this._menu.connect('open-state-changed', (_menu, isOpen) => {
            if (isOpen) {
                GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                    this._entry?.grab_key_focus();
                    return GLib.SOURCE_REMOVE;
                });
            }
        });

        /* ── Popup content ────────────────────────────── */
        this._menu.box.style = 'padding: 0; margin: 0;';

        let popupItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            can_focus: false,
        });
        popupItem.style = 'padding: 0; margin: 0;';
        this._menu.addMenuItem(popupItem);
        this._popupItem = popupItem;

        this._container = new St.BoxLayout({
            vertical: true,
            style_class: 'mei-container',
            width: CHAT_WIDTH,
        });
        popupItem.add_child(this._container);

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

        /* ── Input ────────────────────────────────────── */
        this._entry = new St.Entry({
            hint_text: 'Ask Mei anything…',
            can_focus: true,
            x_expand: true,
            style_class: 'mei-input',
        });
        
        let ct = this._entry.clutter_text;
        ct.set_single_line_mode(false);
        ct.set_line_wrap(true);
        ct.set_line_wrap_mode(0); // WORD_CHAR
        ct.cursor_visible = true;
        
        ct.connect('key-press-event', (actor, event) => {
            let key = event.get_key_symbol();
            if (key === Clutter.KEY_Return || key === Clutter.KEY_KP_Enter) {
                let state = event.get_state();
                if ((state & Clutter.ModifierType.SHIFT_MASK) === 0) {
                    this._onSend();
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        });

        // Wait to add entry until after copy button

        /* ── Copy button (above input, copies last AI reply) */
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
        this._askBtn.connect('clicked', () => this._onSend());
        this._container.add_child(this._askBtn);

        /* Apply theme */
        this._applyTheme();
    }

    disable() {
        this._stopGlint();
        if (this._cancellable) {
            this._cancellable.cancel();
            this._cancellable = null;
        }
        this._soupSession?.abort();
        this._soupSession = null;
        if (this._menu) {
            Main.panel.menuManager.removeMenu(this._menu);
            Main.uiGroup.remove_child(this._menu.actor);
            this._menu.destroy();
            this._menu = null;
        }
        if (this._button) {
            Main.panel._centerBox.remove_child(this._button);
            this._button.destroy();
            this._button = null;
        }
        // _stopBtn was removed
        if (this._schemeSignalId && this._ifaceSettings) {
            this._ifaceSettings.disconnect(this._schemeSignalId);
            this._schemeSignalId = null;
        }
        this._ifaceSettings = null;
        this._meiLabel = null;
        this._messages = [];
    }

    /* ── Theme ────────────────────────────────────────── */

    _applyTheme() {
        let bg = this._isDark ? '#000000' : '#ffffff';
        let fg = this._isDark ? '#ffffff' : '#000000';
        let hintFg = this._isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)';
        let askBg = this._isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        let askHover = this._isDark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.1)';

        this._menu.box.style =
            `padding: 0; margin: 0; background-color: ${bg}; border-radius: 12px;`;
        if (this._popupItem)
            this._popupItem.style = `padding: 0; margin: 0; background-color: ${bg};`;
        if (this._container)
            this._container.set_style(
                `background-color: ${bg}; color: ${fg}; padding: 10px; border-radius: 12px;`
            );
        if (this._entry)
            this._entry.set_style(
                `color: ${fg}; caret-color: ${fg}; -st-hint-color: ${hintFg};`
            );
        if (this._askBtn)
            this._askBtn.set_style(
                `background-color: ${askBg}; color: ${fg};`
            );
    }

    /* ── Glow / pulse effect on panel label ───────────── */

    _startGlint() {
        this._glintActive = true;
        this._button.add_style_class_name('glow');
        this._pulseGlint();
    }

    _pulseGlint() {
        if (!this._glintActive || !this._meiLabel) return;
        this._meiLabel.ease({
            opacity: 60,
            duration: 700,
            mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
            onComplete: () => {
                if (!this._glintActive || !this._meiLabel) return;
                this._meiLabel.ease({
                    opacity: 255,
                    duration: 700,
                    mode: Clutter.AnimationMode.EASE_IN_OUT_SINE,
                    onComplete: () => this._pulseGlint(),
                });
            },
        });
    }

    _stopGlint() {
        this._glintActive = false;
        if (this._button) this._button.remove_style_class_name('glow');
        if (this._meiLabel) {
            this._meiLabel.set_text('Mei');
            this._meiLabel.remove_style_class_name('mei-stop-hover-text');
            this._meiLabel.add_style_class_name('mei-panel-label');
            this._meiLabel.remove_all_transitions();
            this._meiLabel.opacity = 255;
        }
    }

    /* ── Message ──────────────────────────────────────── */

    _showMessage(role, text) {
        this._messageBox.destroy_all_children();

        let bubble = new St.Label({
            style_class: role === 'user' ? 'mei-bubble-user' : 'mei-bubble-ai',
        });
        bubble.clutter_text.set_line_wrap(true);
        bubble.clutter_text.set_line_wrap_mode(0);
        bubble.clutter_text.set_ellipsize(0);

        if (role === 'assistant') {
            bubble.clutter_text.use_markup = true;
            try {
                bubble.clutter_text.set_markup(this._parseMarkdown(text));
            } catch (e) {
                bubble.clutter_text.use_markup = false;
                bubble.clutter_text.set_text(text);
            }
        } else {
            bubble.clutter_text.set_text(text);
        }

        this._messageBox.add_child(bubble);
        this._scrollView.visible = true;
    }

    /* ── Markdown to Pango Markup ─────────────────────── */

    _parseMarkdown(text) {
        let escaped = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
            
        let codeBlocks = [];
        escaped = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
            codeBlocks.push(code.trim());
            let header = lang ? `<b>[${lang}]</b>\n` : '';
            return `${header}<tt>%%%BLOCK${codeBlocks.length - 1}%%%</tt>`;
        });
        
        let inlineCodes = [];
        escaped = escaped.replace(/`([^`]+)`/g, (match, code) => {
            inlineCodes.push(code);
            return `<tt>%%%INLINE${inlineCodes.length - 1}%%%</tt>`;
        });
        
        // Bullet lists
        escaped = escaped.replace(/^(\s*)[-*]\s+(.*)$/gm, '$1• $2');
        
        // Headers
        escaped = escaped.replace(/^### (.*)$/gm, '<b><span size="large">$1</span></b>');
        escaped = escaped.replace(/^## (.*)$/gm, '<b><span size="x-large">$1</span></b>');
        escaped = escaped.replace(/^# (.*)$/gm, '<b><span size="xx-large">$1</span></b>');
        
        // Blockquotes
        escaped = escaped.replace(/^&gt; (.*)$/gm, '<span color="#888888"><i>| $1</i></span>');
        
        // Images and Links
        escaped = escaped.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '🖼 <a href="$2">$1</a>');
        escaped = escaped.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
        
        // Bold, Italic, Strikethrough
        escaped = escaped.replace(/\*\*([^\n]+?)\*\*/g, '<b>$1</b>');
        escaped = escaped.replace(/\*([^\*\n]+)\*/g, '<i>$1</i>');
        escaped = escaped.replace(/_([^\_\n]+)_/g, '<i>$1</i>');
        escaped = escaped.replace(/~~([^\n]+?)~~/g, '<s>$1</s>');
        
        // Restore code
        escaped = escaped.replace(/%%%BLOCK(\d+)%%%/g, (match, i) => codeBlocks[i]);
        escaped = escaped.replace(/%%%INLINE(\d+)%%%/g, (match, i) => inlineCodes[i]);

        return escaped;
    }

    /* ── Send ─────────────────────────────────────────── */

    _onSend() {
        let text = this._entry.get_text().trim();
        if (!text) return;

        this._entry.set_text('');
        this._messages.push({ role: 'user', content: text });

        // Clear message, close popup, start glint
        this._messageBox.destroy_all_children();
        this._scrollView.visible = false;
        this._menu.close();
        this._startGlint();

        this._fetchOllamaResponse();
    }

    _fetchOllamaResponse() {
        if (!this._soupSession) return;

        let body = JSON.stringify({
            model: OLLAMA_MODEL,
            messages: this._messages,
            stream: false,
        });

        let msg = Soup.Message.new('POST', OLLAMA_URL);
        let bytes = new GLib.Bytes(new TextEncoder().encode(body));
        msg.set_request_body_from_bytes('application/json', bytes);

        this._cancellable = new Gio.Cancellable();

        this._soupSession.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            this._cancellable,
            (_session, result) => {
                try {
                    let respBytes = this._soupSession.send_and_read_finish(result);
                    let json = JSON.parse(
                        new TextDecoder().decode(respBytes.get_data())
                    );
                    let reply =
                        json?.message?.content?.trim() || '(no response)';
                    this._lastReply = reply;
                    this._messages.push({ role: 'assistant', content: reply });

                    // Stop glint, show response, open popup
                    this._stopGlint();
                    this._showMessage('assistant', reply);
                    this._copyBtn.visible = true;
                    this._menu.open();
                } catch (e) {
                    if (!this._cancellable?.is_cancelled()) {
                        this._stopGlint();
                        this._showMessage('assistant', '⚠ Could not reach Ollama.');
                        this._menu.open();
                    }
                    log(`[Mei] Ollama error: ${e.message}`);
                }
            }
        );
    }
}
