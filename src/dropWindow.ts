/**
 * Mei's drop window (decision 0027): a borderless, see-through GTK4 window the Shell extension puts
 * under Mei's panel button while a drag from another app is over it. GNOME Shell sees a Wayland drag
 * pass over its own actors but never gets the data; a window of Mei's can. The Shell makes it a dock,
 * so it never takes focus or shows in the window list.
 *
 * Talks to the extension over its pipes: "show W H", "hide" and "quit" come in on stdin; each drop goes
 * out on stdout as one line (src/runtime/attachment.ts). Started by the Shell with cairo drawing: GL
 * costs ~200 ms on the first show, and by then the drop may already have happened (spike 0d).
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

import Gdk from 'gi://Gdk?version=4.0';
import Gio from 'gi://Gio';
import GioUnix from 'gi://GioUnix';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Gtk from 'gi://Gtk?version=4.0';

import { encodeDrop, type Drop } from './runtime/attachment.js';

const stdout = new GioUnix.OutputStream({ fd: 1, close_fd: false });

/** Local files by path; files that aren't local (a link from a browser) go as their address, as text. */
function toDrop(value: unknown): Drop | null {
    if (typeof value === 'string') return value.trim() ? { kind: 'text', text: value } : null;
    if (!(value instanceof Gdk.FileList)) return null;
    const files = value.get_files();
    const paths = files.map(f => f.get_path()).filter((p): p is string => p !== null);
    if (paths.length) return { kind: 'files', paths };
    const uris = files.map(f => f.get_uri()).join('\n');
    return uris ? { kind: 'text', text: uris } : null;
}

function send(drop: Drop): void {
    stdout.write_all(new TextEncoder().encode(`${encodeDrop(drop)}\n`), null);
    stdout.flush(null);
}

// An application, not a bare main loop: under one, the reads from the Shell's pipe never completed.
const app = new Gtk.Application({ application_id: 'com.andystmc.Mei.Drop', flags: Gio.ApplicationFlags.NON_UNIQUE });
app.connect('activate', () => {
    app.hold();
    const css = new Gtk.CssProvider();
    // Not fully clear: GTK commits nothing for a window with nothing to draw, so it would never map. It
    // sits under the top bar anyway; 1% black is never seen.
    css.load_from_string('window { background: rgba(0, 0, 0, 0.01); }');
    const display = Gdk.Display.get_default();
    if (display) Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);

    const window = new Gtk.Window({ application: app, title: 'Mei', decorated: false, resizable: false, default_width: 1, default_height: 1 });
    const area = new Gtk.Box({ hexpand: true, vexpand: true });
    window.set_child(area);
    // Copy only: a drag from Files that ended in a move would take the file away from where it was.
    const target = new Gtk.DropTarget({ actions: Gdk.DragAction.COPY });
    target.set_gtypes([Gdk.FileList.$gtype, GObject.TYPE_STRING]);
    target.connect('drop', (_target: Gtk.DropTarget, value: unknown) => {
        const drop = toDrop(value);
        if (drop) send(drop);
        return drop !== null;
    });
    area.add_controller(target);

    const input = new Gio.DataInputStream({ base_stream: new GioUnix.InputStream({ fd: 0, close_fd: false }) });
    function readCommand(): void {
        input.read_line_async(GLib.PRIORITY_DEFAULT, null, (_stream, res) => {
            let line: string | null = null;
            try {
                [line] = input.read_line_finish_utf8(res);
            } catch {
                line = null;
            }
            const [command, width, height] = (line ?? 'quit').split(' ');
            if (command === 'quit') {
                app.quit();
                return;
            }
            if (command === 'show') {
                window.set_default_size(Math.max(1, Number(width) || 1), Math.max(1, Number(height) || 1));
                window.present();
            } else if (command === 'hide') {
                window.set_visible(false);
            }
            readCommand();
        });
    }
    readCommand();
});
app.run([]);
