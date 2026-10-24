"""A drag source for the nested-Shell e2e, standing in for Files: a window whose label drags a file
(argv[1] is an absolute path) or text (anything else), the way Files and a browser offer them.
Runs on the system's Python with PyGObject."""

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

PAYLOAD = sys.argv[1]


def content() -> Gdk.ContentProvider:
    if PAYLOAD.startswith("/"):
        files = Gdk.FileList.new_from_array([Gio.File.new_for_path(PAYLOAD)])
        return Gdk.ContentProvider.new_for_value(GObject.Value(Gdk.FileList, files))
    return Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", GLib.Bytes.new(PAYLOAD.encode()))


def build(app: Gtk.Application) -> None:
    window = Gtk.ApplicationWindow(application=app, title="Mei drag source", default_width=400, default_height=300)
    label = Gtk.Label(label="drag me", hexpand=True, vexpand=True)
    # Files offers copy and move: Mei must take a copy, or the file would leave its folder.
    source = Gtk.DragSource(actions=Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
    source.connect("prepare", lambda *_: content())
    label.add_controller(source)
    window.set_child(label)
    window.present()


app = Gtk.Application(application_id="org.andystmc.MeiDragSource", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", build)
app.run([])
