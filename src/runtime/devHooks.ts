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

import type { ChatPopup } from '../ui/chatPopup.js';
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
    <method name="PressOpenShortcut"/>
  </interface>
</node>`;

export class DevHooks {
    private readonly _exported: Gio.DBusExportedObject;
    private _pointer: Clutter.VirtualInputDevice | null = null;
    private _keyboard: Clutter.VirtualInputDevice | null = null;

    constructor(private readonly _popup: ChatPopup, private readonly _runtime: RuntimeChatController) {
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
        this._pointer ??= Clutter.get_default_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
        const t = GLib.get_monotonic_time();
        this._pointer.notify_absolute_motion(t, x, y);
        this._pointer.notify_button(t + 10_000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);
        this._pointer.notify_button(t + 20_000, Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED);
    }

    /** Presses Super+Alt+M (the default open-shortcut) the way a keyboard would. */
    PressOpenShortcut(): void {
        this._keyboard ??= Clutter.get_default_backend().get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
        const keys = [Clutter.KEY_Super_L, Clutter.KEY_Alt_L, Clutter.KEY_m];
        let t = GLib.get_monotonic_time();
        for (const key of keys) this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.PRESSED);
        for (const key of keys.reverse()) this._keyboard.notify_keyval(t += 10_000, key, Clutter.KeyState.RELEASED);
    }

    State(): string {
        return JSON.stringify({
            popup: { open: this._popup.isOpen, expanded: this._popup.isExpanded },
            shown: visibleText(this._popup.contentActor),
            controller: this._runtime.debugState(),
        });
    }
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
