/**
 * What the file viewers share (decision 0034): reading the start of a file, loading a picture fitted
 * to a size, monospace text, and every file page's two actions, "Open in its app" and "Show in
 * Files". Files are only read: nothing here writes, renames or moves them.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Clutter from 'gi://Clutter';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import type { PdfInfoReply, PdfPageReply } from '../../runtime/protocol.js';
import { Logger, Tag } from '../../utils/logger.js';
import { cardButton } from '../conversation/cards.js';
import type { PageContent } from '../popup/largePage.js';
import type { Size } from '../popup/pageSize.js';

/** Where a viewer is shown, and what it may ask for beyond the file itself. */
export interface ViewerHost {
    /** The room under the page's top bar. */
    readonly bodySize: Size;
    setTitle(title: string): void;
    /** Show another content in this one's place (a viewer falling back to "anything else"). */
    replace(content: PageContent): void;
    /** The runtime draws PDF pages (the Shell has no Poppler); null without its tools. */
    readonly pdf: PdfPages | null;
    /** A file was opened in its app or shown in Files: the popup makes way. */
    onLeft(): void;
}

export interface PdfPages {
    info(path: string): Promise<PdfInfoReply>;
    page(path: string, page: number, width: number): Promise<PdfPageReply>;
}

export function baseName(path: string): string {
    return path.slice(path.lastIndexOf('/') + 1) || path;
}

/** The page's actions for a file on disk. */
export function fileActions(path: string, host: ViewerHost): St.Button[] {
    const open = cardButton('Open in its app', `Open ${baseName(path)} in its app`);
    open.connect('clicked', () => {
        openInApp(path);
        host.onLeft();
    });
    const show = cardButton('Show in Files', `Show ${baseName(path)} in Files`);
    show.connect('clicked', () => {
        showInFiles(path);
        host.onLeft();
    });
    return [open, show];
}

function openInApp(path: string): void {
    const context = global.create_app_launch_context(global.get_current_time(), -1);
    Gio.AppInfo.launch_default_for_uri_async(Gio.File.new_for_path(path).get_uri(), context, null,
        (_source: unknown, result: Gio.AsyncResult) => {
            try {
                Gio.AppInfo.launch_default_for_uri_finish(result);
            } catch (e) {
                Logger.warn(Tag.UI, `Opening a file in its app: ${(e as Error).message}`);
            }
        });
}

/** Files' own D-Bus interface: opens the folder with the file selected. */
function showInFiles(path: string): void {
    Gio.DBus.session.call('org.freedesktop.FileManager1', '/org/freedesktop/FileManager1', 'org.freedesktop.FileManager1',
        'ShowItems', new GLib.Variant('(ass)', [[Gio.File.new_for_path(path).get_uri()], '']), null,
        Gio.DBusCallFlags.NONE, -1, null, (_bus: Gio.DBusConnection | null, result: Gio.AsyncResult) => {
            try {
                Gio.DBus.session.call_finish(result);
            } catch (e) {
                Logger.warn(Tag.UI, `Showing a file in Files: ${(e as Error).message}`);
            }
        });
}

export interface FileHead {
    bytes: Uint8Array;
    /** The whole file's size. */
    size: number;
}

/** The first `max` bytes of a file, and its size, without blocking the Shell. */
export function readHead(path: string, max: number): Promise<FileHead> {
    const file = Gio.File.new_for_path(path);
    return new Promise((resolve, reject) => {
        file.query_info_async('standard::size', Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, null, (_f, infoResult) => {
            let size: number;
            try {
                size = file.query_info_finish(infoResult).get_size();
            } catch (e) {
                reject(e);
                return;
            }
            file.read_async(GLib.PRIORITY_DEFAULT, null, (_s, readResult) => {
                let stream: Gio.FileInputStream;
                try {
                    stream = file.read_finish(readResult);
                } catch (e) {
                    reject(e);
                    return;
                }
                const chunks: Uint8Array[] = [];
                let total = 0;
                // read_bytes may return less than asked; keep going until `max` or the end.
                const next = (): void => {
                    stream.read_bytes_async(Math.min(64 * 1024, max - total), GLib.PRIORITY_DEFAULT, null, (_st, result) => {
                        try {
                            const chunk = stream.read_bytes_finish(result).toArray();
                            if (chunk.length > 0) {
                                chunks.push(chunk);
                                total += chunk.length;
                            }
                            if (chunk.length > 0 && total < max) {
                                next();
                                return;
                            }
                            stream.close_async(GLib.PRIORITY_DEFAULT, null, null);
                            const bytes = new Uint8Array(total);
                            let at = 0;
                            for (const c of chunks) {
                                bytes.set(c, at);
                                at += c.length;
                            }
                            resolve({ bytes, size });
                        } catch (e) {
                            reject(e);
                        }
                    });
                };
                next();
            });
        });
    });
}

/**
 * A picture loaded off the main loop, fitted within `room` (stage pixels) with its aspect kept and
 * never enlarged; null room: its own size. St's loader fills whatever box it is given, so the fitted
 * box is worked out first, from `natural` or the file's header.
 */
export function loadPicture(path: string, room: Size | null, natural: Size | null = null): Clutter.Actor {
    const scale = St.ThemeContext.get_for_stage(global.stage).scale_factor;
    const file = Gio.File.new_for_path(path);
    const box = room ? fitted(room, natural ?? headerSize(path)) ?? room : null;
    const actor = St.TextureCache.get_default().load_file_async(file, box ? Math.max(1, Math.floor(box.width / scale)) : -1,
        box ? Math.max(1, Math.floor(box.height / scale)) : -1, scale, 1);
    // At its own size wherever it is put, and never drawn out of shape if a parent gives it more.
    actor.x_align = actor.y_align = Clutter.ActorAlign.CENTER;
    actor.content_gravity = Clutter.ContentGravity.RESIZE_ASPECT;
    return actor;
}

/** The largest box of `natural`'s shape within `room`, no larger than `natural`; null: shape unknown. */
export function fitted(room: Size, natural: Size | null): Size | null {
    if (!natural || natural.width <= 0 || natural.height <= 0) return null;
    const k = Math.min(1, room.width / natural.width, room.height / natural.height);
    return { width: Math.max(1, Math.round(natural.width * k)), height: Math.max(1, Math.round(natural.height * k)) };
}

/** An image's size from its header (GdkPixbuf reads only that much). */
function headerSize(path: string): Size | null {
    const [format, width, height] = GdkPixbuf.Pixbuf.get_file_info(path);
    return format ? { width, height } : null;
}

/** Read-only monospace text that can be selected and copied, scrolling both ways. */
export function monoText(text: string): St.ScrollView {
    const label = new St.Label({ text, style_class: 'mei-viewer-mono', reactive: true });
    label.clutter_text.selectable = true;
    label.clutter_text.editable = false;
    label.clutter_text.line_wrap = false;
    const box = new St.BoxLayout({ vertical: true, x_expand: true });
    box.add_child(label);
    return scrolling(box, true);
}

export function scrolling(child: St.BoxLayout, both = false): St.ScrollView {
    const scroll = new St.ScrollView({ style_class: 'mei-scroll mei-viewer-scroll', x_expand: true, y_expand: true,
        overlay_scrollbars: true });
    scroll.set_policy(both ? St.PolicyType.AUTOMATIC : St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
    scroll.set_child(child);
    return scroll;
}

/** A quiet line in the middle of the page: loading, or why nothing shows. */
export function centeredNote(text: string): St.Label {
    return new St.Label({ text, style_class: 'mei-card-muted', x_expand: true, y_expand: true,
        x_align: Clutter.ActorAlign.CENTER, y_align: Clutter.ActorAlign.CENTER });
}

/** Bytes as people read them (GLib's own "4.2 MB"). */
export function formatSize(bytes: number): string {
    return GLib.format_size(bytes);
}
