/**
 * The chat popup under the panel button. It owns the menu, the two views (chat and history), the
 * compact/expanded mode and the animations between them; the parts inside are their own modules:
 *
 *   ┌ PopupHeader ──── Copy · Clear | New chat · History · Expand · Settings ┐
 *   │ MessageList ──── the latest message (compact) or the conversation       │
 *   │ Composer ─────── message box + Ask/Stop                                 │
 *   │ ErrorPill                                                                │
 *   └──────────────────────────────────────────────────────────────────────────┘
 *   HistoryPanel replaces all of it while the saved chats are listed.
 *
 * Settings aren't part of the popup: the gear opens Mei's Settings window.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import { Logger, Tag } from '../utils/logger.js';
import type { ThemeManager } from '../utils/theme.js';
import { AttachmentChip } from './conversation/attachmentChip.js';
import { Composer } from './conversation/composer.js';
import type { ApprovalScope } from '../runtime/protocol.js';
import type { TimelineItem } from '../runtime/timeline.js';
import type { Answer, CardActions } from './conversation/cards.js';
import { MessageList } from './conversation/messageList.js';
import { listedItems, waitingCard } from './conversation/timelineView.js';
import { ErrorPill } from './popup/errorPill.js';
import { PopupHeader } from './popup/header.js';
import { HistoryPanel, type ChatSummary } from './popup/historyPanel.js';
import { SourceSet } from './sources.js';

export type { ChatSummary } from './popup/historyPanel.js';

const COMPACT_WIDTH = 350;
const EXPANDED_WIDTH = 650;
const FOCUS_AFTER_OPEN_MS = 50;
const FADE_MS = 150;
const RESIZE_MS = 200;

export class ChatPopup {
    /** Called when the user sends a message. */
    onSend: ((text: string) => void) | null = null;
    /** Called when the user stops the reply in progress. */
    onCancel: (() => void) | null = null;
    /** Called when the gear is clicked (the popup has closed itself). */
    onOpenSettings: (() => void) | null = null;
    /** Called when the popup switches between compact and expanded. */
    onToggleExpand: ((isExpanded: boolean) => void) | null = null;
    /** Called whenever the popup opens or closes. */
    onOpenStateChanged: ((isOpen: boolean) => void) | null = null;
    /** Called when the user asks to regenerate the reply at this index. */
    onReload: ((index: number) => void) | null = null;
    /** Called when the user starts a new chat. */
    onNewChat: (() => void) | null = null;
    /** Called when the user asks for the history list. */
    onHistoryRequested: (() => void) | null = null;
    /** Called when a saved chat is chosen from the history list. */
    onLoadChat: ((id: string) => void) | null = null;
    /** Called when a saved chat is deleted from the history list. */
    onDeleteChat: ((id: string) => void) | null = null;
    /** Called when the person allows an action on an approval card. */
    onApprove: ((approvalId: string, scope: ApprovalScope) => void) | null = null;
    /** Called when the person denies an action on an approval card. */
    onDeny: ((approvalId: string) => void) | null = null;
    /** Called when the person answers one of Mei's questions. */
    onAnswer: ((requestId: string, value: Answer) => void) | null = null;
    /** Called when the person keeps a memory waiting for review. */
    onKeepMemory: ((memoryId: string) => void) | null = null;
    /** Called when the person undoes or discards a memory. */
    onForgetMemory: ((memoryId: string) => void) | null = null;
    /** Called when the person drops what "Ask about this" attached. */
    onRemoveAttachment: (() => void) | null = null;

    private readonly _sources = new SourceSet();
    private readonly _menu: PopupMenu.PopupMenu;
    private readonly _item: PopupMenu.PopupBaseMenuItem;
    private readonly _container = new St.BoxLayout({ vertical: true, style_class: 'mei-container', width: COMPACT_WIDTH });
    private readonly _chatView = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true });
    private readonly _content = new St.BoxLayout({ vertical: true, x_expand: true, y_expand: true });
    private readonly _header: PopupHeader;
    private readonly _messages: MessageList;
    private readonly _composer: Composer;
    private readonly _error: ErrorPill;
    private readonly _attachment: AttachmentChip;
    private readonly _history: HistoryPanel;
    private readonly _themeSignal: number;
    private _expanded = false;
    private _loading = false;
    private _showingHistory = false;
    private _focusId = 0;
    private _destroyed = false;

    constructor(anchor: St.Widget, private readonly _theme: ThemeManager) {
        const screenHeight = Main.layoutManager.primaryMonitor?.height ?? 1080;
        const contentMaxHeight = Math.round(screenHeight * 0.60);

        this._menu = new PopupMenu.PopupMenu(anchor, 0.5, St.Side.TOP);
        this._menu.actor.add_style_class_name('mei-popup');
        this._menu.box.add_style_class_name('mei-menu-box');
        Main.uiGroup.add_child(this._menu.actor);
        Main.panel.menuManager.addMenu(this._menu);
        this._menu.close();
        this._menu.connect('open-state-changed', (_menu: PopupMenu.PopupMenu, isOpen: boolean) => {
            this._onOpenStateChanged(isOpen);
            return undefined;
        });
        this._item = new PopupMenu.PopupBaseMenuItem({ reactive: false, can_focus: false });
        this._item.add_style_class_name('mei-popup-item');
        this._item.add_child(this._container);
        this._menu.addMenuItem(this._item);

        this._header = new PopupHeader(this._sources, {
            onClear: () => this._newChat(),
            onNewChat: () => this._newChat(),
            onHistory: () => this.onHistoryRequested?.(),
            onToggleExpand: () => this.toggleExpand(),
            onSettings: () => {
                this._menu.close();
                this.onOpenSettings?.();
            },
        });
        this._messages = new MessageList(this._sources, contentMaxHeight, {
            animateHeight: change => this._animateHeight(change),
            isDark: () => this._theme.isDark,
            onReload: index => this.onReload?.(index),
        });
        this._composer = new Composer(this._sources, Math.round(screenHeight * 0.20), {
            onSend: text => this.onSend?.(text),
            onStop: () => this.onCancel?.(),
        });
        this._error = new ErrorPill(this._sources);
        this._attachment = new AttachmentChip(() => this.onRemoveAttachment?.());
        this._history = new HistoryPanel(this._sources, contentMaxHeight, {
            onBack: () => this.hideHistoryList(),
            onLoadChat: id => this.onLoadChat?.(id),
            onDeleteChat: id => this.onDeleteChat?.(id),
        });

        for (const part of [this._messages.actor, this._attachment.actor, this._composer.actor, this._error.actor])
            this._content.add_child(part);
        this._chatView.add_child(this._header.actor);
        this._chatView.add_child(this._content);
        this._container.add_child(this._chatView);
        this._container.add_child(this._history.actor);

        this._applyTheme();
        this._themeSignal = this._theme.onThemeChanged(() => this._applyTheme());
    }

    // ── State ────────────────────────────────────────────────────────────────

    get isExpanded(): boolean {
        return this._expanded;
    }

    get isOpen(): boolean {
        return this._menu.isOpen;
    }

    get isShowingHistory(): boolean {
        return this._showingHistory;
    }

    /** Root of the popup's content. Read by the dev-build test hooks only (src/runtime/devHooks.ts). */
    get contentActor(): St.BoxLayout {
        return this._container;
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

    // ── Conversation ─────────────────────────────────────────────────────────

    /** Compact mode: show only this message. */
    showMessage(role: 'user' | 'assistant', text: string): void {
        this._messages.showMessage(role, text);
        this._header.setCopyText(this._expanded ? '' : this._messages.lastReply);
    }

    /** Expanded mode: show the whole conversation, with the agent's cards in place. */
    showTimeline(items: TimelineItem[], fadeLastAssistant = false): void {
        this._messages.showItems(listedItems(items, this._cards()), fadeLastAssistant);
        this._header.setCopyText('');
    }

    /** Compact mode: show the card the task waits on. Returns false if there is none. */
    showWaitingCard(items: TimelineItem[]): boolean {
        const build = waitingCard(items, this._cards());
        if (!build) return false;
        this._messages.showCard(build);
        this._header.setCopyText('');
        return true;
    }

    private _cards(): CardActions {
        return {
            onApprove: (id, scope) => this.onApprove?.(id, scope),
            onDeny: id => this.onDeny?.(id),
            onAnswer: (id, value) => this.onAnswer?.(id, value),
            onKeepMemory: id => this.onKeepMemory?.(id),
            onForgetMemory: id => this.onForgetMemory?.(id),
        };
    }

    clearMessages(): void {
        this._animateHeight(() => {
            this._messages.clear();
            this._header.setCopyText('');
            this._header.resetCopyState();
        });
    }

    setLoading(loading: boolean): void {
        if (this._loading === loading) return;
        this._loading = loading;
        this._composer.setState(loading, this._expanded);
        this._messages.setLoading(loading);
    }

    showStreamingResponse(content: string, thinking: string): void {
        this._messages.showStreaming(content, thinking);
    }

    /** Show what the next message will carry ("About: …"), or nothing. */
    showAttachment(label: string | null): void {
        this._animateHeight(() => this._attachment.show(label));
    }

    showError(message: string): void {
        this._error.show(message, this._theme.isDark);
    }

    hideError(): void {
        this._error.hide();
    }

    // ── History list ─────────────────────────────────────────────────────────

    showHistoryList(items: ChatSummary[]): void {
        this._history.show(items);
        this._transitionTo(this._history.actor, () => {
            this._showingHistory = true;
        });
    }

    /** Redraw the history list in place, if it is showing (a task started or finished). */
    refreshHistoryList(items: ChatSummary[]): void {
        if (this._showingHistory) this._history.show(items);
    }

    hideHistoryList(): void {
        if (!this._showingHistory) return;
        this._transitionTo(this._chatView, () => {
            this._showingHistory = false;
            this._composer.queueLayout('cursor');
        }, this._width());
    }

    // ── Compact / expanded ───────────────────────────────────────────────────

    /** Fade the content out, resize, let the controller re-render for the new mode, fade back in. */
    toggleExpand(): void {
        const fromWidth = Math.max(1, this._container.get_width() || this._width());
        const fromHeight = Math.max(1, this._container.get_height() || this._heightFor(this._activeView(), fromWidth));
        this._expanded = !this._expanded;
        if (this._expanded) this._container.add_style_class_name('expanded');
        else this._container.remove_style_class_name('expanded');
        this._composer.setState(this._loading, this._expanded);
        this._messages.setExpanded(this._expanded);
        this._header.showModeButtons(this._expanded);
        if (!this._expanded && this._showingHistory) {
            // History is an expanded-mode view: leaving expanded mode goes straight back to chat.
            this._chatView.visible = true;
            this._chatView.opacity = 255;
            this._history.actor.visible = false;
            this._showingHistory = false;
        }
        this._content.ease({
            opacity: 0,
            duration: FADE_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;
                this._header.showExpandState(this._expanded);
                this.onToggleExpand?.(this._expanded); // the controller re-renders for the new mode
                this._container.set_width(fromWidth);
                this._container.set_height(fromHeight);
                this._sources.idle(() => {
                    this._resize(this._activeView(), this._width(), () => {
                        this._composer.queueLayout('cursor');
                        this._content.ease({ opacity: 255, duration: FADE_MS, mode: Clutter.AnimationMode.EASE_IN_QUAD });
                    });
                    return GLib.SOURCE_REMOVE;
                }, GLib.PRIORITY_DEFAULT);
            },
        });
    }

    // ── Layout and animation ─────────────────────────────────────────────────

    private _width(): number {
        return this._expanded ? EXPANDED_WIDTH : COMPACT_WIDTH;
    }

    private _activeView(): St.BoxLayout {
        return this._showingHistory ? this._history.actor : this._chatView;
    }

    private _heightFor(view: St.BoxLayout, width: number): number {
        const [, natural] = view.get_preferred_height(width);
        return Math.max(1, Math.ceil(natural));
    }

    /** Animate the container to `view`'s size at `width`, then let it size itself again. */
    private _resize(view: St.BoxLayout, width: number, onComplete: () => void): void {
        this._container.ease({
            width,
            height: this._heightFor(view, width),
            duration: RESIZE_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;
                this._container.set_height(-1);
                onComplete();
            },
        });
    }

    /** Run `change`, then ease the popup's height to fit the result. */
    private _animateHeight(change: () => void): void {
        if (this._destroyed) return;
        const width = Math.max(1, this._container.get_width() || COMPACT_WIDTH);
        const current = this._container.get_height();
        this._container.set_height(Math.max(1, current > 0 ? current : this._heightFor(this._activeView(), width)));
        change();
        this._sources.idle(() => {
            this._resize(this._activeView(), width, () => {
                if (!this._showingHistory) this._composer.queueLayout('cursor');
            });
            return GLib.SOURCE_REMOVE;
        }, GLib.PRIORITY_DEFAULT);
    }

    /** Fade out the current view, resize to `target`, fade it in. */
    private _transitionTo(target: St.BoxLayout, onComplete: () => void, width = this._container.get_width() || COMPACT_WIDTH): void {
        const current = this._activeView();
        const pinSize = (view: St.BoxLayout) => {
            this._container.set_width(Math.max(1, this._container.get_width() || width));
            this._container.set_height(Math.max(1, this._container.get_height() || this._heightFor(view, width)));
        };
        if (current === target) {
            pinSize(target);
            this._resize(target, width, onComplete);
            return;
        }
        current.ease({
            opacity: 0,
            duration: FADE_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;
                pinSize(current);
                current.visible = false;
                target.visible = true;
                target.opacity = 0;
                this._resize(target, width, () => {
                    target.ease({ opacity: 255, duration: FADE_MS, mode: Clutter.AnimationMode.EASE_IN_QUAD });
                    onComplete();
                });
            },
        });
    }

    // ── Events and theme ─────────────────────────────────────────────────────

    private _onOpenStateChanged(isOpen: boolean): void {
        Logger.debug(Tag.UI, `Popup ${isOpen ? 'opened' : 'closed'}`);
        this._focusId = this._sources.remove(this._focusId);
        if (isOpen) {
            // Focus after the open animation has given the entry its allocation.
            this._focusId = this._sources.timeout(FOCUS_AFTER_OPEN_MS, () => {
                this._focusId = 0;
                if (!this._showingHistory) this._composer.focus();
                return GLib.SOURCE_REMOVE;
            });
        } else {
            this._composer.stopBlink();
            this._header.resetCopyState();
        }
        this.onOpenStateChanged?.(isOpen);
    }

    private _newChat(): void {
        if (this._messages.hasMessages) this.onNewChat?.();
    }

    private _applyTheme(): void {
        this._theme.applyTheme({
            menuBox: this._menu.box,
            popupItem: this._item,
            container: this._container,
            entry: this._composer.entry,
            askBtn: this._composer.askButton,
            copyBtn: this._header.copyButton,
        });
        const isDark = this._theme.isDark;
        this._header.applyTheme(isDark);
        this._history.applyTheme(isDark);
        this._error.applyTheme(isDark);
        this._messages.applyTheme();
    }

    destroy(): void {
        if (this._destroyed) return;
        this._messages.destroy();
        this._destroyed = true;
        this._theme.disconnect(this._themeSignal);
        this._sources.destroy();
        for (const actor of [this._container, this._content, this._chatView, this._history.actor]) actor.remove_all_transitions();
        this._composer.stopBlink();
        // Close first: removing a menu that is still open leaves the panel's menu manager holding
        // it, and the next popup to open touches the destroyed BoxPointer.
        if (this._menu.isOpen) this._menu.close(BoxPointer.PopupAnimation.NONE);
        Main.panel.menuManager.removeMenu(this._menu);
        Main.uiGroup.remove_child(this._menu.actor);
        this._menu.destroy();
    }
}
