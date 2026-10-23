/**
 * The ShellBridge (§12.6): the few things only the Shell can do, offered to the Mei runtime: list
 * and focus windows, open apps, read and set the clipboard, and say how long the person has been idle.
 *
 * Exported on the extension's own session-bus connection and named in Hello. Only the unique name
 * that owns `com.andystmc.Mei1` right now may call it; anyone else gets AccessDenied. Methods take
 * and return one JSON string, like the runtime's interface.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import type Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import { Logger, Tag } from '../utils/logger.js';
import { makeAttachment } from './attachment.js';
import type { Attachment } from './protocol.js';

export const BRIDGE_PATH = '/com/andystmc/Mei1/ShellBridge';
const INTERFACE = 'com.andystmc.Mei1.ShellBridge';
const METHODS = [
    'ListWindows', 'LaunchApp', 'FocusWindow', 'ClipboardGet', 'ClipboardSet', 'GetIdleTime', 'GetMonitors',
] as const;
const XML = `<node><interface name="${INTERFACE}">${METHODS.map(m =>
    `<method name="${m}"><arg type="s" direction="in"/><arg type="s" direction="out"/></method>`).join('')}
</interface></node>`;
const MAX_CLIPBOARD = 20_000;

type Handler = (args: Record<string, unknown>) => Promise<object> | object;

const HANDLERS: Record<(typeof METHODS)[number], Handler> = {
    ListWindows: () => ({ windows: listWindows() }),
    LaunchApp: args => launchApp(args),
    FocusWindow: args => focusWindow(Number(args.id)),
    ClipboardGet: () => clipboardGet(),
    ClipboardSet: args => {
        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, String(args.text ?? '').slice(0, MAX_CLIPBOARD));
        return {};
    },
    GetIdleTime: () => ({ ms: global.backend.get_core_idle_monitor().get_idletime() }),
    GetMonitors: () => ({ monitors: listMonitors() }),
};

interface Rect {
    x: number;
    y: number;
    width: number;
    height: number;
}

export interface WindowInfo {
    id: number;
    app_id: string;
    title: string;
    focused: boolean;
    pid: number;
    // Stage coordinates. Computer use anchors AT-SPI's window-relative extents at the buffer's origin
    // (decision 0022): the frame leaves out the client-side shadow.
    buffer: Rect;
    frame: Rect;
    monitor: number;
}

interface MonitorInfo extends Rect {
    index: number;
    scale: number;
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
        const handler = HANDLERS[method as (typeof METHODS)[number]];
        Promise.resolve()
            .then(() => handler(args))
            .then(result => invocation.return_value(new GLib.Variant('(s)', [JSON.stringify(result)])))
            .catch(e => invocation.return_dbus_error('com.andystmc.Mei1.Error.Failed',
                e instanceof Error ? e.message : String(e)));
    }
}

function normalWindows(): Meta.Window[] {
    return global.get_window_actors()
        .map(actor => actor.get_meta_window())
        .filter((w): w is Meta.Window => w !== null && !w.is_skip_taskbar());
}

export function listWindows(): WindowInfo[] {
    const tracker = Shell.WindowTracker.get_default();
    return normalWindows().map(w => ({
        id: w.get_id(),
        app_id: tracker.get_window_app(w)?.get_id() ?? '',
        title: w.get_title() ?? '',
        focused: w.has_focus(),
        pid: w.get_pid(),
        buffer: rect(w.get_buffer_rect()),
        frame: rect(w.get_frame_rect()),
        monitor: w.get_monitor(),
    }));
}

function listMonitors(): MonitorInfo[] {
    const display = global.display;
    return Array.from({ length: display.get_n_monitors() }, (_, index) => ({
        index,
        ...rect(display.get_monitor_geometry(index)),
        scale: display.get_monitor_scale(index),
    }));
}

function rect(r: { x: number; y: number; width: number; height: number }): Rect {
    return { x: r.x, y: r.y, width: r.width, height: r.height };
}

function focusWindow(id: number): Record<string, never> {
    const window = normalWindows().find(w => w.get_id() === id);
    if (!window) throw new Error(`No window ${id} is open.`);
    window.activate(global.get_current_time());
    return {};
}

/** For "Ask about this": the focused window, and the text selected anywhere (the primary selection). */
export function focusedContext(): Promise<Attachment | null> {
    const window = global.display.get_focus_window();
    const appId = window ? Shell.WindowTracker.get_default().get_window_app(window)?.get_id() ?? '' : '';
    const title = window?.get_title() ?? '';
    return new Promise(resolve => St.Clipboard.get_default().get_text(St.ClipboardType.PRIMARY,
        (_clipboard, text) => resolve(makeAttachment(appId, title, text ?? ''))));
}

function clipboardGet(): Promise<{ text: string }> {
    return new Promise(resolve => St.Clipboard.get_default().get_text(St.ClipboardType.CLIPBOARD,
        (_clipboard, text) => resolve({ text: (text ?? '').slice(0, MAX_CLIPBOARD) })));
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
