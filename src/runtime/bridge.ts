/**
 * The ShellBridge (§12.6): the few things only the Shell can do, offered to the Mei runtime.
 *
 * Exported on the extension's own session-bus connection and named in Hello. Only the unique name
 * that owns `com.andystmc.Mei1` right now may call it; anyone else gets AccessDenied. Methods take
 * and return one JSON string, like the runtime's interface.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

import { Logger, Tag } from '../utils/logger.js';

export const BRIDGE_PATH = '/com/andystmc/Mei1/ShellBridge';
const INTERFACE = 'com.andystmc.Mei1.ShellBridge';
const XML = `<node><interface name="${INTERFACE}">
  <method name="ListWindows"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
  <method name="LaunchApp"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>
</interface></node>`;

export interface WindowInfo {
    app_id: string;
    title: string;
    focused: boolean;
}

export class ShellBridge {
    private _id = 0;

    /** `_runtime`: the runtime's current unique name, or null while it isn't running. */
    constructor(private readonly _runtime: () => string | null) {}

    export(): void {
        const info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0];
        this._id = Gio.DBus.session.register_object(BRIDGE_PATH, info,
            (_conn, sender, _path, _iface, method, params, invocation) => this._call(sender, method, params, invocation),
            null, null);
    }

    destroy(): void {
        if (this._id) Gio.DBus.session.unregister_object(this._id);
        this._id = 0;
    }

    private _call(sender: string, method: string, params: GLib.Variant, invocation: Gio.DBusMethodInvocation): void {
        const runtime = this._runtime();
        if (!runtime || sender !== runtime) {
            Logger.warn(Tag.Extension, `Refused a ShellBridge call from ${sender}`);
            invocation.return_dbus_error('org.freedesktop.DBus.Error.AccessDenied', 'Only the Mei runtime may call this.');
            return;
        }
        let args: Record<string, unknown>;
        try {
            args = JSON.parse((params.deepUnpack() as [string])[0]) as Record<string, unknown>;
        } catch {
            invocation.return_dbus_error('org.freedesktop.DBus.Error.InvalidArgs', 'Expected one JSON object.');
            return;
        }
        try {
            const result = method === 'ListWindows' ? { windows: listWindows() } : launchApp(args);
            invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(result)]));
        } catch (e) {
            invocation.return_dbus_error('com.andystmc.Mei1.Error.Failed', e instanceof Error ? e.message : String(e));
        }
    }
}

export function listWindows(): WindowInfo[] {
    const tracker = Shell.WindowTracker.get_default();
    return global.get_window_actors()
        .map(actor => actor.get_meta_window())
        .filter(w => w !== null && !w.is_skip_taskbar())
        .map(w => ({
            app_id: tracker.get_window_app(w!)?.get_id() ?? '',
            title: w!.get_title() ?? '',
            focused: w!.has_focus(),
        }));
}

/** Open an app as the person would from the Shell, optionally with files (file:// URIs only). */
function launchApp(args: Record<string, unknown>): Record<string, never> {
    const id = String(args.app_id ?? '');
    const app = Shell.AppSystem.get_default().lookup_app(id.endsWith('.desktop') ? id : `${id}.desktop`);
    if (!app) throw new Error(`No app ${id} is installed.`);
    const uris = (Array.isArray(args.uris) ? args.uris : []).filter((u): u is string =>
        typeof u === 'string' && u.startsWith('file://'));
    if (uris.length) app.get_app_info().launch_uris(uris, global.create_app_launch_context(0, -1));
    else app.activate();
    return {};
}
