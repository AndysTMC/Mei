"""Spike 0b, AT-SPI coverage: for a GTK4/libadwaita app, GTK4's widget factory, Chrome, Firefox and an
Electron app (Obsidian), each in the private headless Shell with a throwaway profile: how soon its
tree appears, how big it is, how many interactive nodes have a name and an action, whether extents
are given, and a task done through AT-SPI alone where there's one to do."""

import os
import sys
import time

from gi.repository import Atspi, GLib

from shell import Shell, app_named, describe, find, press, save, set_text, text_of, walk

INTERACTIVE = {"button", "push button", "toggle button", "check box", "radio button", "entry", "text", "password text",
               "combo box", "menu item", "link", "slider", "spin button", "page tab", "list item", "tree item"}
FORM = """<!doctype html><html><head><title>Mei form</title></head><body>
<label for=name>Your name</label> <input id=name>
<button id=go onclick="document.getElementById('out').textContent='Hello, '+document.getElementById('name').value">Greet</button>
<p id=out>Waiting</p></body></html>"""


def coverage(app, started: float, limit: int = 20000) -> dict:
    t0 = time.monotonic()
    nodes = walk(app, limit)
    walked = time.monotonic() - t0
    described = []
    for n in nodes:
        try:
            described.append(describe(n))
        except GLib.Error:
            pass
    inter = [d for d in described if d["role"] in INTERACTIVE and d.get("showing")]
    return {
        "appeared_s": round(started, 2), "walk_s": round(walked, 2), "nodes": len(nodes),
        "interactive_showing": len(inter),
        "named": sum(1 for d in inter if d["name"].strip()),
        "with_action": sum(1 for d in inter if d["actions"]),
        "editable": sum(1 for d in described if d["editable"]),
        "screen_extents_nonzero": sum(1 for d in inter if d.get("screen") and d["screen"][0] > 0),
        "window_extents": sum(1 for d in inter if d.get("window") and d["window"][2] > 0),
        "roles": sorted({d["role"] for d in inter}),
        "sample": inter[:12],
    }


def wait_app(shell: Shell, argv, names, env=None, timeout=45.0):
    t0 = time.monotonic()
    shell.launch(argv, **(env or {}))
    app = app_named(*names, timeout=timeout)
    return app, time.monotonic() - t0


def calculator(shell: Shell) -> dict:
    app, took = wait_app(shell, ["gnome-calculator"], ["calculator"])
    if app is None:
        return {"error": "no accessible app appeared"}
    time.sleep(1.5)
    result = coverage(app, took)
    pressed = []
    for label in ("7", "+", "3", "="):
        button = find(app, "button", label) or find(app, "push button", label)
        ok = bool(button and press(button))
        pressed.append([label, ok])
        time.sleep(0.2)
    time.sleep(0.5)
    texts = [text_of(n) for n in walk(app) if n.get_role_name() in ("text", "label", "editbar", "entry")]
    result["task"] = {"pressed": pressed, "shows_10": any(t.strip() == "10" or t.strip().endswith("10") for t in texts)}
    shell.screenshot("calculator")
    return result


def widget_factory(shell: Shell) -> dict:
    app, took = wait_app(shell, ["gtk4-widget-factory"], ["widget"])
    if app is None:
        return {"error": "no accessible app appeared"}
    time.sleep(1.5)
    return coverage(app, took)


def browser_form(shell: Shell, argv, names, page: str, env=None) -> dict:
    app, took = wait_app(shell, argv, names, env, timeout=60)
    if app is None:
        return {"error": "no accessible app appeared"}
    doc = None
    deadline = time.monotonic() + 30
    while doc is None and time.monotonic() < deadline:  # the page's document arrives after the window
        doc = find(app, "document web", "Mei form") or find(app, "document frame", "Mei form")
        time.sleep(0.5)
    result = coverage(app, took)
    if doc is None:
        result["task"] = {"error": "the page's document never appeared in the tree"}
        return result
    entry = find(doc, "entry")
    button = find(doc, "button", "Greet") or find(doc, "push button", "Greet")
    task: dict = {"entry": entry is not None, "button": button is not None}
    if entry is not None:
        task["set_text"] = bool(set_text(entry, "Mei"))
        if not task["set_text"]:  # no EditableText: focus it through AT-SPI, then type as a keyboard
            comp = entry.get_component_iface()
            task["focused"] = bool(comp and Atspi.Component.grab_focus(entry))
            time.sleep(0.3)
            shell.call("TypeText", "s", "Mei")
            time.sleep(0.5)
            task["typed"] = "Mei" in text_of(entry)
    if button is not None:
        task["pressed"] = bool(press(button))
    time.sleep(1.0)
    task["greeted"] = any("Hello, Mei" in (text_of(n) or "") for n in walk(doc, 500))
    result["task"] = task
    return result


def electron(shell: Shell) -> dict:
    home = os.environ["HOME"]
    app, took = wait_app(shell, ["/opt/Obsidian/obsidian", "--ozone-platform=wayland", "--force-renderer-accessibility",
                                 f"--user-data-dir={home}/obsidian", "--no-sandbox"], ["obsidian"], timeout=60)
    if app is None:
        return {"error": "no accessible app appeared"}
    time.sleep(4)
    return coverage(app, took)


def main() -> None:
    out = sys.argv[1]
    home = os.environ["HOME"]
    page = os.path.join(home, "form.html")
    open(page, "w").write(FORM)
    shell = Shell(out)
    shell.start()
    shell.enable_accessibility()
    Atspi.init()
    results = {}
    steps = [
        ("gnome_calculator", lambda: calculator(shell)),
        ("gtk4_widget_factory", lambda: widget_factory(shell)),
        ("chrome", lambda: browser_form(shell, ["google-chrome", "--ozone-platform=wayland", "--force-renderer-accessibility",
                                                f"--user-data-dir={home}/chrome", "--no-first-run",
                                                "--no-default-browser-check", "--disable-gpu", f"file://{page}"],
                                        ["chrome"], page)),
        ("firefox", lambda: browser_form(shell, ["firefox", "--new-instance", "--profile", f"{home}/ff", f"file://{page}"],
                                         ["firefox"], page, {"MOZ_ENABLE_WAYLAND": "1"})),
        ("electron_obsidian", lambda: electron(shell)),
    ]
    try:
        for name, step in steps:
            try:
                results[name] = step()
            except Exception as e:  # noqa: BLE001  a spike records what broke and goes on
                results[name] = {"error": f"{type(e).__name__}: {e}"}
            shell.screenshot(name)
            for app in shell.apps:
                app.terminate()
            shell.apps.clear()
            time.sleep(2)
            print(name, {k: v for k, v in results[name].items() if k not in ("sample", "roles")}, flush=True)
    finally:
        save(out, "atspi", results)
        shell.stop()


if __name__ == "__main__":
    main()
