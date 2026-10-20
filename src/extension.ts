/**
 * Mei — AI assistant GNOME Shell extension.
 *
 * The extension is UI only (ADR 0002): the panel indicator and chat popup render what the Mei
 * runtime reports over D-Bus and send it commands. Conversations, providers, and settings live in
 * the runtime; nothing here calls a provider, writes files, or keeps chat state of its own.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import type Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import { MeiIndicator } from './panel/indicator.js';
import { ChatPopup } from './ui/chatPopup.js';
import { ThemeManager } from './utils/theme.js';
import { Logger, Tag } from './utils/logger.js';
import { RuntimeChatController } from './runtime/controller.js';

export default class MeiExtension extends Extension {
    private _indicator: MeiIndicator | null = null;
    private _popup: ChatPopup | null = null;
    private _themeManager: ThemeManager | null = null;
    private _runtime: RuntimeChatController | null = null;
    private _devHooks: { destroy(): void } | null = null;
    private _settings: Gio.Settings | null = null;

    override enable(): void {
        Logger.info(Tag.Extension, 'Enabling Mei extension');
        this._themeManager = new ThemeManager();
        const runtime = new RuntimeChatController();
        this._runtime = runtime;

        this._indicator = new MeiIndicator();
        const popup = new ChatPopup(this._indicator.actor, this._themeManager);
        this._popup = popup;
        runtime.bind(popup);
        runtime.onStateChanged = () => this._syncIndicatorState();

        this._indicator.onClicked = () => popup.toggle();
        this._indicator.onStopRequested = () => {
            runtime.cancel();
            popup.open();
        };
        popup.onSend = text => runtime.send(text);
        popup.onCancel = () => runtime.cancel();
        popup.onReload = index => runtime.reload(index);
        popup.onNewChat = () => runtime.newChat();
        popup.onHistoryRequested = () => runtime.showHistoryList();
        popup.onLoadChat = id => runtime.loadChat(id);
        popup.onDeleteChat = id => runtime.deleteChat(id);
        popup.onOpenSettings = () => this.openPreferences();
        popup.onToggleExpand = isExpanded => {
            runtime.toggleExpand(isExpanded);
            this._syncIndicatorState();
        };
        popup.onOpenStateChanged = () => this._syncIndicatorState();
        // The first time the extension meets a runtime whose setup isn't done, open setup (§18.3).
        runtime.onSetupNeeded = () => this.openPreferences();

        this._settings = this.getSettings();
        // POPUP too: while Mei's popup is open it holds a grab, and the same keys should close it.
        Main.wm.addKeybinding('open-shortcut', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW | Shell.ActionMode.POPUP, () => popup.toggle());

        runtime.start();
        if (__DEV__ && GLib.getenv('MEI_DEV_HOOKS') === '1') {
            void import('./runtime/devHooks.js').then(({ DevHooks }) => {
                if (this._runtime === runtime) this._devHooks = new DevHooks(popup, runtime);
            });
        }
        this._syncIndicatorState();
        Logger.info(Tag.Extension, 'Mei extension enabled');
    }

    override disable(): void {
        Logger.info(Tag.Extension, 'Disabling Mei extension');
        if (this._settings) Main.wm.removeKeybinding('open-shortcut');
        this._settings = null;
        this._devHooks?.destroy();
        this._devHooks = null;
        this._runtime?.destroy();
        this._runtime = null;
        this._popup?.destroy();
        this._popup = null;
        this._indicator?.destroy();
        this._indicator = null;
        this._themeManager?.destroy();
        this._themeManager = null;
        Logger.info(Tag.Extension, 'Mei extension disabled');
    }

    private _syncIndicatorState(): void {
        if (!this._indicator) return;
        const isStreaming = this._runtime?.isStreaming ?? false;
        const popupOpen = Boolean(this._popup?.isOpen);
        const popupExpanded = Boolean(this._popup?.isExpanded);
        this._indicator.setStopControlVisible(isStreaming && popupOpen && !popupExpanded);
        this._indicator.setActivity(isStreaming && !popupOpen);
    }
}
