"""Spike 0b, coordinates: two virtual monitors at 100/125/150 %. GTK4 on Wayland reports AT-SPI extents
relative to its window only; the Shell knows where the window is. For each scale and monitor: open
Calculator there, add its "7" button's window extents to the window's frame (or buffer) origin,
click that point as a person would, and see whether the display says 7."""

import sys
import time

from gi.repository import Atspi, GLib

from shell import Shell, app_named, find, press, save, text_of, walk

DC = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig")
CONFIGS = [(1.0, 1.0), (1.25, 1.5), (1.5, 1.25)]


def apply_scales(shell: Shell, scales: tuple[float, ...]) -> list[dict]:
    serial, monitors, _logical, _props = shell.call("GetCurrentState", iface=DC)
    layout, x = [], 0
    for (spec, modes, _mprops), wanted in zip(monitors, scales):
        connector = spec[0]
        mode = next(m for m in modes if m[6].get("is-current", False)) if any(m[6].get("is-current") for m in modes) else modes[0]
        mode_id, width, height, supported = mode[0], mode[1], mode[2], mode[5]
        scale = min(supported, key=lambda s: abs(s - wanted))
        layout.append((x, 0, scale, 0, x == 0, [(connector, mode_id, {})]))
        x += round(width / scale)
    shell.call("ApplyMonitorsConfig", "uua(iiduba(ssa{sv}))a{sv}", serial, 1, layout, {}, iface=DC)
    time.sleep(1.5)
    return shell.state()["monitors"]


def display(app) -> str:
    texts = [text_of(n) for n in walk(app, 400) if n.get_role_name() in ("text", "label", "editbar", "entry")]
    return " | ".join(t for t in texts if t.strip())[:200]


def trial(shell: Shell, monitor: dict) -> dict:
    # A new window opens where the pointer is: move it there (no click), then open Calculator.
    shell.call("Scroll", "iii", monitor["x"] + monitor["width"] // 2, monitor["y"] + monitor["height"] // 2, 0)
    time.sleep(0.3)
    shell.launch(["gnome-calculator"])
    app = app_named("calculator", timeout=30)
    if app is None:
        return {"error": "Calculator didn't appear"}
    time.sleep(1.5)
    clear = find(app, "button", "C") or find(app, "button", "Clear")
    if clear:
        press(clear)
    seven = find(app, "button", "7")
    ext = Atspi.Component.get_extents(seven, Atspi.CoordType.WINDOW)
    window = shell.state()["window"]
    out = {"monitor": monitor, "window": window, "extents": [ext.x, ext.y, ext.width, ext.height], "tries": []}
    for origin in ("frame", "buffer"):
        base = window if origin == "frame" else window["buffer"]
        x, y = base["x"] + ext.x + ext.width / 2, base["y"] + ext.y + ext.height / 2
        before = display(app)
        shell.click(x, y)
        time.sleep(0.4)
        after = display(app)
        hit = "7" in after and after != before
        out["tries"].append({"origin": origin, "at": [round(x), round(y)], "hit": hit, "display": after})
        if hit:
            break
    return out


def main() -> None:
    out = sys.argv[1]
    shell = Shell(out)
    shell.start()
    shell.enable_accessibility()
    Atspi.init()
    results = []
    try:
        for scales in CONFIGS:
            try:
                monitors = apply_scales(shell, scales)
            except GLib.Error as e:
                results.append({"scales": scales, "error": e.message})
                continue
            for index, monitor in enumerate(monitors):
                r = trial(shell, monitor)
                r["scales"] = scales
                r["on"] = index
                results.append(r)
                shell.screenshot(f"coords-{scales[0]}-{scales[1]}-m{index}")
                for app in shell.apps:
                    app.terminate()
                shell.apps.clear()
                time.sleep(1.5)
                tries = r.get("tries", [])
                print(scales, "monitor", index, monitor.get("scale"), [(t["origin"], t["hit"]) for t in tries], r.get("error", ""),
                      flush=True)
    finally:
        save(out, "coords", results)
        shell.stop()


if __name__ == "__main__":
    main()
