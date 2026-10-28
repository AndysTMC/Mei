/**
 * The chat popup under the panel button. It owns the menu, the two views (chat and history), the
 * compact/expanded mode and the animations between them; the parts inside are their own modules:
 *
 *   ┌ PopupHeader ──────── Clear | New chat · History · Expand · Settings ┐
 *   │ MessageList ──────── the latest reply (compact) or the conversation  │
 *   │ InteractionPanel ─── what Mei waits for, in place of the composer    │
 *   │ Composer ─────────── message box + Ask/Stop · mic · voice            │
 *   │ ErrorPill ────────── a notice: Close, and Set up or Copy             │
 *   └───────────────────────────────────────────────────────────────────────┘
 *   HistoryPanel replaces all of it while the saved chats are listed, and LargePage while it shows
 *   what Mei is doing or an attachment (decision 0034).
 *
 * Settings aren't part of the popup: the gear opens Mei's Settings window.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as BoxPointer from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import { Logger, Tag } from '../utils/logger.js';
import { iconButton } from './effects.js';
import type { ThemeManager } from '../utils/theme.js';
import { AttachmentChip } from './conversation/attachmentChip.js';
import { voiceLine, type VoiceView } from '../runtime/voice.js';
import { Composer } from './conversation/composer.js';
import { attachmentLabel, attachmentTitle, canOpen } from '../runtime/attachment.js';
import type { ApprovalScope, Attachment, Picture } from '../runtime/protocol.js';
import type { Interaction, TimelineItem, WorkView } from '../runtime/timeline.js';
import type { Answer, CardActions } from './conversation/cards.js';
import { InteractionPanel } from './conversation/interaction.js';
import { MessageList } from './conversation/messageList.js';
import { listedItems } from './conversation/timelineView.js';
import { ErrorPill, type NoticeAction } from './popup/errorPill.js';
import { PopupHeader } from './popup/header.js';
import { HistoryPanel, type ChatSummary } from './popup/historyPanel.js';
import { LargePage, type PageContent } from './popup/largePage.js';
import { largePageSize } from './popup/pageSize.js';
import { WorkPage } from './popup/workPage.js';
import { SourceSet } from './sources.js';
import { loadPicture } from './viewers/common.js';
import { fileViewer, textViewer, type PdfPages, type ViewerHost } from './viewers/index.js';

export type { ChatSummary } from './popup/historyPanel.js';

const COMPACT_WIDTH = 350;
const EXPANDED_WIDTH = 650;
const FOCUS_AFTER_OPEN_MS = 50;
const FADE_MS = 150;
const RESIZE_MS = 200;
/** The picture at the top of a task's steps, in CSS pixels. */
const THUMBNAIL = { width: 160, height: 100 };

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
    /** A reply's Read aloud: read it out, or stop. */
    onReadAloud: ((messageId: string, text: string) => void) | null = null;
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
    /** Called when the person declines and tells Mei what to do instead. */
    onDenyWith: ((approvalId: string, text: string) => void) | null = null;
    /** Called when the person answers one of Mei's questions. */
    onAnswer: ((requestId: string, value: Answer) => void) | null = null;
    onResume: ((taskId: string) => void) | null = null;
    onStopTask: ((taskId: string) => void) | null = null;
    /** Called when the person keeps a memory waiting for review. */
    onKeepMemory: ((memoryId: string) => void) | null = null;
    /** Called when the person undoes or discards a memory. */
    onForgetMemory: ((memoryId: string) => void) | null = null;
    /** Called when the person presses the mic (dictate, or done). */
    onDictate: (() => void) | null = null;
    /** Called when the person presses voice (talk with Mei, or stop). */
    onVoice: (() => void) | null = null;
    /** Called when the person drops what "Ask about this" attached. */
    onRemoveAttachment: (() => void) | null = null;
    /** Called when the person clicks the picture at the top of a task's steps. */
    onOpenWork: ((taskId: string) => void) | null = null;
    /** The work page's Pause: hold the task before its next act. (Go on is `onResume`.) */
    onPauseTask: ((taskId: string) => void) | null = null;
    /** The work page's Stop: the kill switch's path, and this task. */
    onStopWork: ((taskId: string) => void) | null = null;
    /** The newest picture of the screen a task kept (the thumbnail's), from the runtime. */
    findPicture: ((taskId: string, actionId: string) => Promise<Picture | null>) | null = null;
    /** The runtime's PDF pages, for the PDF viewer; null: PDFs show as files. */
    pdf: PdfPages | null = null;

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
    private readonly _interaction: InteractionPanel;
    private readonly _history: HistoryPanel;
    private readonly _page: LargePage;
    private readonly _themeSignal: number;
    private _expanded = false;
    private _voiceReady = false;
    private _loading = false;
    private _showingHistory = false;
    private _showingPage = false;
    private _closingPage = false;
    /** What the chip shows, opened when it is clicked. */
    private _attached: Attachment | null = null;
    private _focusId = 0;
    private _destroyed = false;

    constructor(anchor: St.Widget, private readonly _theme: ThemeManager, extensionPath: string) {
        const screenHeight = Main.layoutManager.primaryMonitor?.height ?? 1080;
        const contentMaxHeight = Math.round(screenHeight * 0.60);

        this._menu = new PopupMenu.PopupMenu(anchor, 0.5, St.Side.TOP);
        this._menu.actor.add_style_class_name('mei-popup');
        this._menu.box.add_style_class_name('mei-menu-box');
        Main.uiGroup.add_child(this._menu.actor);
        // Escape on the large page goes back to the chat; anywhere else it closes the popup as before.
        // Connected before addMenu: the menu manager closes the menu on Escape from the same signal,
        // and the first handler to stop it wins.
        this._menu.actor.connect('captured-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
            if (!this._showingPage || event.type() !== Clutter.EventType.KEY_PRESS
                || event.get_key_symbol() !== Clutter.KEY_Escape) return Clutter.EVENT_PROPAGATE;
            this.closePage();
            return Clutter.EVENT_STOP;
        });
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
            canReadAloud: () => this._voiceReady,
            onReadAloud: (messageId, text) => this.onReadAloud?.(messageId, text),
            onOpenAttachment: attachment => this.openAttachment(attachment),
        });
        this._composer = new Composer(this._sources, Math.round(screenHeight * 0.20), {
            onSend: text => this.onSend?.(text),
            onStop: () => this.onCancel?.(),
            onDictate: () => this.onDictate?.(),
            onVoice: () => this.onVoice?.(),
        }, Gio.FileIcon.new(Gio.File.new_for_path(`${extensionPath}/icons/mei-voice-symbolic.svg`)));
        this._error = new ErrorPill(this._sources);
        this._attachment = new AttachmentChip(() => this.onRemoveAttachment?.(), () => {
            if (this._attached) this.openAttachment(this._attached);
        });
        this._interaction = new InteractionPanel(this._cards());
        this._history = new HistoryPanel(this._sources, contentMaxHeight, {
            onBack: () => this.hideHistoryList(),
            onLoadChat: id => this.onLoadChat?.(id),
            onDeleteChat: id => this.onDeleteChat?.(id),
        });
        this._page = new LargePage(() => this.closePage());

        for (const part of [this._messages.actor, this._attachment.actor, this._interaction.actor, this._composer.actor,
            this._error.actor])
            this._content.add_child(part);
        this._chatView.add_child(this._header.actor);
        this._chatView.add_child(this._content);
        this._container.add_child(this._chatView);
        this._container.add_child(this._history.actor);
        this._container.add_child(this._page.actor);

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

    get isShowingPage(): boolean {
        return this._showingPage;
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

    /** The conversation (expanded) or its latest reply (compact), each reply with its details. */
    showTimeline(items: TimelineItem[], fadeLastAssistant = false): void {
        this._messages.showItems(listedItems(items, this._cards(), (taskId, actionId) => this._thumbnail(taskId, actionId)),
            fadeLastAssistant);
        this._header.setCopyText('');
    }

    /** What Mei waits for takes the composer's place; nothing: the composer is back. */
    showInteraction(interaction: Interaction | null): void {
        const wasShowing = this._interaction.actor.visible;
        if (!interaction && !wasShowing) return;
        this._animateHeight(() => {
            const shown = this._interaction.show(interaction);
            this._composer.actor.visible = !shown;
        });
        // A new card while the popup is open gets the keyboard; one that arrived while it was closed gets
        // it when the popup opens (below), rather than the hidden message box.
        if (interaction && this._interaction.changed && this.isOpen) this._interaction.focus();
    }

    /** The answer didn't reach Mei: the interaction can be answered again. */
    retryInteraction(): void {
        this._interaction.retry();
    }

    private _cards(): CardActions {
        return {
            onApprove: (id, scope) => this.onApprove?.(id, scope),
            onDeny: id => this.onDeny?.(id),
            onDenyWith: (id, text) => this.onDenyWith?.(id, text),
            onAnswer: (id, value) => this.onAnswer?.(id, value),
            onResume: id => this.onResume?.(id),
            onStopTask: id => this.onStopTask?.(id),
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

    /** Voice in the composer: the mic and voice buttons, and while talking, what it's doing and heard. */
    showVoice(view: VoiceView): void {
        const talking = ['listening', 'thinking', 'speaking', 'paused'].includes(view.state) && !view.dictating;
        const dictating = view.dictating && ['listening', 'paused'].includes(view.state);
        const mode = dictating ? 'dictating' : talking ? 'talking' : 'idle';
        this._voiceReady = !['off', 'unavailable', 'starting'].includes(view.state);
        this._composer.setVoice({ available: view.state !== 'off', mode, status: voiceLine(view).status,
            transcript: talking && view.state !== 'speaking' ? view.transcript : '' });
    }

    /** The reply Read aloud is reading, or none: its button shows Stop. */
    setReading(messageId: string | null): void {
        this._messages.setReading(messageId);
    }

    /** The message box's sizes (for the dev hooks' tests). */
    get inputSizes(): Record<string, number> {
        return this._composer.debugSizes();
    }

    /** What's in the message box now (for the dev hooks' tests). */
    get inputText(): string {
        return this._composer.entry.get_text();
    }

    /** A message that couldn't be sent goes back in the box, unless they've started another. */
    restoreDraft(text: string): void {
        this._composer.restoreDraft(text);
    }

    /** Dictated words so far (`final`: an utterance done), into the message box. */
    dictate(text: string, final: boolean, raw = text): void {
        this._composer.dictate(text, final, raw);
    }

    /** Show what the next message will carry ("About: …"), or nothing. */
    showAttachment(attachment: Attachment | null): void {
        this._attached = attachment;
        this._animateHeight(() => this._attachment.show(attachment ? attachmentLabel(attachment) : null,
            attachment !== null && canOpen(attachment)));
    }

    /** A notice: closable; with an action when there's a way forward; `source` lets its cause clear it. */
    showError(message: string, options: { action?: NoticeAction; source?: string } = {}): void {
        this._error.show(message, this._theme.isDark, options);
    }

    hideError(source?: string): void {
        if (source === undefined || this._error.source === source) this._error.hide();
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

    // ── Large page (decision 0034) ───────────────────────────────────────────

    /** An attachment on the large page: its first file (the others a step away), or its text. */
    openAttachment(attachment: Attachment, index = 0): void {
        if (!canOpen(attachment)) return;
        if (attachment.kind !== 'files') {
            this.showPage(textViewer(attachmentTitle(attachment), attachment.text, this._viewerHost()));
            return;
        }
        const paths = attachment.paths ?? [];
        const at = Math.max(0, Math.min(index, paths.length - 1));
        const content = fileViewer(paths[at], this._viewerHost());
        if (paths.length > 1) content.actions.unshift(...this._stepper(attachment, at, paths.length));
        this.showPage(content);
    }

    /** A file on the large page (the dev hooks' tests open each kind this way). */
    openFile(path: string): void {
        this.showPage(fileViewer(path, this._viewerHost()));
    }

    /** What Mei is doing in this task, on the large page; again while it shows: the newer state. */
    showWork(view: WorkView): void {
        const work = this._work();
        if (work && work.taskId === view.taskId) {
            work.update(view);
            return;
        }
        this.showPage(new WorkPage(view, this._pageBodySize(), {
            onPause: id => this.onPauseTask?.(id),
            onGoOn: id => this.onResume?.(id),
            onStop: id => this.onStopWork?.(id),
        }));
    }

    showWorkPicture(picture: Picture): void {
        this._work()?.showPicture(picture);
    }

    /** The task the work page shows, if it is showing. */
    get workTaskId(): string | null {
        return this._work()?.taskId ?? null;
    }

    get workPicture(): string | null {
        return this._work()?.shownPicture ?? null;
    }

    /** The large page's state and size, and the popup's (for the dev hooks' tests). */
    get pageState(): Record<string, unknown> {
        const content = this._page.content as (PageContent & { mode?: string; debugState?: unknown }) | null;
        const [x, y] = this._page.actor.get_transformed_position();
        return {
            open: this._showingPage, title: this._page.content ? this._titleText() : '', mode: content?.mode ?? null,
            work: content instanceof WorkPage ? content.debugState : null,
            page: { x: Math.round(x), y: Math.round(y), width: this._page.actor.width, height: this._page.actor.height },
            popup: { width: this._container.width, height: this._container.height },
            expected: this._page.size,
        };
    }

    /** Show `content` on the large page, growing into it; already there: in place. */
    showPage(content: PageContent): void {
        this._page.show(content);
        if (this._showingPage) return;
        this._page.setSize(this._pageSize());
        this._transitionTo(this._page.actor, () => {
            this._showingPage = true;
            this._showingHistory = false; // opened over History (a test hook): Back goes to the chat
            this._page.focus();
        }, this._page.size.width, () => this._placeUnderTopBar(true));
    }

    /** Back to the chat, as History goes back: fade, resize, fade in. */
    closePage(): void {
        if (!this._showingPage || this._closingPage) return;
        this._closingPage = true;
        this._transitionTo(this._chatView, () => {
            this._showingPage = false;
            this._closingPage = false;
            this._page.clear();
            this._composer.queueLayout('cursor');
            this._composer.focus();
        }, this._width(), () => this._placeUnderTopBar(false));
    }

    /** The page hangs centred under the whole top bar; the chat under Mei's button, as the menu opens it. */
    private _placeUnderTopBar(centred: boolean): void {
        this._menu._boxPointer.setPosition(centred ? Main.panel : this._menu.sourceActor, 0.5);
    }

    /** The work page, from the moment it is shown (its picture loads while the page grows) until it closes. */
    private _work(): WorkPage | null {
        const content = this._page.content;
        return !this._closingPage && content instanceof WorkPage ? content : null;
    }

    private _titleText(): string {
        const walk = (actor: Clutter.Actor): string => {
            if (actor instanceof St.Label && actor.has_style_class_name('mei-page-title')) return actor.text;
            for (const child of actor.get_children()) {
                const found = walk(child);
                if (found) return found;
            }
            return '';
        };
        return walk(this._page.actor);
    }

    private _pageSize() {
        const index = Main.layoutManager.primaryIndex;
        const monitor = Main.layoutManager.primaryMonitor ?? { width: 1920, height: 1080 };
        const area = Main.layoutManager.getWorkAreaForMonitor(index);
        return largePageSize(monitor, area);
    }

    private _pageBodySize() {
        if (!this._showingPage) this._page.setSize(this._pageSize());
        return this._page.bodySize;
    }

    private _viewerHost(): ViewerHost {
        const page = this._page;
        if (!this._showingPage) page.setSize(this._pageSize());
        return {
            bodySize: page.bodySize,
            pdf: this.pdf,
            setTitle: title => page.setTitle(title),
            replace: content => page.show(content),
            onLeft: () => this._menu.close(),
        };
    }

    /** Previous and next, for an attachment of several files. */
    private _stepper(attachment: Attachment, at: number, count: number): St.Widget[] {
        const step = (icon: string, name: string, to: number) => {
            const button = iconButton(icon, name);
            button.reactive = to >= 0 && to < count;
            button.connect('clicked', () => this.openAttachment(attachment, to));
            return button;
        };
        const where = new St.Label({ text: `${at + 1} of ${count}`, style_class: 'mei-card-muted', y_align: Clutter.ActorAlign.CENTER });
        return [step('go-previous-symbolic', 'Previous file', at - 1), where, step('go-next-symbolic', 'Next file', at + 1)];
    }

    /** The latest picture of the screen, small, at the top of a task's steps; a click opens the work page. */
    private _thumbnail(taskId: string, actionId: string): St.Widget {
        const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
        const size = { width: THUMBNAIL.width * scale, height: THUMBNAIL.height * scale };
        const button = new St.Button({ style_class: 'mei-work-thumbnail', can_focus: true, reactive: true, track_hover: true,
            accessible_name: 'See what Mei is doing', x_align: Clutter.ActorAlign.START });
        button.set_size(size.width, size.height);
        button.connect('clicked', () => this.onOpenWork?.(taskId));
        // The list may be redrawn (and this button destroyed) before the lookup answers.
        let gone = false;
        button.connect('destroy', () => {
            gone = true;
        });
        this.findPicture?.(taskId, actionId).then(picture => {
            if (picture && !gone) button.set_child(loadPicture(picture.path, size, picture));
        }).catch((e: Error) => Logger.debug(Tag.UI, `No thumbnail: ${e.message}`));
        return button;
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
        if (this._showingPage) {
            // The page has no mode of its own: changing modes goes back to the chat at once.
            this._showingPage = false;
            this._closingPage = false;
            this._placeUnderTopBar(false);
            this._page.actor.visible = false;
            this._page.clear();
            this._chatView.visible = true;
            this._chatView.opacity = 255;
        }
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
        if (this._showingPage) return this._page.actor;
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
                if (!this._showingHistory && !this._showingPage) this._composer.queueLayout('cursor');
            });
            return GLib.SOURCE_REMOVE;
        }, GLib.PRIORITY_DEFAULT);
    }

    /** Fade out the current view, resize to `target`, fade it in. `onSwap`: once the old view is gone. */
    private _transitionTo(target: St.BoxLayout, onComplete: () => void, width = this._container.get_width() || COMPACT_WIDTH,
        onSwap?: () => void): void {
        const current = this._activeView();
        const pinSize = (view: St.BoxLayout) => {
            this._container.set_width(Math.max(1, this._container.get_width() || width));
            this._container.set_height(Math.max(1, this._container.get_height() || this._heightFor(view, width)));
        };
        if (current === target) {
            pinSize(target);
            onSwap?.();
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
                onSwap?.();
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
            if (this._showingPage) this._placeUnderTopBar(true); // opening put it back under the button
            // Focus after the open animation has given the entry its allocation.
            this._focusId = this._sources.timeout(FOCUS_AFTER_OPEN_MS, () => {
                this._focusId = 0;
                if (this._showingPage) this._page.focus();
                else if (this._showingHistory) return GLib.SOURCE_REMOVE;
                else if (this._interaction.actor.visible) this._interaction.focus();
                else this._composer.focus();
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
        // The stylesheet's one emphasis, a primary button in the text's color, needs the mode.
        this._container.remove_style_class_name(isDark ? 'mei-light' : 'mei-dark');
        this._container.add_style_class_name(isDark ? 'mei-dark' : 'mei-light');
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
        for (const actor of [this._container, this._content, this._chatView, this._history.actor, this._page.actor])
            actor.remove_all_transitions();
        this._page.clear();
        this._composer.stopBlink();
        // Close first: removing a menu that is still open leaves the panel's menu manager holding
        // it, and the next popup to open touches the destroyed BoxPointer.
        if (this._menu.isOpen) this._menu.close(BoxPointer.PopupAnimation.NONE);
        Main.panel.menuManager.removeMenu(this._menu);
        Main.uiGroup.remove_child(this._menu.actor);
        this._menu.destroy();
    }
}
