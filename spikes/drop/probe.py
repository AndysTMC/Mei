"""Spike 0d driver: in a private headless GNOME Shell, drag a file (and text) from a GTK4 app onto a
stand-in for Mei's panel button, in each mode the spike extension has, and print what reached whom
and when. Throwaway; system Python with PyGObject. Run through run.sh."""

import json
import os
import re
import subprocess
import sys
import time

from gi.repository import Gio, GLib

OUT = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE = ("org.gnome.Shell", "/com/andystmc/MeiDndSpike", "com.andystmc.MeiDndSpike")
bus = Gio.bus_get_sync(Gio.BusType.SESSION)


def call(member: str, sig: str | None = None, *args):
    params = GLib.Variant(f"({sig})", args) if sig else None
    reply = bus.call_sync(*SPIKE, member, params, None, Gio.DBusCallFlags.NONE, 10_000, None)
    return reply.unpack()[0] if reply and reply.n_children() else None


def lines(path: str) -> list[dict]:
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else []


def wait_for(pred, timeout: float, what: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = pred()
            if value:
                return value
        except GLib.Error:
            pass
        time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {what}")


def scenario(name: str, mode: str, payload: str, **drag) -> dict:
    drop_log = os.path.join(OUT, "drop.log")
    source_log = os.path.join(OUT, f"source-{name}.log")
    for path in (drop_log, source_log):
        if os.path.exists(path):
            os.remove(path)
    call("Reset")
    display = re.findall(r"Using Wayland display name '([^']+)'", open(os.path.join(OUT, "shell.log")).read())[-1]
    env = {**os.environ, "GDK_BACKEND": "wayland", "WAYLAND_DISPLAY": display}
    app = subprocess.Popen(["/usr/bin/python3", os.path.join(HERE, "source.py"), source_log, payload], env=env)
    try:
        src = wait_for(lambda: next((w for w in json.loads(call("Targets"))["windows"]
                                     if w["title"] == "Mei drag source"), None), 15, "the source window")
        time.sleep(0.5)
        call("SetMode", "s", mode)
        time.sleep(1.0)  # a resident drop window starts (and, for "twice", shows and hides once)
        targets = json.loads(call("Targets"))
        b = targets["button"]
        args = {"from": [src["x"] + src["w"] // 2, src["y"] + src["h"] // 2],
                "to": [b["x"] + b["w"] // 2, b["y"] + b["h"] // 2], **drag}
        for attempt in range(3):  # a press can be lost on its way in; a person would press again
            call("Drag", "s", json.dumps(args))
            time.sleep(4 + drag.get("holdMs", 400) / 1000)
            if any(e["what"] == "xdnd-begin" for e in json.loads(call("Log"))) or "openmenu" in mode:
                break
            call("SetMode", "s", mode)
        shell = json.loads(call("Log"))
        result = {"name": name, "mode": mode, "payload": payload, "shell": shell, "drop": lines(drop_log),
                  "source": lines(source_log), "focus_after": json.loads(call("Targets"))["focus"]}
    finally:
        app.terminate()
        app.wait(5)
    return result


def summary(r: dict) -> str:
    t0 = next((e["t"] for e in r["shell"] if e["what"] == "xdnd-begin"), None)
    over = next((e["t"] for e in r["shell"] if e["what"] == "over-target"), None)
    rel = lambda t: None if t is None or over is None else round(t - over)  # noqa: E731
    first = lambda log, what: next((e for e in log if e["what"] == what), None)  # noqa: E731
    enter, drop = first(r["drop"], "enter"), first(r["drop"], "drop")
    placed = first(r["shell"], "placed")
    end = [e for e in r["source"] if e["what"] in ("drag-end", "drag-cancel")]
    return json.dumps({
        "name": r["name"], "xdnd_begin": t0 is not None, "positions": next((e.get("positions") for e in r["shell"]
                                                                             if e["what"] == "xdnd-end"), None),
        "button_drag_over": sum(e["what"] == "button-drag-over" for e in r["shell"]),
        "button_accept_drop": any(e["what"] == "button-accept-drop" for e in r["shell"]),
        "spawn_after_over_ms": rel(first(r["shell"], "spawn") and first(r["shell"], "spawn")["t"]),
        "shown_after_over_ms": rel(first(r["shell"], "window-shown") and first(r["shell"], "window-shown")["t"]),
        "first_frame_after_over_ms": rel(first(r["shell"], "first-frame") and first(r["shell"], "first-frame")["t"]),
        "enter_after_over_ms": rel(enter and enter["t"]), "placed": placed,
        "after_300ms": first(r["shell"], "after-300ms"),
        "drop": drop, "source_end": end, "focus_after": r["focus_after"],
        "drop_window_active": [e["active"] for e in r["drop"] if e["what"] == "is-active"],
        "set_type_failed": first(r["shell"], "set-type-failed"),
    })


def main() -> None:
    log = open(os.path.join(OUT, "shell.log"), "a")
    shell = subprocess.Popen(["gnome-shell", "--headless", "--wayland", "--no-x11", "--virtual-monitor", "1280x800"],
                             stdout=log, stderr=log)
    try:
        wait_for(lambda: call("Targets"), 60, "the spike extension")
        time.sleep(3)  # the startup animation eats input
        sample = os.path.join(os.environ["HOME"], "notes.txt")
        with open(sample, "w") as f:
            f.write("Groceries: eggs, milk.\n")
        only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
        scenario("warm-up", "observe", sample)  # the first drag after startup gets lost
        base = "win,layer=dock,passthrough,cairo"
        plans = [
            ("U1-cold-at-begin", base + ",prewarm", sample, {}),
            ("U2-cold-at-begin", base + ",prewarm", sample, {}),
            ("U3-cold-at-button", base, sample, {}),
            ("U4-cold-at-button", base, sample, {}),
            ("U5-cold-at-begin-quick", base + ",prewarm", sample, {"steps": 8, "stepMs": 16, "holdMs": 100}),
            ("U6-cold-at-begin-quick", base + ",prewarm", "Some words", {"steps": 8, "stepMs": 16, "holdMs": 100}),
            ("U7-warm-quick", base + ",resident,twice", sample, {"steps": 8, "stepMs": 16, "holdMs": 100}),
            ("U8-warm-quick", base + ",resident,twice", sample, {"steps": 8, "stepMs": 16, "holdMs": 100}),
        ]
        results = []
        for name, mode, payload, drag in plans:
            if only and not any(name.startswith(o) for o in only):
                continue
            r = scenario(name, mode, payload, **drag)
            results.append(r)
            print(summary(r), flush=True)
        with open(os.path.join(OUT, "results.json"), "w") as f:
            json.dump(results, f, indent=1)
    finally:
        shell.terminate()
        shell.wait(20)


if __name__ == "__main__":
    main()
