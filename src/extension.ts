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

import { DropZone } from './panel/dropZone.js';
import { MeiIndicator } from './panel/indicator.js';
import { ChatPopup } from './ui/chatPopup.js';
import { TaskNotifier } from './ui/notifier.js';
import { ThemeManager } from './utils/theme.js';
import { Logger, Tag } from './utils/logger.js';
import { BRIDGE_PATH, ShellBridge, focusedContext } from './runtime/bridge.js';
import { ComputerControl } from './runtime/control.js';
import { RuntimeChatController } from './runtime/controller.js';

export default class MeiExtension extends Extension {
    private _indicator: MeiIndicator | null = null;
    private _popup: ChatPopup | null = null;
    private _themeManager: ThemeManager | null = null;
    private _runtime: RuntimeChatController | null = null;
    private _bridge: ShellBridge | null = null;
    private _control: ComputerControl | null = null;
    private _notifier: TaskNotifier | null = null;
    private _dropZone: DropZone | null = null;
    private _devHooks: { destroy(): void } | null = null;
    private _settings: Gio.Settings | null = null;

    override enable(): void {
        Logger.info(Tag.Extension, 'Enabling Mei extension');
        this._themeManager = new ThemeManager();
        const runtime = new RuntimeChatController(BRIDGE_PATH);
        this._runtime = runtime;
        // Computer use's chip and kill switch (§10.3): they work even when the runtime doesn't answer.
        const control = new ComputerControl(reason => runtime.stopComputerUse(reason));
        this._control = control;
        // What only the Shell can do (windows, launching apps) for the runtime, and no other caller.
        this._bridge = new ShellBridge(() => runtime.runtimeOwner, active => control.show(active),
            () => this._popup?.close());
        this._bridge.export();

        this._indicator = new MeiIndicator();
        const popup = new ChatPopup(this._indicator.actor, this._themeManager, this.path);
        this._popup = popup;
        runtime.bind(popup);
        runtime.onStateChanged = () => this._syncIndicatorState();
        // Finished tasks and cards the popup isn't showing arrive as notifications; clicking one opens it.
        const notifier = new TaskNotifier(id => runtime.openConversation(id));
        this._notifier = notifier;
        runtime.onNotice = notice => notifier.notify(notice);

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
        popup.onLoadChat = id => {
            runtime.loadChat(id);
            notifier.dismiss(id);
        };
        popup.onDeleteChat = id => runtime.deleteChat(id);
        popup.onApprove = (id, scope) => runtime.approve(id, scope);
        popup.onDeny = id => runtime.deny(id);
        popup.onDenyWith = (id, text) => runtime.denyWith(id, text);
        popup.onAnswer = (id, value) => runtime.answer(id, value);
        popup.onResume = id => runtime.resume(id);
        popup.onStopTask = id => runtime.stopTask(id);
        popup.onRemoveAttachment = () => runtime.removeAttachment();
        // Files or text dragged from another app onto the button go with the next message (0027).
        this._dropZone = new DropZone(this._indicator.actor, `${this.path}/dropWindow.js`);
        this._dropZone.onDrop = drop => runtime.attachDrop(drop);
        popup.onDictate = () => runtime.dictate();
        popup.onVoice = () => runtime.voiceToggle();
        popup.onKeepMemory = id => runtime.keepMemory(id);
        popup.onForgetMemory = id => runtime.forgetMemory(id);
        popup.onOpenSettings = () => this.openPreferences();
        popup.onToggleExpand = isExpanded => {
            runtime.toggleExpand(isExpanded);
            this._syncIndicatorState();
        };
        popup.onOpenStateChanged = isOpen => {
            const current = runtime.currentConversation;
            if (isOpen && current && !popup.isShowingHistory) notifier.dismiss(current);
            this._syncIndicatorState();
        };
        // The first time the extension meets a runtime whose setup isn't done, open setup (§18.3).
        runtime.onSetupNeeded = () => this.openPreferences();

        this._settings = this.getSettings();
        // POPUP too: while Mei's popup is open it holds a grab, and the same keys should close it.
        const modes = Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW | Shell.ActionMode.POPUP;
        Main.wm.addKeybinding('open-shortcut', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, modes,
            () => popup.toggle());
        // Talk to Mei: listen, shown only in the top bar; the popup opens when Mei answers or needs
        // something (decision 0026). Again: send what was said, or with nothing said, stop.
        Main.wm.addKeybinding('voice-shortcut', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, modes,
            () => runtime.voiceListen());
        // The kill switch for computer use: never through the popup, which may be what's being driven.
        Main.wm.addKeybinding('stop-computer-shortcut', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT,
            modes | Shell.ActionMode.SYSTEM_MODAL, () => control.stop('Stopped with the keyboard shortcut'));
        // "Ask about this" (§18.4): the focused window and the selected text go with a new message.
        Main.wm.addKeybinding('ask-shortcut', this._settings, Meta.KeyBindingFlags.IGNORE_AUTOREPEAT, modes, () => {
            focusedContext()
                .then(attachment => {
                    if (this._runtime === runtime) runtime.askAbout(attachment);
                })
                .catch(e => Logger.warn(Tag.Extension, `Ask about this: ${(e as Error).message}`));
        });

        runtime.start();
        if (__DEV__ && GLib.getenv('MEI_DEV_HOOKS') === '1') {
            void import('./runtime/devHooks.js').then(({ DevHooks }) => {
                if (this._runtime === runtime) this._devHooks = new DevHooks(popup, runtime, notifier, this._dropZone);
            });
        }
        this._syncIndicatorState();
        Logger.info(Tag.Extension, 'Mei extension enabled');
    }

    override disable(): void {
        Logger.info(Tag.Extension, 'Disabling Mei extension');
        if (this._settings) {
            Main.wm.removeKeybinding('open-shortcut');
            Main.wm.removeKeybinding('ask-shortcut');
            Main.wm.removeKeybinding('voice-shortcut');
            Main.wm.removeKeybinding('stop-computer-shortcut');
        }
        this._settings = null;
        this._devHooks?.destroy();
        this._devHooks = null;
        this._dropZone?.destroy();
        this._dropZone = null;
        this._runtime?.destroy();
        this._runtime = null;
        this._notifier?.destroy();
        this._notifier = null;
        this._bridge?.destroy();
        this._bridge = null;
        this._control?.destroy();
        this._control = null;
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
        const busy = this._runtime?.isBusy ?? false;
        const waiting = this._runtime?.needsAttention ?? false;
        const popupOpen = Boolean(this._popup?.isOpen);
        const popupExpanded = Boolean(this._popup?.isExpanded);
        this._indicator.setStopControlVisible(isStreaming && !waiting && popupOpen && !popupExpanded);
        this._indicator.setActivity((isStreaming || busy || waiting) && !popupOpen);
        this._indicator.setVoiceState(this._runtime?.voiceState ?? 'off');
    }
}
