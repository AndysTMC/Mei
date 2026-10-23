/**
 * Test seam for dev builds: lets the nested-Shell end-to-end tests drive the popup and read what
 * it shows, since GNOME 50 doesn't allow Shell.Eval. Exported only when the bundle is built with
 * `--dev` and MEI_DEV_HOOKS=1 is set; production builds drop the import entirely (`__DEV__`).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import type { ChatPopup } from '../ui/chatPopup.js';
import type { TaskNotifier } from '../ui/notifier.js';
import type { RuntimeChatController } from './controller.js';

const OBJECT_PATH = '/com/andystmc/MeiDev';
const XML = `
<node>
  <interface name="com.andystmc.MeiDev">
    <method name="Send"><arg type="s" direction="in" name="text"/></method>
    <method name="Popup"><arg type="s" direction="in" name="action"/></method>
    <method name="State"><arg type="s" direction="out" name="json"/></method>
    <method name="Screenshot"><arg type="s" direction="in" name="path"/></method>
    <method name="Click"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/></method>
    <method name="Scroll"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/><arg type="i" direction="in" name="steps"/></method>
    <method name="PressOpenShortcut"/>
    <method name="PressAskShortcut"/>
    <method name="PressVoiceShortcut"/>
    <method name="PressStopShortcut"/>
    <method name="ActivateWindow"><arg type="s" direction="in" name="title"/><arg type="b" direction="out" name="found"/></method>
    <method name="SetPrimarySelection"><arg type="s" direction="in" name="text"/></method>
    <method name="ClickButton"><arg type="s" direction="in" name="label"/><arg type="b" direction="out" name="found"/></method>
    <method name="HoverButton"><arg type="s" direction="in" name="name"/><arg type="b" direction="out" name="found"/></method>
    <method name="ClickNamed"><arg type="s" direction="in" name="name"/><arg type="b" direction="out" name="found"/></method>
    <method name="ClickStageButton"><arg type="s" direction="in" name="label"/><arg type="b" direction="out" name="found"/></method>
    <method name="StageText"><arg type="s" direction="out" name="json"/></method>
    <method name="TypeText"><arg type="s" direction="in" name="text"/></method>
  </interface>
</node>`;

export class DevHooks {
    private readonly _exported: Gio.DBusExportedObject;
    // Made up front: the Shell adds a new input device asynchronously, and the first events sent
    // through one made on the spot can be lost (the first click of a test went nowhere).
    private readonly _pointer: Clutter.VirtualInputDevice;
    private readonly _keyboard: Clutter.VirtualInputDevice;
    /** Each ClickButton: was the button what the pointer was over, and did it say "clicked"? */
    private readonly _clicks: { label: string; picked: boolean; clicked: boolean }[] = [];

    constructor(private readonly _popup: ChatPopup, private readonly _runtime: RuntimeChatController,
        private readonly _notifier: TaskNotifier) {
        const seat = Clutter.get_default_backend().get_default_seat();
        this._pointer = seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        this._keyboard = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        this._exported = Gio.DBusExportedObject.wrapJSObject(XML, this);
        this._exported.export(Gio.DBus.session, OBJECT_PATH);
    }

    destroy(): void {
        this._exported.unexport();
    }

    Send(text: string): void {
        this._popup.onSend?.(text); // the same path a typed message takes
    }

    Popup(action: string): void {
        if (action === 'open') this._popup.open();
        else if (action === 'close') this._popup.close();
        else if (action === 'expand' && !this._popup.isExpanded) this._popup.toggleExpand();
        else if (action === 'collapse' && this._popup.isExpanded) this._popup.toggleExpand();
        else if (action === 'new') this._popup.onNewChat?.();
        else if (action === 'load-latest') this._runtime.debugLoadLatest();
        else if (action === 'reload-draft') this._popup.onReload?.(this._runtime.draftIndex);
        else if (action === 'activate-notice') this._activateNotice();
    }

    /** Clicks Mei's notification for the last notice, as a person clicking the banner would. */
    private _activateNotice(): void {
        const notice = this._runtime.debugState().notice as { conversationId: string } | null;
        if (notice) this._notifier.shownFor(notice.conversationId)?.activate();
    }

    /** Saves the whole screen as PNG (to see windows the hooks can't read, like Settings). */
    ScreenshotAsync([path]: [string], invocation: Gio.DBusMethodInvocation): void {
        const stream = Gio.File.new_for_path(path).replace(null, false, Gio.FileCreateFlags.NONE, null);
        const shooter = new Shell.Screenshot();
        shooter.screenshot(false, stream, (_s, res) => {
            try {
                shooter.screenshot_finish(res);
                stream.close(null);
                invocation.return_value(null);
            } catch (e) {
                invocation.return_dbus_error('com.andystmc.MeiDev.Error.Failed', String(e));
            }
        });
    }

    /** A left click at stage coordinates, for driving windows such as Settings. */
    Click(x: number, y: number): void {
        const t = GLib.get_monotonic_time();
        this._pointer.notify_absolute_motion(t, x, y);
        this._pointer.notify_button(t + 10_000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        this._pointer.notify_button(t + 20_000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
    }

    /** Wheel steps at stage coordinates: positive scrolls down. */
    Scroll(x: number, y: number, steps: number): void {
        const t = GLib.get_monotonic_time();
        this._pointer.notify_absolute_motion(t, x, y);
        const direction = steps > 0 ? Clutter.ScrollDirection.DOWN : Clutter.ScrollDirection.UP;
        for (let i = 0; i < Math.abs(steps); i++)
            this._pointer.notify_discrete_scroll(t + (i + 1) * 10_000, direction, Clutter.ScrollSource.WHEEL);
    }

    /** Clicks the popup's visible button with this label, where it is on screen, like a person would;
     * only if the button is what is there (not scrolled away or covered). Returns whether it exists. */
    ClickButton(label: string): boolean {
        const button = findButton(this._popup.contentActor, label);
        if (!button) return false;
        const [x, y] = button.get_transformed_position();
        const [w, h] = button.get_transformed_size();
        const at = [Math.round(x + w / 2), Math.round(y + h / 2)];
        const top = global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, at[0], at[1]);
        const record = { label, picked: top !== null && (top === button || button.contains(top)), clicked: false };
        this._clicks.push(record);
        if (!record.picked) return true;
        button.connect('clicked', () => {
            record.clicked = true;
        });
        this.Click(at[0], at[1]);
        return true;
    }

    /** Moves the pointer over the popup's last visible button with this accessible name (a reply's footer). */
    HoverButton(name: string): boolean {
        const at = this._named(name);
        if (at) this._pointer.notify_absolute_motion(GLib.get_monotonic_time(), at[0], at[1]);
        return at !== null;
    }

    /** Clicks the popup's last visible button with this accessible name. */
    ClickNamed(name: string): boolean {
        const at = this._named(name);
        if (at) this.Click(at[0], at[1]);
        return at !== null;
    }

    private _named(name: string): [number, number] | null {
        const buttons: St.Button[] = [];
        const walk = (actor: Clutter.Actor) => {
            if (!actor.visible) return;
            if (actor instanceof St.Button && actor.accessible_name === name) buttons.push(actor);
            actor.get_children().forEach(walk);
        };
        walk(this._popup.contentActor);
        const button = buttons.at(-1);
        if (!button) return null;
        const [x, y] = button.get_transformed_position();
        const [w, h] = button.get_transformed_size();
        return [Math.round(x + w / 2), Math.round(y + h / 2)];
    }

    /** Presses Super+Alt+M (the default open-shortcut) the way a keyboard would. */
    PressOpenShortcut(): void {
        this._press([Clutter.KEY_Super_L, Clutter.KEY_Alt_L, Clutter.KEY_m]);
    }

    /** Presses Super+Alt+A (the default ask-shortcut). */
    PressAskShortcut(): void {
        this._press([Clutter.KEY_Super_L, Clutter.KEY_Alt_L, Clutter.KEY_a]);
    }

    /** Presses Super+Alt+Space (the default voice-shortcut). */
    PressVoiceShortcut(): void {
        this._press([Clutter.KEY_Super_L, Clutter.KEY_Alt_L, Clutter.KEY_space]);
    }

    /** Presses Super+Alt+Escape (the default stop-computer-shortcut, computer use's kill switch). */
    PressStopShortcut(): void {
        this._press([Clutter.KEY_Super_L, Clutter.KEY_Alt_L, Clutter.KEY_Escape]);
    }

    /** Brings the window with this title to the front, as a person clicking it would. */
    ActivateWindow(title: string): boolean {
        const window = global.get_window_actors().map(a => a.get_meta_window()).find(w => w?.get_title() === title);
        window?.activate(global.get_current_time());
        return Boolean(window);
    }

    /** Selects text as if the person had highlighted it in some app. */
    SetPrimarySelection(text: string): void {
        St.Clipboard.get_default().set_text(St.ClipboardType.PRIMARY, text);
    }

    /** Clicks a visible button with this label anywhere in the Shell (a portal's consent dialog). */
    ClickStageButton(label: string): boolean {
        const button = findButton(global.stage, label);
        if (!button) return false;
        const [x, y] = button.get_transformed_position();
        const [w, h] = button.get_transformed_size();
        this.Click(Math.round(x + w / 2), Math.round(y + h / 2));
        return true;
    }

    /** Types text into whatever has keyboard focus, as a keyboard would. */
    TypeText(text: string): void {
        let t = GLib.get_monotonic_time();
        for (const ch of text) {
            const key = Clutter.unicode_to_keysym(ch.codePointAt(0) ?? 0);
            this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.PRESSED);
            this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.RELEASED);
        }
    }

    /** All visible text in the Shell (dialogs included), for tests that look for a dialog. */
    StageText(): string {
        return JSON.stringify(visibleText(global.stage));
    }

    private _press(keys: number[]): void {
        let t = GLib.get_monotonic_time();
        for (const key of keys) this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.PRESSED);
        for (const key of keys.reverse()) this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.RELEASED);
    }

    State(): string {
        const focused = global.display.focus_window;
        const focus = focused?.get_frame_rect();
        const buffer = focused?.get_buffer_rect();
        return JSON.stringify({
            popup: { open: this._popup.isOpen, expanded: this._popup.isExpanded },
            // Where the focused window is (Settings opens wherever the Shell places it).
            // The Shell takes no input until its startup animation is over: drive it only after.
            startingUp: Main.layoutManager._startingUp,
            window: focus ? {
                x: focus.x, y: focus.y, width: focus.width, height: focus.height,
                buffer: buffer ? { x: buffer.x, y: buffer.y, width: buffer.width, height: buffer.height } : null,
                monitor: focused?.get_monitor() ?? -1,
                title: focused?.get_title() ?? '',
            } : null,
            monitors: Main.layoutManager.monitors.map(m => ({
                x: m.x, y: m.y, width: m.width, height: m.height, scale: global.display.get_monitor_scale(m.index),
            })),
            clicks: this._clicks.slice(-5),
            shown: visibleText(this._popup.contentActor),
            controller: this._runtime.debugState(),
            // Every notification in the tray: Mei's own, and those the runtime sent while detached.
            notifications: Main.messageTray.getSources().flatMap(s => s.notifications.map(n =>
                ({ source: s.title, title: n.title, body: n.body }))),
        });
    }
}

function findButton(actor: Clutter.Actor, label: string): St.Button | null {
    if (!actor.visible) return null;
    if (actor instanceof St.Button && actor.get_label() === label && actor.reactive) return actor;
    for (const child of actor.get_children()) {
        const found = findButton(child, label);
        if (found) return found;
    }
    return null;
}

function visibleText(actor: Clutter.Actor): string[] {
    const out: string[] = [];
    const walk = (a: Clutter.Actor) => {
        if (!a.visible) return;
        if (a instanceof Clutter.Text) {
            const text = a.get_text();
            if (text.trim()) out.push(text);
        }
        for (const child of a.get_children()) walk(child);
    };
    walk(actor);
    return out;
}
