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
 * SPDX-License-Identifier: GPL-3.0-only
 */

import St from 'gi://St';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Atk from 'gi://Atk';
import Gio from 'gi://Gio';
import Soup from 'gi://Soup?version=3.0';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Animation from 'resource:///org/gnome/shell/ui/animation.js';

import { createMessageActor, formatThinkingPreview, type MessageRole, type RenderedMessageActor } from './messageRenderer.js';
import { createMessageInfoPanel, styleMessageInfoPanel } from './messageInfoPanel.js';
import { renderHistoryList, styleHistoryList, type ChatSummary } from './historyListView.js';
import { PopupLogPanel } from './popupLogPanel.js';
import {
    addSettingsEntryRow,
    addSettingsNavRow,
    addSettingsSection,
    addSettingsSegmentRow,
    addSettingsStatusRow,
    createSettingsRow,
} from './popupSettingsWidgets.js';
import { ThemeManager, type ThemedWidgets } from '../utils/theme.js';
import { Logger, Tag } from '../utils/logger.js';
import {
    DEEPSEEK_REASONING_EFFORT_LABELS,
    DEEPSEEK_THINKING_LABELS,
    getDeepSeekReasoningEffort,
    getDeepSeekThinking,
    getOpenCodeMode,
    getProviderIdsForType,
    getProviderLabel,
    getProviderType,
    OPEN_CODE_MODE_LABELS,
    PROVIDER_TYPE_IDS,
    PROVIDER_TYPE_LABELS,
    type DeepSeekReasoningEffort,
    type DeepSeekThinking,
    type OpenCodeMode,
    type ProviderType,
} from '../providers/catalog.js';
import { fetchProviderModels } from '../providers/modelList.js';
import type { ChatMessageMetadata, ProviderId } from '../providers/types.js';
import {
    createEmptyProviderConfig,
    isApiKeyPlaceholderLike,
    mergeMigratedApiKeyConfigs,
    parseProviderConfigs,
    type ProviderConfigKey,
    type StoredProviderConfig,
} from '../providers/configStore.js';
import {
    migratePlaintextApiKeys,
    resolveStoredProviderConfig,
    updateStoredProviderApiKey,
} from '../providers/apiKeys.js';

const CHAT_WIDTH = 350;
const SETTINGS_WIDTH = 650;
const SETTINGS_HEIGHT = 650;
const SETTINGS_SCROLL_MAX_HEIGHT = SETTINGS_HEIGHT - 52;
const INPUT_MIN_HEIGHT = 22;
type InputScrollTarget = 'none' | 'top' | 'cursor' | 'bottom';
type HistoryScrollTarget = 'top' | 'bottom';
type SettingsScreen = 'main' | 'providers' | 'logs';
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
    private _loadingBubble?: St.BoxLayout;
    private _thinkingHeader?: St.BoxLayout;
    private _thinkingTitleLabel?: St.Label;
    private _thinkingDetailsLabel?: St.Label;
    private _thinkingToggleBtn?: St.Button;
    private _streamingAnswerBox?: St.BoxLayout;
    private _streamingAnswerActor?: RenderedMessageActor;
    private _streamRenderTimeoutId = 0;
    private _pendingStreamContent = '';
    private _pendingStreamThinking = '';
    private _thinkingExpanded = true;
    private _thinkingAutoCollapsed = false;
    private _isLoading = false;
    private _copyBtn: St.Button;
    private _settingsBtn: St.Button;
    private _popupItem: PopupMenu.PopupBaseMenuItem;
    private _themeManager: ThemeManager;
    private _settings: Gio.Settings | null;
    private _themeSignalId: number = 0;
    private _settingsSignalIds: number[] = [];
    private _lastReply: string | null = null;
    private _focusTimeoutId: number = 0;
    private _blinkTimeoutId: number = 0;

    private _copyTimeoutId: number = 0;
    private _historyScrollTimeoutId: number = 0;
    private _historyScrollTarget: HistoryScrollTarget = 'bottom';
    private _inputLayoutTimeoutId: number = 0;
    private _inputScrollTimeoutId: number = 0;
    private _transientSourceIds: Set<number> = new Set();
    private _destroyed = false;
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
    private _settingsView!: St.BoxLayout;
    private _settingsTopBar!: St.BoxLayout;
    private _settingsBackBtn!: St.Button;
    private _settingsTitle!: St.Label;
    private _settingsScrollView!: St.ScrollView;
    private _settingsListBox!: St.BoxLayout;
    private _refreshingSettingsView: boolean = false;
    private _settingsEntryActors: Partial<Record<ProviderConfigKey, St.Entry | St.PasswordEntry>> = {};
    private _providerDraft: { provider: ProviderId; config: StoredProviderConfig } | null = null;
    private _apiKeyCache = new Map<string, string>();
    private _apiKeyEditing = false;
    private _settingsSaveStatus = '';
    private _settingsScreen: SettingsScreen = 'main';
    private _settingsForcedWide: boolean = false;
    private _modelFetchSession: Soup.Session;
    private _modelFetchCancellable: Gio.Cancellable | null = null;
    private _modelFetchSeq = 0;
    private _modelFetchKey = '';
    private _modelFetchStatus = '';
    private _modelFetchLoading = false;
    private _modelDropdownOpen = false;
    private _providerDropdownOpen = false;
    private _modelOptions: string[] = [];
    private _logPanel = new PopupLogPanel();

    private _hasMessages: boolean = false;
    private _isHistoryView: boolean = false;
    private _isSettingsView: boolean = false;

    /** Called when the user sends a message. */
    onSend: ((text: string) => void) | null = null;

    /** Called when the user clicks the stop button to cancel request. */
    onCancel: (() => void) | null = null;

    /** Called when the settings icon is clicked. */
    onOpenSettings: (() => void) | null = null;

    /** Called when the popup is expanded or restored. */
    onToggleExpand: ((isExpanded: boolean) => void) | null = null;

    /** Called whenever the popup menu is opened or closed. */
    onOpenStateChanged: ((isOpen: boolean) => void) | null = null;

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

    constructor(anchor: St.Widget, themeManager: ThemeManager, settings: Gio.Settings | null = null) {
        this._themeManager = themeManager;
        this._settings = settings;
        this._modelFetchSession = new Soup.Session({ timeout: 10 });
        this._migratePlaintextProviderKeys();

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
        this._menu.connect('open-state-changed', (_menu: PopupMenu.PopupMenu, isOpen: boolean) => {
            Logger.debug(Tag.UI, `Popup ${isOpen ? 'opened' : 'closed'}`);
            if (isOpen) {
                this._clearFocusTimeout();
                this._focusTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 50, () => {
                    this._focusTimeoutId = 0;
                    if (!this._isHistoryView && !this._isSettingsView) {
                        this._entry?.grab_key_focus();
                        this._queueInputLayoutUpdate('cursor');
                    }
                    return GLib.SOURCE_REMOVE;
                });
            } else {
                this._clearFocusTimeout();
                this._stopCursorBlink();
                this._resetCopyState();
            }
            this.onOpenStateChanged?.(isOpen);
            return undefined;
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
            accessible_name: 'Copy latest response',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        this._copyBtn.connect('clicked', () => {
            if (this._lastReply) {
                St.Clipboard.get_default().set_text(
                    St.ClipboardType.CLIPBOARD,
                    this._lastReply
                );

                if (this._copyTimeoutId !== 0) {
                    this._removeSource(this._copyTimeoutId);
                    this._copyTimeoutId = 0;
                }

                this._copyBtn.set_label('Copied');

                this._copyTimeoutId = this._addOneShotTimeout(GLib.PRIORITY_DEFAULT, 2000, () => {
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
            accessible_name: 'Clear current chat',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
            accessible_name: 'Start new chat',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
            accessible_name: 'Show chat history',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
            accessible_name: 'Expand chat',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
            accessible_name: 'Open Mei settings',
            accessible_role: Atk.Role.PUSH_BUTTON,
            child: new St.Icon({
                icon_name: 'emblem-system-symbolic',
                icon_size: 14,
            }),
        });
        this._settingsBtn.connect('clicked', () => {
            if (this._settings) {
                this.showSettings();
            } else {
                this._menu.close();
                this.onOpenSettings?.();
            }
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
            accessible_name: 'Message input',
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

        ct.connect('key-press-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
            const key = event.get_key_symbol();
            if (key === Clutter.KEY_Return || key === Clutter.KEY_KP_Enter) {
                const state = event.get_state();
                if ((state & Clutter.ModifierType.SHIFT_MASK) === 0) {
                    this._addOneShotIdle(GLib.PRIORITY_DEFAULT_IDLE, () => {
                        this._handleSend();
                        return GLib.SOURCE_REMOVE;
                    });
                    return Clutter.EVENT_STOP;
                }
            }
            return Clutter.EVENT_PROPAGATE;
        });

        // Intercept clicks on the St.Entry padding/margin area (empty space to
        // the right of short lines). Transform the click coordinates into the
        // ClutterText actor's own coordinate space and use coords_to_position()
        // to place the cursor at the nearest character.
        this._entry.connect('button-press-event', (_actor: Clutter.Actor, event: Clutter.Event) => {
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
            accessible_name: 'Send message',
            accessible_role: Atk.Role.PUSH_BUTTON,
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
            accessible_name: 'Back to chat',
            accessible_role: Atk.Role.PUSH_BUTTON,
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

        /* ── Settings View ──────────────────────────────── */
        this._settingsView = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_expand: true,
            visible: false,
        });

        this._settingsTopBar = new St.BoxLayout({
            x_expand: true,
            style_class: 'mei-top-bar',
        });

        this._settingsBackBtn = new St.Button({
            style_class: 'mei-icon-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: 'Back to chat',
            accessible_role: Atk.Role.PUSH_BUTTON,
            child: new St.Icon({
                icon_name: 'go-previous-symbolic',
                icon_size: 14,
            }),
        });
        this._settingsBackBtn.connect('clicked', () => this.hideSettings());
        this._settingsTopBar.add_child(this._settingsBackBtn);
        this._addButtonClickScaleEffect(this._settingsBackBtn);

        this._settingsTitle = new St.Label({
            text: 'Settings',
            style_class: 'mei-history-header-title',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._settingsTopBar.add_child(this._settingsTitle);

        const settingsRightSpacer = new St.Widget({
            width: 22,
        });
        this._settingsTopBar.add_child(settingsRightSpacer);

        this._settingsView.add_child(this._settingsTopBar);

        this._settingsScrollView = new St.ScrollView({
            style_class: 'mei-settings-scroll',
            x_expand: true,
            y_expand: false,
            overlay_scrollbars: true,
        });
        this._settingsScrollView.set_policy(
            St.PolicyType.NEVER,
            St.PolicyType.NEVER
        );
        this._settingsScrollView.set_style(`max-height: ${SETTINGS_SCROLL_MAX_HEIGHT}px;`);

        this._settingsListBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-settings-list',
        });
        this._settingsScrollView.set_child(this._settingsListBox);
        this._settingsView.add_child(this._settingsScrollView);

        this._container.add_child(this._settingsView);

        if (this._settings) {
            this._settingsSignalIds.push(this._settings.connect('changed', (_settings: Gio.Settings, key: string) => {
                if (!this._isSettingsView || this._refreshingSettingsView) return;
                if (key === 'provider-configs') return;
                this._refreshSettingsView();
            }));
        }

        /* ── Apply theme ──────────────────────────────── */
        this._applyTheme();
        this._themeSignalId = this._themeManager.onThemeChanged(() => this._applyTheme());
    }

    /* ── Public API ───────────────────────────────────── */

    get isExpanded(): boolean {
        return this._isExpanded;
    }

    get isOpen(): boolean {
        return this._menu.isOpen;
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

        const rendered = createMessageActor(text, {
            role,
            compact: !this._isExpanded,
        });
        rendered.actor.x_align = role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START;
        rendered.actor.x_expand = role === 'assistant';

        if (role === 'assistant') {
            this._lastReply = text;
            this._copyBtn.visible = !this._isExpanded && text.length > 0;
        } else {
            this._copyBtn.visible = false;
        }

        this._messageBox.add_child(rendered.actor);
        this._scrollView.visible = true;
        this._queueHistoryScrollToTop();
    }

    private _animateHeightChange(changeFn: () => void): void {
        if (this._destroyed) return;
        const containerWidth = Math.max(1, this._container.get_width() || CHAT_WIDTH);
        const currentHeight = this._container.get_height();
        const [, naturalHeight] = this._activeView().get_preferred_height(containerWidth);
        const fromHeight = Math.max(1, currentHeight > 0 ? currentHeight : naturalHeight);
        this._container.set_height(fromHeight);

        changeFn();

        this._addOneShotIdle(GLib.PRIORITY_DEFAULT, () => {
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            const targetHeight = this._targetHeightForView(this._activeView(), containerWidth);

            this._container.ease({
                height: targetHeight,
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => {
                    if (this._destroyed) return;
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
     */
    showHistory(
        messages: { role: string, content: string, thinking?: string, metadata?: ChatMessageMetadata }[],
        fadeLastAssistant = false
    ): void {
        if (this._isLoading) {
            this._removeLoadingBubble();
        }
        this._messageBox.destroy_all_children();

        for (let i = 0; i < messages.length; i++) {
            const msg = messages[i];
            const role = msg.role;
            const text = msg.content;
            if (!isRenderableRole(role)) continue;

            const msgContainer = new St.BoxLayout({
                vertical: true,
                x_expand: true,
                style_class: 'mei-msg-container',
            });

            const rendered = createMessageActor(text, {
                role,
                compact: !this._isExpanded,
            });
            rendered.actor.x_align = role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START;
            rendered.actor.x_expand = role === 'assistant';
            const shouldFadeIn = fadeLastAssistant && role === 'assistant' && i === messages.length - 1;
            if (shouldFadeIn) msgContainer.opacity = 0;

            if (role === 'assistant' && this._isExpanded && msg.thinking) {
                msgContainer.add_child(this._createThinkingBlock(msg.thinking));
            }

            msgContainer.add_child(rendered.actor);

            const infoPanel = role === 'assistant'
                ? createMessageInfoPanel(msg.metadata, this._themeManager.isDark)
                : null;

            // Action buttons bar below each message
            const actionBar = new St.BoxLayout({
                style_class: 'mei-action-bar',
                x_align: role === 'user' ? Clutter.ActorAlign.END : Clutter.ActorAlign.START,
            });

            // Copy button
            const copyIcon = new St.Icon({
                icon_name: 'edit-copy-symbolic',
                icon_size: 12,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            const copyBtn = new St.Button({
                style_class: 'mei-action-btn',
                can_focus: true,
                reactive: true,
                track_hover: true,
                accessible_name: `Copy ${role === 'user' ? 'message' : 'response'}`,
                accessible_role: Atk.Role.PUSH_BUTTON,
                child: copyIcon,
            });
            copyBtn.connect('clicked', () => {
                St.Clipboard.get_default().set_text(
                    St.ClipboardType.CLIPBOARD,
                    text
                );
                copyIcon.icon_name = 'object-select-symbolic';
                this._addOneShotTimeout(GLib.PRIORITY_DEFAULT, 1500, () => {
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
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                const reloadBtn = new St.Button({
                    style_class: 'mei-action-btn',
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                    accessible_name: 'Regenerate response',
                    accessible_role: Atk.Role.PUSH_BUTTON,
                    child: reloadIcon,
                });
                reloadBtn.connect('clicked', () => {
                    this.onReload?.(i);
                });
                actionBar.add_child(reloadBtn);
                this._addButtonClickScaleEffect(reloadBtn);

                const infoGlyph = new St.Label({
                    text: 'i',
                    style_class: 'mei-info-glyph',
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                });
                const infoBtn = new St.Button({
                    style_class: 'mei-action-btn mei-info-btn',
                    can_focus: true,
                    reactive: true,
                    track_hover: true,
                    accessible_name: 'Show response information',
                    accessible_role: Atk.Role.PUSH_BUTTON,
                    child: infoGlyph,
                });
                infoBtn.connect('clicked', () => {
                    if (!infoPanel) return;
                    this._toggleMessageInfoPanel(infoPanel, infoBtn);
                });
                actionBar.add_child(infoBtn);
                this._addButtonClickScaleEffect(infoBtn);
            }

            msgContainer.add_child(actionBar);
            if (infoPanel) {
                msgContainer.add_child(infoPanel);
            }
            this._messageBox.add_child(msgContainer);
            if (shouldFadeIn) {
                this._addOneShotIdle(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    if (msgContainer.get_parent()) {
                        msgContainer.ease({
                            opacity: 255,
                            duration: 320,
                            mode: Clutter.AnimationMode.EASE_IN_OUT_QUAD,
                        });
                    }
                    return GLib.SOURCE_REMOVE;
                });
            }
        }

        if (this._isLoading) {
            this._attachLoadingBubbleForCurrentMode();
        }

        this._scrollView.visible = messages.length > 0 || this._isLoading;
        this._copyBtn.visible = false;
        this._hasMessages = messages.length > 0 || this._isLoading;

        this._queueHistoryScrollToBottom();
    }

    private _toggleMessageInfoPanel(panel: St.BoxLayout, button: St.Button): void {
        const visible = !panel.visible;
        button.accessible_name = visible ? 'Hide response information' : 'Show response information';
        if (visible) {
            button.add_style_class_name('selected');
        } else {
            button.remove_style_class_name('selected');
        }

        this._animateHeightChange(() => {
            panel.remove_all_transitions();
            if (visible) {
                panel.opacity = 0;
                panel.visible = true;
                panel.ease({
                    opacity: 255,
                    duration: 120,
                    mode: Clutter.AnimationMode.EASE_IN_QUAD,
                });
            } else {
                panel.visible = false;
                panel.opacity = 255;
            }
        });
    }

    private _styleMessageInfoPanel(panel: St.Widget): void {
        styleMessageInfoPanel(panel, this._themeManager.isDark);
    }

    private _createThinkingBlock(thinking: string): St.BoxLayout {
        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-thinking-block',
        });

        const header = new St.BoxLayout({
            x_expand: false,
            x_align: Clutter.ActorAlign.START,
            style_class: 'mei-thinking-header',
        });
        header.add_child(new St.Label({
            text: 'Thinking',
            style_class: 'mei-thinking-block-title',
            y_align: Clutter.ActorAlign.CENTER,
        }));

        const body = new St.Label({
            text: formatThinkingPreview(thinking),
            visible: false,
            x_expand: true,
            style_class: 'mei-thinking-details',
        });
        body.clutter_text.set_line_wrap(true);
        body.clutter_text.set_line_wrap_mode(0);
        body.clutter_text.set_ellipsize(0);

        let expanded = false;
        const toggleBtn = new St.Button({
            label: '⌄',
            style_class: 'mei-thinking-toggle',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: 'Toggle thinking details',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        toggleBtn.connect('clicked', () => {
            expanded = !expanded;
            body.visible = expanded;
            toggleBtn.set_label(expanded ? '⌃' : '⌄');
        });
        header.add_child(toggleBtn);

        box.add_child(header);
        box.add_child(body);

        return box;
    }

    toggleExpand(): void {
        const fromWidth = Math.max(1, this._container.get_width() || (this._isExpanded ? SETTINGS_WIDTH : CHAT_WIDTH));
        const fromHeight = Math.max(1, this._container.get_height() || this._targetHeightForView(this._activeView(), fromWidth));

        this._isExpanded = !this._isExpanded;

        if (this._isExpanded) {
            this._container.add_style_class_name('expanded');
        } else {
            this._container.remove_style_class_name('expanded');
        }
        this._syncAskButtonState();

        // Toggle button visibility based on mode
        this._clearBtn.visible = !this._isExpanded;
        this._newChatBtn.visible = this._isExpanded;
        this._historyBtn.visible = this._isExpanded;

        // If collapsing while in a secondary view, go back to chat first
        if (!this._isExpanded && (this._isHistoryView || this._isSettingsView)) {
            this._chatView.visible = true;
            this._chatView.opacity = 255;
            this._historyView.visible = false;
            this._settingsView.visible = false;
            this._isHistoryView = false;
            this._isSettingsView = false;
        }

        // 1. Fade out the content smoothly
        this._contentBox.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;
                const targetWidth = this._isExpanded ? SETTINGS_WIDTH : CHAT_WIDTH;

                // Update settings/expand icon and copy button visibility
                this._expandIcon.icon_name = this._isExpanded
                    ? 'bolt-symbolic'
                    : 'chat-symbolic';
                this._expandBtn.accessible_name = this._isExpanded
                    ? 'Collapse chat'
                    : 'Expand chat';

                // Notify extension to refresh rendering (via onToggleExpand)
                this.onToggleExpand?.(this._isExpanded);

                this._container.set_width(fromWidth);
                this._container.set_height(fromHeight);

                this._addOneShotIdle(GLib.PRIORITY_DEFAULT, () => {
                    if (this._destroyed) return GLib.SOURCE_REMOVE;

                    // 2. Animate the container size after refreshed content has a layout.
                    this._container.ease({
                        width: targetWidth,
                        height: this._targetHeightForView(this._activeView(), targetWidth),
                        duration: 220,
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                        onComplete: () => {
                            if (this._destroyed) return;
                            this._container.set_height(-1);
                            this._queueInputLayoutUpdate('cursor');

                            // 3. Fade the content back in
                            this._contentBox.ease({
                                opacity: 255,
                                duration: 150,
                                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                            });
                        }
                    });
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
    }

    private _syncAskButtonState(): void {
        if (this._isLoading && !this._isExpanded) {
            this._askBtn.set_label('Stop');
            this._askBtn.accessible_name = 'Stop response';
            this._askBtn.add_style_class_name('loading');
            this._askBtn.reactive = true;
            return;
        }

        this._askBtn.remove_style_class_name('loading');
        this._askBtn.set_label('Ask');
        this._askBtn.accessible_name = this._isLoading ? 'Response in progress' : 'Send message';
        this._askBtn.reactive = !this._isLoading;
    }

    private _resetStreamingBubbleActors(): void {
        this._thinkingDetailsLabel = undefined;
        this._thinkingHeader = undefined;
        this._thinkingTitleLabel = undefined;
        this._thinkingToggleBtn = undefined;
        this._streamingAnswerBox = undefined;
        if (this._streamingAnswerActor) {
            this._streamingAnswerActor.destroy();
            this._streamingAnswerActor = undefined;
        }
    }

    private _returnSpinnerToContentBox(): void {
        const spinnerParent = this._spinner.get_parent();
        if (spinnerParent === this._contentBox) return;

        if (spinnerParent) {
            if (spinnerParent instanceof St.Button) {
                spinnerParent.set_child(null);
            } else {
                spinnerParent.remove_child(this._spinner);
            }
        }
        this._contentBox.add_child(this._spinner);
    }

    private _removeLoadingBubble(): void {
        if (this._streamRenderTimeoutId !== 0) {
            this._removeSource(this._streamRenderTimeoutId);
            this._streamRenderTimeoutId = 0;
        }
        this._pendingStreamContent = '';
        this._pendingStreamThinking = '';
        this._returnSpinnerToContentBox();
        if (this._loadingBubble) {
            const bubbleParent = this._loadingBubble.get_parent();
            if (bubbleParent) {
                bubbleParent.remove_child(this._loadingBubble);
            }
            this._loadingBubble.destroy();
            this._loadingBubble = undefined;
        }
        this._resetStreamingBubbleActors();
    }

    private _attachLoadingBubbleForCurrentMode(): void {
        this._removeLoadingBubble();
        this._loadingBubble = this._isExpanded
            ? this._createExpandedLoadingBubble()
            : new St.BoxLayout({
                style_class: 'mei-bubble-ai',
                x_align: Clutter.ActorAlign.START,
                x_expand: false,
            });

        if (!this._isExpanded) {
            this._reparentSpinner(this._loadingBubble);
        }

        this._spinner.play();
        this._spinner.visible = true;
        this._messageBox.add_child(this._loadingBubble);
        this._scrollView.visible = true;
        this._hasMessages = true;
    }

    /** Sets the loading state of the ask button. */
    setLoading(loading: boolean): void {
        if (this._isLoading === loading) return;
        this._isLoading = loading;
        this._syncAskButtonState();

        if (loading) {
            this._thinkingExpanded = true;
            this._thinkingAutoCollapsed = false;
            this._attachLoadingBubbleForCurrentMode();

            // Auto-scroll to bottom
            this._addOneShotIdle(GLib.PRIORITY_DEFAULT, () => {
                if (this._destroyed) return GLib.SOURCE_REMOVE;
                const adjustment = this._scrollView.get_vadjustment();
                adjustment.value = adjustment.upper - adjustment.page_size;
                return GLib.SOURCE_REMOVE;
            });
        } else {
            // Workaround for Clutter hover/scale sticking when child is replaced during interaction
            this._askBtn.scale_x = 1.0;
            this._askBtn.scale_y = 1.0;
            this._askBtn.sync_hover();

            this._spinner.stop();
            this._spinner.visible = false;
            this._removeLoadingBubble();
            this._thinkingAutoCollapsed = false;
        }
    }

    private _createExpandedLoadingBubble(): St.BoxLayout {
        const bubble = new St.BoxLayout({
            vertical: true,
            style_class: 'mei-streaming-bubble',
            x_expand: true,
        });

        const header = new St.BoxLayout({
            style_class: 'mei-thinking-header',
            x_expand: false,
            x_align: Clutter.ActorAlign.START,
            visible: true,
        });
        this._reparentSpinner(header);
        this._spinner.x_expand = false;
        this._spinner.y_expand = false;
        const thinkingLabel = new St.Label({
            text: 'Thinking',
            visible: false,
            style_class: 'mei-thinking-title',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._thinkingTitleLabel = thinkingLabel;
        header.add_child(thinkingLabel);
        this._thinkingToggleBtn = new St.Button({
            label: this._thinkingExpanded ? '⌃' : '⌄',
            style_class: 'mei-thinking-toggle',
            can_focus: true,
            reactive: true,
            track_hover: true,
            visible: false,
            accessible_name: 'Toggle thinking details',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        this._thinkingToggleBtn.connect('clicked', () => {
            this._thinkingExpanded = !this._thinkingExpanded;
            if (this._thinkingDetailsLabel) {
                this._thinkingDetailsLabel.visible = this._thinkingExpanded;
            }
            this._thinkingToggleBtn?.set_label(this._thinkingExpanded ? '⌃' : '⌄');
        });
        header.add_child(this._thinkingToggleBtn);
        bubble.add_child(header);
        this._thinkingHeader = header;

        this._thinkingDetailsLabel = new St.Label({
            text: '',
            visible: false,
            x_expand: true,
            style_class: 'mei-thinking-details',
        });
        this._thinkingDetailsLabel.clutter_text.set_line_wrap(true);
        this._thinkingDetailsLabel.clutter_text.set_line_wrap_mode(0);
        this._thinkingDetailsLabel.clutter_text.set_ellipsize(0);
        bubble.add_child(this._thinkingDetailsLabel);

        this._streamingAnswerBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-streaming-answer',
        });
        bubble.add_child(this._streamingAnswerBox);
        return bubble;
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

    showStreamingResponse(content: string, thinking: string): void {
        this._pendingStreamContent = content;
        this._pendingStreamThinking = thinking;
        if (this._streamRenderTimeoutId !== 0) return;

        this._streamRenderTimeoutId = this._addOneShotTimeout(GLib.PRIORITY_DEFAULT, 50, () => {
            this._streamRenderTimeoutId = 0;
            this._renderStreamingResponse(this._pendingStreamContent, this._pendingStreamThinking);
            return GLib.SOURCE_REMOVE;
        });
    }

    private _renderStreamingResponse(content: string, thinking: string): void {
        if (!this._isExpanded || !this._loadingBubble) return;

        const adjustment = this._scrollView.get_vadjustment();
        const scrollValue = adjustment.get_value();
        const hasThinking = thinking.trim().length > 0;
        const hasContent = content.trim().length > 0;

        // Auto-scroll logic: if the user was already near the bottom (within 20px), auto-scroll to the new bottom.
        const isNearBottom = scrollValue >= (adjustment.get_upper() - adjustment.get_page_size() - 20);

        if (hasThinking && hasContent && !this._thinkingAutoCollapsed) {
            this._thinkingExpanded = false;
            this._thinkingAutoCollapsed = true;
        }

        if (this._thinkingHeader) {
            this._thinkingHeader.visible = hasThinking || !hasContent;
        }
        if (this._thinkingTitleLabel) {
            this._thinkingTitleLabel.visible = hasThinking;
        }
        if (this._thinkingDetailsLabel) {
            this._thinkingDetailsLabel.set_text(hasThinking ? formatThinkingPreview(thinking.trim()) : '');
            this._thinkingDetailsLabel.visible = hasThinking && this._thinkingExpanded;
        }
        if (this._thinkingToggleBtn) {
            this._thinkingToggleBtn.visible = hasThinking;
            this._thinkingToggleBtn.set_label(this._thinkingExpanded ? '⌃' : '⌄');
        }

        if (this._streamingAnswerBox) {
            if (hasContent) {
                if (!this._streamingAnswerActor) {
                    this._streamingAnswerActor = createMessageActor(content, {
                        role: 'assistant',
                        compact: false,
                        streaming: true,
                    });
                    this._streamingAnswerActor.actor.x_expand = true;
                    this._streamingAnswerBox.add_child(this._streamingAnswerActor.actor);
                } else {
                    this._streamingAnswerActor.update(content, { streaming: true });
                }
            } else if (this._streamingAnswerActor) {
                this._streamingAnswerActor.destroy();
                this._streamingAnswerActor = undefined;
            }
        }

        this._addOneShotIdle(GLib.PRIORITY_DEFAULT, () => {
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            const lower = adjustment.get_lower();
            const upper = adjustment.get_upper();
            const pageSize = adjustment.get_page_size();
            const target = isNearBottom
                ? Math.max(lower, upper - pageSize)
                : Math.max(lower, Math.min(scrollValue, upper - pageSize));
            adjustment.set_value(target);
            return GLib.SOURCE_REMOVE;
        });
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
            accessible_name: 'Copy error details',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        copyBtn.connect('clicked', () => {
            St.Clipboard.get_default().set_text(
                St.ClipboardType.CLIPBOARD,
                this._errorMessage
            );
            copyBtn.set_label('Copied');
            this._addOneShotTimeout(GLib.PRIORITY_DEFAULT, 1500, () => {
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

    /* ── Secondary popup views ───────────────────────── */

    private _activeView(): St.BoxLayout {
        if (this._isHistoryView) return this._historyView;
        if (this._isSettingsView) return this._settingsView;
        return this._chatView;
    }

    private _targetHeightForView(view: St.BoxLayout, width: number = Math.max(1, this._container.get_width() || CHAT_WIDTH)): number {
        const [, toHeight] = view.get_preferred_height(width);
        const height = Math.max(1, Math.ceil(toHeight));
        return view === this._settingsView ? Math.min(height, SETTINGS_HEIGHT) : height;
    }

    private _transitionToView(
        targetView: St.BoxLayout,
        onComplete: () => void,
        targetWidth: number = Math.max(1, this._container.get_width() || CHAT_WIDTH)
    ): void {
        const activeView = this._activeView();
        if (activeView === targetView) {
            const fromWidth = Math.max(1, this._container.get_width() || targetWidth);
            const fromHeight = Math.max(1, this._container.get_height() || this._targetHeightForView(targetView, fromWidth));
            this._container.set_width(fromWidth);
            this._container.set_height(fromHeight);
            this._container.ease({
                width: targetWidth,
                height: this._targetHeightForView(targetView, targetWidth),
                duration: 200,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => {
                    if (this._destroyed) return;
                    this._container.set_height(-1);
                    onComplete();
                },
            });
            return;
        }

        activeView.ease({
            opacity: 0,
            duration: 150,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;

                const fromWidth = Math.max(1, this._container.get_width() || targetWidth);
                const fromHeight = Math.max(1, this._container.get_height() || this._targetHeightForView(activeView, fromWidth));
                this._container.set_width(fromWidth);
                this._container.set_height(fromHeight);

                activeView.visible = false;
                targetView.visible = true;
                targetView.opacity = 0;

                this._container.ease({
                    width: targetWidth,
                    height: this._targetHeightForView(targetView, targetWidth),
                    duration: 200,
                    mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                    onComplete: () => {
                        if (this._destroyed) return;
                        this._container.set_height(-1);
                        targetView.ease({
                            opacity: 255,
                            duration: 150,
                            mode: Clutter.AnimationMode.EASE_IN_QUAD,
                        });
                        onComplete();
                    },
                });
            },
        });
    }

    private _transitionToChat(onComplete: () => void, targetWidth: number = this._isExpanded ? SETTINGS_WIDTH : CHAT_WIDTH): void {
        this._transitionToView(this._chatView, () => {
            this._isHistoryView = false;
            this._isSettingsView = false;
            this._queueInputLayoutUpdate('cursor');
            onComplete();
        }, targetWidth);
    }

    /* ── History list panel ──────────────────────────── */

    /**
     * Populate and show the history panel (big popup only).
     * Fades out the chat view and fades in the history list.
     */
    showHistoryList(items: ChatSummary[]): void {
        renderHistoryList(this._historyListBox, items, {
            addButtonClickScaleEffect: button => this._addButtonClickScaleEffect(button),
            addOneShotTimeout: (priority, interval, callback) => this._addOneShotTimeout(priority, interval, callback),
            removeSource: sourceId => this._removeSource(sourceId),
            hideHistoryList: () => this.hideHistoryList(),
            onLoadChat: id => this.onLoadChat?.(id),
            onDeleteChat: id => this.onDeleteChat?.(id),
        });

        this._applyHistoryTheme();

        this._transitionToView(this._historyView, () => {
            this._isHistoryView = true;
            this._isSettingsView = false;
        });
    }

    /** Hide the history panel and show the chat view. */
    hideHistoryList(): void {
        if (!this._isHistoryView) return;
        this._transitionToChat(() => {});
    }

    /** Populate and show the in-popup settings panel. */
    showSettings(): void {
        if (!this._settings) {
            this.onOpenSettings?.();
            return;
        }

        this._settingsScreen = 'main';
        this._providerDraft = null;
        this._apiKeyEditing = false;
        this._settingsForcedWide = !this._isExpanded;
        this._container.add_style_class_name('expanded');
        this._refreshSettingsView();
        this._transitionToView(this._settingsView, () => {
            this._isHistoryView = false;
            this._isSettingsView = true;
        }, SETTINGS_WIDTH);
    }

    /** Hide the settings panel and show the chat view. */
    hideSettings(): void {
        if (!this._isSettingsView) return;
        if (this._settingsScreen !== 'main') {
            if (this._settingsScreen === 'providers') {
                this._providerDraft = null;
            }
            this._settingsScreen = 'main';
            this._refreshSettingsViewAnimated();
            return;
        }
        const targetWidth = this._isExpanded ? SETTINGS_WIDTH : CHAT_WIDTH;
        this._transitionToChat(() => {
            if (this._settingsForcedWide && !this._isExpanded) {
                this._container.remove_style_class_name('expanded');
            }
            this._settingsForcedWide = false;
        }, targetWidth);
    }

    private _refreshSettingsView(): void {
        const settings = this._settings;
        if (!settings) return;

        this._refreshingSettingsView = true;
        this._settingsEntryActors = {};
        this._settingsListBox.destroy_all_children();
        this._settingsTitle.set_text(this._settingsScreen === 'main'
            ? 'Settings'
            : this._settingsScreen === 'providers'
                ? 'AI Providers'
                : 'Logs');

        if (this._settingsScreen === 'main') {
            this._addSettingsNavRow('Configure AI Providers', 'network-server-symbolic', () => {
                this._settingsScreen = 'providers';
                this._modelDropdownOpen = false;
                this._settingsSaveStatus = '';
                this._refreshSettingsViewAnimated();
            });
            this._addSettingsNavRow('Manage Logs', 'format-justify-left-symbolic', () => {
                this._settingsScreen = 'logs';
                this._logPanel.load();
                this._refreshSettingsViewAnimated();
            });
            this._updateSettingsScrollHeight();
            this._applySettingsTheme();
            this._refreshingSettingsView = false;
            return;
        }

        if (this._settingsScreen === 'logs') {
            this._logPanel.render(this._settingsListBox, {
                refresh: () => this._refreshSettingsView(),
                addButtonClickScaleEffect: button => this._addButtonClickScaleEffect(button),
            });
            this._updateSettingsScrollHeight();
            this._applySettingsTheme();
            this._refreshingSettingsView = false;
            return;
        }

        const providerType = getProviderType(settings.get_string('provider-type'));
        const provider = this._ensureProviderForType(providerType);
        const savedConfig = this._getCurrentProviderConfig();
        const config = this._providerDraft?.provider === provider
            ? this._providerDraft.config
            : savedConfig;

        this._addSettingsSection('Provider');
        this._addSettingsSegmentRow(
            'Type',
            PROVIDER_TYPE_IDS,
            providerType,
            id => PROVIDER_TYPE_LABELS[id],
            id => this._setProviderType(id)
        );

        if (providerType !== 'custom') {
            const providers = getProviderIdsForType(providerType);
            this._addProviderDropdownRow(provider, providers);
        }

        if (provider === 'opencode') {
            const modeIds: OpenCodeMode[] = ['go', 'zen'];
            this._addSettingsSegmentRow(
                'Mode',
                modeIds,
                getOpenCodeMode(config.mode),
                id => OPEN_CODE_MODE_LABELS[id],
                id => void this._updateCurrentProviderConfig('mode', id)
            );
        }

        if (provider === 'deepseek') {
            const thinkingIds: DeepSeekThinking[] = ['default', 'enabled', 'disabled'];
            const thinking = getDeepSeekThinking(config.thinking);
            this._addSettingsSegmentRow(
                'Thinking',
                thinkingIds,
                thinking,
                id => DEEPSEEK_THINKING_LABELS[id],
                id => void this._updateCurrentProviderConfig('thinking', id)
            );
            if (thinking === 'enabled') {
                const effortIds: DeepSeekReasoningEffort[] = ['low', 'high', 'max'];
                this._addSettingsSegmentRow(
                    'Reasoning effort',
                    effortIds,
                    getDeepSeekReasoningEffort(config.reasoningEffort),
                    id => DEEPSEEK_REASONING_EFFORT_LABELS[id],
                    id => void this._updateCurrentProviderConfig('reasoningEffort', id)
                );
            }
        }

        this._addSettingsSection('Connection');
        if (this._modelOptions.length > 0) {
            this._addModelDropdownRow(config.modelName || this._modelOptions[0], this._modelOptions);
        } else {
            this._addSettingsEntryRow(
                'Model',
                config.modelName || '',
                'modelName',
                'Model name'
            );
        }
        this._addFetchModelsRow(provider, config);

        if (providerType === 'local' || providerType === 'custom') {
            this._addSettingsEntryRow(
                'URL',
                config.url || '',
                'url',
                providerType === 'custom' ? 'Endpoint URL' : 'Optional endpoint URL'
            );
        }

        if (this._apiKeyEditing) {
            this._addSettingsEntryRow('API Key', '', 'apiKey', 'Enter new API key', true);
        } else {
            const apiKeyRow = this._createSettingsRow('API Key');
            const enterApiKeyBtn = new St.Button({
                label: 'Enter new API key',
                style_class: 'mei-settings-value-btn',
                can_focus: true,
                reactive: true,
                track_hover: true,
                accessible_name: 'Enter new API key',
                accessible_role: Atk.Role.PUSH_BUTTON,
            });
            enterApiKeyBtn.connect('clicked', () => {
                this._apiKeyEditing = true;
                this._settingsSaveStatus = '';
                this._refreshSettingsView();
                this._settingsEntryActors.apiKey?.grab_key_focus();
            });
            apiKeyRow.add_child(enterApiKeyBtn);
            this._settingsListBox.add_child(apiKeyRow);
            this._addButtonClickScaleEffect(enterApiKeyBtn);
        }
        if (this._modelFetchStatus) {
            this._addSettingsStatusRow(this._modelFetchStatus);
        }
        if (this._settingsSaveStatus) {
            this._addSettingsStatusRow(this._settingsSaveStatus);
        }

        this._updateSettingsScrollHeight();
        this._applySettingsTheme();
        this._refreshingSettingsView = false;
    }

    private _refreshSettingsViewAnimated(): void {
        if (!this._isSettingsView || this._destroyed) {
            this._refreshSettingsView();
            return;
        }

        const fromHeight = Math.max(1, this._container.get_height() || this._targetHeightForView(this._settingsView, SETTINGS_WIDTH));
        this._settingsScrollView.remove_all_transitions();
        this._settingsListBox.remove_all_transitions();

        this._settingsScrollView.ease({
            opacity: 0,
            duration: 120,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
            onComplete: () => {
                if (this._destroyed) return;

                this._container.remove_all_transitions();
                this._container.set_height(fromHeight);
                this._refreshSettingsView();
                this._settingsScrollView.opacity = 0;

                this._addOneShotIdle(GLib.PRIORITY_DEFAULT, () => {
                    if (this._destroyed) return GLib.SOURCE_REMOVE;
                    const targetHeight = this._targetHeightForView(this._settingsView, SETTINGS_WIDTH);
                    this._container.ease({
                        height: targetHeight,
                        duration: 200,
                        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                        onComplete: () => {
                            if (this._destroyed) return;
                            this._container.set_height(-1);
                            this._settingsScrollView.ease({
                                opacity: 255,
                                duration: 120,
                                mode: Clutter.AnimationMode.EASE_IN_QUAD,
                            });
                        },
                    });
                    return GLib.SOURCE_REMOVE;
                });
            },
        });
    }

    private _updateSettingsScrollHeight(): void {
        const width = Math.max(1, SETTINGS_WIDTH - 20);
        const [, naturalHeight] = this._settingsListBox.get_preferred_height(width);
        const needsScroll = naturalHeight > SETTINGS_SCROLL_MAX_HEIGHT;
        const height = Math.max(1, Math.min(Math.ceil(naturalHeight) + (needsScroll ? 0 : 1), SETTINGS_SCROLL_MAX_HEIGHT));
        this._settingsScrollView.set_height(height);
        this._settingsScrollView.set_style(`max-height: ${SETTINGS_SCROLL_MAX_HEIGHT}px;`);
        this._settingsScrollView.set_policy(
            St.PolicyType.NEVER,
            needsScroll ? St.PolicyType.AUTOMATIC : St.PolicyType.NEVER
        );
    }

    private _addSettingsSection(title: string): void {
        addSettingsSection(this._settingsListBox, title);
    }

    private _addSettingsNavRow(title: string, iconName: string, onClick: () => void): void {
        addSettingsNavRow(this._settingsListBox, title, iconName, onClick, {
            addButtonClickScaleEffect: button => this._addButtonClickScaleEffect(button),
        });
    }

    private _addProviderDropdownRow(selectedProvider: ProviderId, providers: readonly ProviderId[]): void {
        const row = this._createSettingsRow('Provider');
        const button = new St.Button({
            label: getProviderLabel(selectedProvider),
            style_class: 'mei-settings-value-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: `Provider: ${getProviderLabel(selectedProvider)}`,
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        button.connect('clicked', () => {
            this._providerDropdownOpen = !this._providerDropdownOpen;
            this._modelDropdownOpen = false;
            this._refreshSettingsView();
        });
        row.add_child(button);
        this._settingsListBox.add_child(row);
        this._addButtonClickScaleEffect(button);

        if (!this._providerDropdownOpen) return;

        const listBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-model-dropdown',
        });
        for (const provider of providers) {
            const providerBtn = new St.Button({
                label: getProviderLabel(provider),
                style_class: provider === selectedProvider ? 'mei-model-option selected' : 'mei-model-option',
                can_focus: true,
                reactive: true,
                track_hover: true,
                accessible_name: `Use provider ${getProviderLabel(provider)}`,
                accessible_role: Atk.Role.PUSH_BUTTON,
            });
            providerBtn.connect('clicked', () => {
                this._providerDropdownOpen = false;
                this._modelDropdownOpen = false;
                this._modelOptions = [];
                this._modelFetchKey = '';
                this._modelFetchStatus = '';
                this._settingsSaveStatus = '';
                this._providerDraft = null;
                this._apiKeyEditing = false;
                this._settings?.set_string('provider', provider);
            });
            listBox.add_child(providerBtn);
            this._addButtonClickScaleEffect(providerBtn);
        }
        this._settingsListBox.add_child(listBox);
    }

    private _addModelDropdownRow(valueText: string, options: string[]): void {
        const selected = valueText || options[0] || '';
        const row = this._createSettingsRow('Model');
        const button = new St.Button({
            label: selected || 'Select model',
            style_class: 'mei-settings-value-btn',
            can_focus: true,
            reactive: true,
            track_hover: true,
            accessible_name: `Model: ${selected || 'Select model'}`,
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        button.connect('clicked', () => {
            this._modelDropdownOpen = !this._modelDropdownOpen;
            this._refreshSettingsView();
        });
        row.add_child(button);
        this._settingsListBox.add_child(row);
        this._addButtonClickScaleEffect(button);

        if (!this._modelDropdownOpen) return;

        const listBox = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'mei-model-dropdown',
        });
        for (const model of options) {
            const modelBtn = new St.Button({
                label: model,
                style_class: model === selected ? 'mei-model-option selected' : 'mei-model-option',
                can_focus: true,
                reactive: true,
                track_hover: true,
                accessible_name: `Use model ${model}`,
                accessible_role: Atk.Role.PUSH_BUTTON,
            });
            modelBtn.connect('clicked', () => {
                this._selectModelOption(model);
            });
            listBox.add_child(modelBtn);
            this._addButtonClickScaleEffect(modelBtn);
        }
        this._settingsListBox.add_child(listBox);
    }

    private _addSettingsStatusRow(text: string): void {
        addSettingsStatusRow(this._settingsListBox, text);
    }

    private _addFetchModelsRow(provider: ProviderId, config: StoredProviderConfig): void {
        const row = new St.BoxLayout({
            x_expand: true,
            x_align: Clutter.ActorAlign.START,
            style_class: 'mei-settings-fetch-row',
        });

        const fetchBtn = new St.Button({
            label: this._modelFetchLoading ? 'Fetching...' : 'Fetch Models',
            style_class: 'mei-settings-chip',
            can_focus: true,
            reactive: !this._modelFetchLoading,
            track_hover: true,
            accessible_name: 'Fetch provider models',
            accessible_role: Atk.Role.PUSH_BUTTON,
        });
        fetchBtn.connect('clicked', () => {
            if (this._modelFetchLoading) return;
            this._settingsSaveStatus = '';
            const draft = this._readProviderConfigDraft(config);
            this._providerDraft = { provider, config: draft };
            void this._queueProviderModelFetch(provider, draft, true);
        });
        row.add_child(fetchBtn);
        this._addButtonClickScaleEffect(fetchBtn);

        this._settingsListBox.add_child(row);
    }

    private _addSettingsSegmentRow<T extends string>(
        labelText: string,
        ids: readonly T[],
        activeId: T,
        getLabel: (id: T) => string,
        onSelect: (id: T) => void
    ): void {
        addSettingsSegmentRow(this._settingsListBox, labelText, ids, activeId, getLabel, onSelect, {
            addButtonClickScaleEffect: button => this._addButtonClickScaleEffect(button),
        });
    }

    private _addSettingsEntryRow(
        labelText: string,
        value: string,
        key: ProviderConfigKey,
        hintText: string,
        isSecret: boolean = false
    ): void {
        const entry = addSettingsEntryRow(
            this._settingsListBox,
            labelText,
            value,
            key,
            hintText,
            isSecret,
            () => this._refreshingSettingsView,
            (savedKey, savedValue, savedLabel) => void this._saveCurrentProviderField(savedKey, savedValue, savedLabel),
            { addButtonClickScaleEffect: button => this._addButtonClickScaleEffect(button) }
        );
        this._settingsEntryActors[key] = entry;
    }

    private _createSettingsRow(labelText: string): St.BoxLayout {
        return createSettingsRow(labelText);
    }

    private _setProviderType(providerType: ProviderType): void {
        const settings = this._settings;
        if (!settings) return;

        this._providerDropdownOpen = false;
        this._modelDropdownOpen = false;
        this._modelOptions = [];
        this._modelFetchKey = '';
        this._modelFetchStatus = '';
        this._settingsSaveStatus = '';
        this._providerDraft = null;
        this._apiKeyEditing = false;
        settings.set_string('provider-type', providerType);
        const providers = getProviderIdsForType(providerType);
        const currentProvider = settings.get_string('provider');
        if (!providers.includes(currentProvider as ProviderId)) {
            settings.set_string('provider', providers[0]);
        }
    }

    private _ensureProviderForType(providerType: ProviderType): ProviderId {
        const settings = this._settings!;
        const providers = getProviderIdsForType(providerType);
        const currentProvider = settings.get_string('provider');
        if (providers.includes(currentProvider as ProviderId)) {
            return currentProvider as ProviderId;
        }

        const fallbackProvider = providers[0];
        settings.set_string('provider', fallbackProvider);
        return fallbackProvider;
    }

    private _getProviderConfigs(): Record<string, StoredProviderConfig> {
        const settings = this._settings;
        if (!settings) return {};
        return parseProviderConfigs(settings.get_string('provider-configs') || '{}');
    }

    private _getCurrentProviderConfig(): StoredProviderConfig {
        const provider = this._settings?.get_string('provider') || '';
        const configs = this._getProviderConfigs();
        return configs[provider] || createEmptyProviderConfig();
    }

    private _readProviderConfigDraft(fallback: StoredProviderConfig): StoredProviderConfig {
        const apiKeyText = this._settingsEntryActors.apiKey?.get_text();
        return {
            url: this._settingsEntryActors.url?.get_text() ?? fallback.url,
            modelName: this._settingsEntryActors.modelName?.get_text() ?? fallback.modelName,
            apiKey: apiKeyText === undefined || isApiKeyPlaceholderLike(apiKeyText) ? fallback.apiKey : apiKeyText,
            apiKeyStorage: fallback.apiKeyStorage,
            mode: fallback.mode,
            thinking: fallback.thinking,
            reasoningEffort: fallback.reasoningEffort,
        };
    }

    private async _migratePlaintextProviderKeys(): Promise<void> {
        const settings = this._settings;
        if (!settings) return;

        const original = this._getProviderConfigs();
        const result = await migratePlaintextApiKeys(original);
        if (this._destroyed || !result.changed) return;
        const current = parseProviderConfigs(settings.get_string('provider-configs'));
        settings.set_string('provider-configs', JSON.stringify(
            mergeMigratedApiKeyConfigs(original, result.configs, current)
        ));
    }

    private async _resolveProviderConfig(provider: ProviderId, config: StoredProviderConfig): Promise<StoredProviderConfig> {
        if (config.apiKey && !isApiKeyPlaceholderLike(config.apiKey)) return config;
        const cachedKey = this._apiKeyCache.get(provider);
        if (cachedKey) return { ...config, apiKey: cachedKey };

        const resolved = await resolveStoredProviderConfig(provider, config);
        if (resolved.apiKey) this._apiKeyCache.set(provider, resolved.apiKey);
        return resolved;
    }

    private async _saveCurrentProviderField(key: ProviderConfigKey, value: string, labelText: string): Promise<void> {
        const settings = this._settings;
        if (!settings) return;

        const provider = settings.get_string('provider') as ProviderId;
        const configs = this._getProviderConfigs();
        const savedConfig = configs[provider] || createEmptyProviderConfig();
        const visibleDraft = this._readProviderConfigDraft(
            this._providerDraft?.provider === provider
                ? this._providerDraft.config
                : savedConfig
        );
        if (key === 'apiKey' && isApiKeyPlaceholderLike(value.trim())) {
            this._providerDraft = { provider, config: visibleDraft };
            this._settingsSaveStatus = 'Using stored API key.';
            this._refreshSettingsView();
            return;
        }
        const nextSavedConfig = key === 'apiKey'
            ? await updateStoredProviderApiKey(provider, savedConfig, value)
            : { ...savedConfig, [key]: value };
        const nextDraftConfig = key === 'apiKey'
            ? { ...visibleDraft, apiKey: nextSavedConfig.apiKey, apiKeyStorage: nextSavedConfig.apiKeyStorage }
            : { ...visibleDraft, [key]: value };
        if (this._destroyed) return;
        const latestConfigs = this._getProviderConfigs();
        const latestConfig = latestConfigs[provider] || createEmptyProviderConfig();
        latestConfigs[provider] = key === 'apiKey'
            ? { ...latestConfig, apiKey: nextSavedConfig.apiKey, apiKeyStorage: nextSavedConfig.apiKeyStorage }
            : { ...latestConfig, [key]: value };
        settings.set_string('provider-configs', JSON.stringify(latestConfigs));
        const isCurrentProvider = settings.get_string('provider') === provider;
        if (key === 'apiKey') {
            if (value.trim()) {
                this._apiKeyCache.set(provider, value.trim());
            } else {
                this._apiKeyCache.delete(provider);
            }
            this._invalidateModelFetch();
            if (isCurrentProvider) this._apiKeyEditing = false;
        } else if (key === 'url') {
            this._invalidateModelFetch();
        }
        this._providerDraft = isCurrentProvider ? { provider, config: nextDraftConfig } : null;
        this._settingsSaveStatus = isCurrentProvider ? `Saved ${labelText}.` : '';
        this._modelFetchStatus = '';
        this._refreshSettingsView();
    }

    private _selectModelOption(model: string): void {
        const settings = this._settings;
        if (!settings) return;

        const provider = settings.get_string('provider') as ProviderId;
        const configs = this._getProviderConfigs();
        const savedConfig = configs[provider] || createEmptyProviderConfig();
        const visibleDraft = this._readProviderConfigDraft(
            this._providerDraft?.provider === provider
                ? this._providerDraft.config
                : savedConfig
        );
        const nextConfig = { ...visibleDraft, modelName: model };

        configs[provider] = { ...savedConfig, modelName: model };
        settings.set_string('provider-configs', JSON.stringify(configs));
        this._providerDraft = { provider, config: nextConfig };
        this._settingsSaveStatus = '';
        this._modelDropdownOpen = false;
        this._refreshSettingsView();
    }

    private async _updateCurrentProviderConfig(key: ProviderConfigKey, value: string, refreshView: boolean = true): Promise<void> {
        const settings = this._settings;
        if (!settings) return;

        const provider = settings.get_string('provider');
        const configs = this._getProviderConfigs();
        if (!configs[provider]) {
            configs[provider] = createEmptyProviderConfig();
        }
        if (key === 'apiKey' && isApiKeyPlaceholderLike(value.trim())) return;
        if (configs[provider][key] === value) return;
        if (key === 'apiKey') {
            configs[provider] = await updateStoredProviderApiKey(provider, configs[provider], value);
            if (value.trim()) {
                this._apiKeyCache.set(provider, value.trim());
            } else {
                this._apiKeyCache.delete(provider);
            }
        } else {
            configs[provider][key] = value;
        }
        if (this._destroyed) return;
        const latestConfigs = this._getProviderConfigs();
        const latestConfig = latestConfigs[provider] || createEmptyProviderConfig();
        latestConfigs[provider] = key === 'apiKey'
            ? { ...latestConfig, apiKey: configs[provider].apiKey, apiKeyStorage: configs[provider].apiKeyStorage }
            : {
                ...latestConfig,
                [key]: value,
            };
        settings.set_string('provider-configs', JSON.stringify(latestConfigs));

        if (key === 'url' || key === 'apiKey' || key === 'mode') {
            this._invalidateModelFetch();
        }

        if (refreshView && this._isSettingsView && this._settingsScreen === 'providers') {
            this._refreshSettingsView();
        }
    }

    private async _queueProviderModelFetch(provider: ProviderId, config: StoredProviderConfig, force: boolean = false): Promise<void> {
        const resolvedConfig = await this._resolveProviderConfig(provider, config);
        if (this._destroyed) return;

        const key = this._getModelFetchKey(provider, resolvedConfig);
        if (!force && key === this._modelFetchKey) return;

        this._modelFetchKey = key;
        this._modelOptions = [];
        this._modelFetchStatus = '';
        this._modelFetchLoading = true;
        this._modelDropdownOpen = false;
        const seq = ++this._modelFetchSeq;
        this._modelFetchCancellable?.cancel();
        const cancellable = new Gio.Cancellable();
        this._modelFetchCancellable = cancellable;

        fetchProviderModels(
            this._modelFetchSession,
            provider,
            {
                url: resolvedConfig.url || '',
                apiKey: resolvedConfig.apiKey || '',
                mode: resolvedConfig.mode || '',
            },
            cancellable
        )
            .then(result => {
                if (this._destroyed || seq !== this._modelFetchSeq || cancellable.is_cancelled()) return;
                this._modelFetchLoading = false;
                this._modelOptions = result.models;
                this._modelFetchStatus = result.requiresApiKey
                    ? resolvedConfig.apiKeyStorage === 'secret'
                        ? 'Stored API key could not be read. Enter and save it again.'
                        : 'API key required to load models.'
                    : result.models.length === 0
                        ? 'No models returned; enter a model name manually.'
                        : '';

                if (!resolvedConfig.modelName && result.models.length > 0) {
                    this._providerDraft = {
                        provider,
                        config: { ...resolvedConfig, modelName: result.models[0] },
                    };
                }
                if (this._isSettingsView && this._settingsScreen === 'providers') {
                    this._refreshSettingsView();
                }
            })
            .catch(e => {
                if (this._destroyed || seq !== this._modelFetchSeq || cancellable.is_cancelled()) return;
                this._modelFetchLoading = false;
                this._modelOptions = [];
                this._modelFetchStatus = `Model list unavailable: ${e instanceof Error ? e.message : String(e)}`;
                if (this._isSettingsView && this._settingsScreen === 'providers') {
                    this._refreshSettingsView();
                }
            });

        this._modelFetchStatus = '';
    }

    private _getModelFetchKey(provider: ProviderId, config: StoredProviderConfig): string {
        return [
            provider,
            config.url || '',
            config.apiKey || '',
            config.mode || '',
        ].join('\u0000');
    }

    private _invalidateModelFetch(): void {
        this._modelOptions = [];
        this._modelFetchKey = '';
        this._modelFetchStatus = '';
        this._modelFetchLoading = false;
        this._modelDropdownOpen = false;
        this._modelFetchCancellable?.cancel();
        this._modelFetchCancellable = null;
        this._modelFetchSeq++;
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
            if (this._destroyed) {
                this._inputLayoutTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
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
            if (this._destroyed) {
                this._inputScrollTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
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

    private _queueHistoryScrollToTop(): void {
        this._queueHistoryScroll('top');
    }

    private _queueHistoryScrollToBottom(): void {
        this._queueHistoryScroll('bottom');
    }

    private _queueHistoryScroll(target: HistoryScrollTarget): void {
        this._historyScrollTarget = target;
        if (this._historyScrollTimeoutId !== 0) return;

        this._historyScrollTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 33, () => {
            if (this._destroyed) {
                this._historyScrollTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
            this._historyScrollTimeoutId = 0;
            const adj = this._scrollView.get_vadjustment();
            if (this._historyScrollTarget === 'top') {
                adj.set_value(adj.get_lower());
            } else {
                const maxValue = Math.max(adj.get_lower(), adj.get_upper() - adj.get_page_size());
                adj.set_value(maxValue);
            }
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
        this._settingsBackBtn.set_style(iconStyle);

        // Apply theme color to History Title
        const fg = this._themeManager.isDark ? '#ffffff' : '#000000';
        this._historyTitle.set_style(`color: ${fg}; font-weight: bold; font-size: 14px;`);
        this._settingsTitle.set_style(`color: ${fg}; font-weight: bold; font-size: 14px;`);

        this._applyErrorTheme();
        this._applyHistoryTheme();
        this._applyMessageInfoTheme();
        this._applySettingsTheme();
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
        styleHistoryList(this._historyListBox, this._themeManager.isDark);
    }

    private _applyMessageInfoTheme(): void {
        if (!this._messageBox) return;

        const visit = (actor: Clutter.Actor): void => {
            if (actor instanceof St.Widget && actor.has_style_class_name('mei-message-info-panel')) {
                this._styleMessageInfoPanel(actor);
            }
            for (const child of actor.get_children()) {
                visit(child);
            }
        };

        visit(this._messageBox);
    }

    private _applySettingsTheme(): void {
        if (!this._settingsListBox) return;

        const isDark = this._themeManager.isDark;
        const fg = isDark ? '#ffffff' : '#000000';
        const muted = isDark ? '#a0a0a0' : '#666666';
        const bg = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        const selectedBg = isDark ? 'rgba(255,255,255,0.20)' : 'rgba(0,0,0,0.14)';

        for (const child of this._settingsListBox.get_children()) {
            if (child instanceof St.Label) {
                const bgStyle = child.has_style_class_name('mei-log-text') ? `background-color: ${bg}; ` : '';
                child.set_style(`${bgStyle}color: ${child.has_style_class_name('mei-log-text') ? fg : muted};`);
                continue;
            }
            if (child instanceof St.Button) {
                child.set_style(`background-color: ${bg}; color: ${fg};`);
                continue;
            }
            if (child instanceof St.ScrollView) {
                child.set_style(`background-color: ${bg};`);
                const scrollChild = child.get_child();
                if (scrollChild instanceof St.BoxLayout && scrollChild.has_style_class_name('mei-log-box')) {
                    for (const logChild of scrollChild.get_children()) {
                        if (logChild instanceof St.Label && logChild.has_style_class_name('mei-log-text')) {
                            logChild.set_style(`color: ${fg};`);
                        }
                    }
                }
                continue;
            }
            if (!(child instanceof St.BoxLayout)) continue;

            for (const rowChild of child.get_children()) {
                if (rowChild instanceof St.Label) {
                    rowChild.set_style(`color: ${fg};`);
                } else if (rowChild instanceof St.Button) {
                    const selected = rowChild.has_style_class_name('selected');
                    rowChild.set_style(`background-color: ${selected ? selectedBg : bg}; color: ${fg};`);
                } else if (rowChild instanceof St.Entry || rowChild instanceof St.PasswordEntry) {
                    rowChild.set_style(`background-color: ${bg}; color: ${fg}; caret-color: ${fg}; -st-hint-color: ${muted};`);
                } else if (rowChild instanceof St.BoxLayout) {
                    for (const segment of rowChild.get_children()) {
                        if (segment instanceof St.Button) {
                            const selected = segment.has_style_class_name('selected');
                            segment.set_style(`background-color: ${selected ? selectedBg : bg}; color: ${fg};`);
                        } else if (segment instanceof St.Label) {
                            segment.set_style(`color: ${fg};`);
                        } else if (segment instanceof St.Icon) {
                            segment.set_style(`color: ${muted};`);
                        }
                    }
                }
            }
        }
    }

    private _startCursorBlink(): void {
        if (this._blinkTimeoutId) return;
        const ct = this._entry.clutter_text;
        ct.cursor_visible = true;
        this._blinkTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            if (this._destroyed) {
                this._blinkTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
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
            if (this._destroyed) {
                this._blinkTimeoutId = 0;
                return GLib.SOURCE_REMOVE;
            }
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
            this._removeSource(this._copyTimeoutId);
            this._copyTimeoutId = 0;
        }
        this._copyBtn.set_label('Copy');
    }

    private _addOneShotTimeout(priority: number, interval: number, callback: () => typeof GLib.SOURCE_REMOVE): number {
        let sourceId = 0;
        sourceId = GLib.timeout_add(priority, interval, () => {
            this._transientSourceIds.delete(sourceId);
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            return callback();
        });
        this._transientSourceIds.add(sourceId);
        return sourceId;
    }

    private _addOneShotIdle(priority: number, callback: () => typeof GLib.SOURCE_REMOVE): number {
        let sourceId = 0;
        sourceId = GLib.idle_add(priority, () => {
            this._transientSourceIds.delete(sourceId);
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            return callback();
        });
        this._transientSourceIds.add(sourceId);
        return sourceId;
    }

    private _removeSource(sourceId: number): void {
        if (sourceId === 0) return;
        this._transientSourceIds.delete(sourceId);
        GLib.source_remove(sourceId);
    }

    /* ── Cleanup ──────────────────────────────────────── */

    destroy(): void {
        if (this._destroyed) return;
        this.setLoading(false);
        this._destroyed = true;
        if (this._themeSignalId !== 0) {
            this._themeManager.disconnect(this._themeSignalId);
            this._themeSignalId = 0;
        }
        if (this._settings) {
            for (const signalId of this._settingsSignalIds) {
                this._settings.disconnect(signalId);
            }
        }
        this._settingsSignalIds = [];
        this._modelFetchCancellable?.cancel();
        this._modelFetchCancellable = null;
        this._modelFetchSession.abort();
        this._clearFocusTimeout();
        this._clearInputTimeouts();
        if (this._historyScrollTimeoutId !== 0) {
            GLib.source_remove(this._historyScrollTimeoutId);
            this._historyScrollTimeoutId = 0;
        }
        for (const sourceId of this._transientSourceIds) {
            GLib.source_remove(sourceId);
        }
        this._transientSourceIds.clear();
        this._container.remove_all_transitions();
        this._contentBox.remove_all_transitions();
        this._chatView.remove_all_transitions();
        this._historyView.remove_all_transitions();
        this._settingsView.remove_all_transitions();
        this._settingsScrollView.remove_all_transitions();
        this._settingsListBox.remove_all_transitions();
        this._stopCursorBlink();
        this._resetCopyState();
        if (this._menu) {
            Main.panel.menuManager.removeMenu(this._menu);
            Main.uiGroup.remove_child(this._menu.actor);
            this._menu.destroy();
        }
    }
}

function isRenderableRole(role: string): role is MessageRole {
    return role === 'user' || role === 'assistant';
}
