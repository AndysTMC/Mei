"""A GTK4 form for computer use's end-to-end test: Name, Email, a checkbox, a password field, Submit.

Submitting writes what the form holds to the file named in argv[1]: the fields' text, the checkbox,
and only whether the password field has anything in it. Runs on the system's Python with PyGObject.
"""

import json
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402


def build(app: Gtk.Application, out: str) -> None:
    window = Gtk.ApplicationWindow(application=app, title="Mei test form", default_width=420, default_height=380)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=16, margin_bottom=16, margin_start=16,
                  margin_end=16)

    def field(label: str, entry: Gtk.Widget) -> Gtk.Widget:
        box.append(Gtk.Label(label=label, xalign=0))
        entry.update_property([Gtk.AccessibleProperty.LABEL], [label])
        box.append(entry)
        return entry

    name = field("Name", Gtk.Entry())
    email = field("Email", Gtk.Entry())
    news = Gtk.CheckButton(label="Send me news")
    box.append(news)
    password = field("Password", Gtk.PasswordEntry())
    submit = Gtk.Button(label="Submit")
    status = Gtk.Label(label="")
    box.append(submit)
    box.append(status)

    def submitted(_button: Gtk.Button) -> None:
        with open(out, "w") as f:
            json.dump({"name": name.get_text(), "email": email.get_text(), "news": news.get_active(),
                       "password_filled": bool(password.get_text())}, f)
        status.set_label("Submitted")

    submit.connect("clicked", submitted)
    window.set_child(box)
    window.present()


def main() -> None:
    app = Gtk.Application(application_id="org.andystmc.MeiTestForm", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: build(a, sys.argv[1]))
    app.run([])


if __name__ == "__main__":
    main()
