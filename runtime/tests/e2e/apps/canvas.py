"""A canvas-only GTK4 app for computer use's end-to-end test: one drawing area with a red square, and
nothing inside it that accessibility tools can see. Only a picture shows where the square is.

Every click appends a line to the file named in argv[1]: "hit" inside the square, else "miss x y".
"""

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

SQUARE = (220, 140, 60)  # x, y, size in the drawing area


def build(app: Gtk.Application, out: str) -> None:
    window = Gtk.ApplicationWindow(application=app, title="Mei test canvas", default_width=400, default_height=300)
    area = Gtk.DrawingArea(hexpand=True, vexpand=True)

    def draw(_area, cr, _width, _height) -> None:
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.paint()
        cr.set_source_rgb(0.85, 0.1, 0.1)
        x, y, size = SQUARE
        cr.rectangle(x, y, size, size)
        cr.fill()

    def clicked(_gesture, _n, x: float, y: float) -> None:
        sx, sy, size = SQUARE
        with open(out, "a") as f:
            f.write("hit\n" if sx <= x < sx + size and sy <= y < sy + size else f"miss {x:.0f} {y:.0f}\n")

    area.set_draw_func(draw)
    click = Gtk.GestureClick()
    click.connect("pressed", clicked)
    area.add_controller(click)
    window.set_child(area)
    window.present()


def main() -> None:
    app = Gtk.Application(application_id="org.andystmc.MeiTestCanvas", flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: build(a, sys.argv[1]))
    app.run([])


if __name__ == "__main__":
    main()
