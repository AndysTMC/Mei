"""Spike 0d: a drag source, as Files would be. A window whose label drags a file (argv[2] == "file")
or text ("text"); logs how each drag ended to argv[1]. System Python with PyGObject."""

import json
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

LOG, PAYLOAD = sys.argv[1], sys.argv[2]


def note(what: str, **data) -> None:
    with open(LOG, "a") as f:
        f.write(json.dumps({"t": round(time.monotonic() * 1000, 1), "what": what, **data}) + "\n")


def content() -> Gdk.ContentProvider:
    if PAYLOAD.startswith("/"):
        files = Gdk.FileList.new_from_array([Gio.File.new_for_path(PAYLOAD)])
        value = GObject.Value(Gdk.FileList, files)
        return Gdk.ContentProvider.new_for_value(value)
    return Gdk.ContentProvider.new_for_bytes("text/plain;charset=utf-8", GLib.Bytes.new(PAYLOAD.encode()))


def build(app: Gtk.Application) -> None:
    window = Gtk.ApplicationWindow(application=app, title="Mei drag source", default_width=400, default_height=300)
    label = Gtk.Label(label="drag me", hexpand=True, vexpand=True)
    source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
    source.connect("prepare", lambda *_: content())
    source.connect("drag-begin", lambda *_: note("drag-begin"))
    source.connect("drag-end", lambda _s, _d, delete: note("drag-end", delete=delete))
    source.connect("drag-cancel", lambda _s, _d, reason: note("drag-cancel", reason=reason.value_nick) or False)
    label.add_controller(source)
    window.set_child(label)
    window.present()
    note("shown")


app = Gtk.Application(application_id="org.andystmc.MeiDragSource", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.connect("activate", build)
app.run([])
