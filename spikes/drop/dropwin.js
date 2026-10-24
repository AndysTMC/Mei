// Spike 0d: the drop window. A borderless GTK4 window with a DropTarget for files and text, shown and
// hidden by lines on stdin ("show W H", "hide", "quit"); logs what reached it to $MEI_DROP_LOG.

import Gdk from 'gi://Gdk?version=4.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import GioUnix from 'gi://GioUnix';
import Gtk from 'gi://Gtk?version=4.0';

const started = GLib.get_monotonic_time() / 1000;
const out = Gio.File.new_for_path(GLib.getenv('MEI_DROP_LOG') ?? '/dev/null').append_to(Gio.FileCreateFlags.NONE, null);
const note = (what, data = {}) => {
    out.write_all(new TextEncoder().encode(JSON.stringify({ t: Math.round(GLib.get_monotonic_time() / 100) / 10, what, ...data }) + '\n'), null);
    out.flush(null);
};

const app = new Gtk.Application({ application_id: 'com.andystmc.MeiDropSpike', flags: Gio.ApplicationFlags.NON_UNIQUE });
app.connect('activate', () => {
    note('activated', { startupMs: Math.round(GLib.get_monotonic_time() / 1000 - started) });
    app.hold();
    const window = new Gtk.Window({ application: app, title: 'Mei drop', decorated: false, resizable: false,
        default_width: 40, default_height: 30 });
    const css = new Gtk.CssProvider();
    css.load_from_string('window { background: rgba(128,128,128,0.35); }');
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);
    const area = new Gtk.Box({ hexpand: true, vexpand: true });
    window.set_child(area);
    const target = new Gtk.DropTarget({ actions: Gdk.DragAction.COPY });
    target.set_gtypes([Gdk.FileList.$gtype, GObject.TYPE_STRING]);
    target.connect('enter', (_t, x, y) => {
        note('enter', { x, y, formats: target.get_current_drop()?.get_formats().to_string() });
        return Gdk.DragAction.COPY;
    });
    target.connect('leave', () => note('leave'));
    target.connect('drop', (_t, value) => {
        if (value instanceof Gdk.FileList) note('drop', { files: value.get_files().map(f => f.get_path()) });
        else note('drop', { text: String(value) });
        return true;
    });
    area.add_controller(target);
    if (GLib.getenv('MEI_DROP_REALIZE')) {
        window.realize();
        note('realized');
    }
    window.connect('notify::is-active', () => note('is-active', { active: window.is_active }));

    const input = new Gio.DataInputStream({ base_stream: new GioUnix.InputStream({ fd: 0, close_fd: false }) });
    const read = () => input.read_line_async(GLib.PRIORITY_DEFAULT, null, (_s, res) => {
        const [line] = input.read_line_finish_utf8(res);
        if (line === null) {
            app.quit();
            return;
        }
        const [cmd, w, h] = line.split(' ');
        note('cmd', { line });
        if (cmd === 'show') {
            window.set_default_size(Number(w), Number(h));
            window.present();
        } else if (cmd === 'hide') {
            window.set_visible(false);
        } else if (cmd === 'quit') {
            app.quit();
            return;
        }
        read();
    });
    read();
});
app.run([]);
