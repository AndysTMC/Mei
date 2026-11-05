"""Computer use (§10, decision 0022) without a desktop: the wire protocol, geometry as measured in spike 0b,
how an act is judged from the observed element, the password hand-off through the loop, and the core's
controller against a fake worker (the control lease, replies, a dying worker, the kill switch)."""

import asyncio
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import msgspec
import pytest

from mei.capabilities.base import READ_ONLY, CapabilityError, Window
from mei.capabilities.computer import (ActParams, DesktopAct, HANDOFF_DONE, judge, needs_input, outline,
                                       pick_window)
from mei.computer import controller as ctl
from mei.computer import geometry, jail, wire
from mei.computer.controller import Desktop, DesktopError, Seen
from mei.computer.geometry import Picture, Rect, Stream
from mei.core.states import Execution, TaskState
from mei.policy.engine import PRESETS, Facts, Subject, evaluate
from mei.policy.paths import PathRules
from mei.protocol import ComputerSettings, TaskCommandArgs, UpdateConfigArgs

from agent_harness import Harness, call, turn

S, E = TaskState, Execution

# ── The wire ─────────────────────────────────────────────────────────────────


def test_messages_round_trip_and_bad_ones_are_refused():
    act = wire.Act(id=3, token="ab", action="press", element="e2", window={"id": 1})
    assert wire.command(wire.encode(act)) == act
    assert wire.event(wire.encode(wire.Reply(id=3, ok=False, error="stale", message="observe again"))).error == "stale"
    for bad in ('{"op":"act","id":"3","token":"a","action":"press"}',  # id must be an int
                '{"op":"act","id":true,"token":"a","action":"press"}',  # a bool isn't an int
                '{"op":"act","id":3,"token":"a"}',  # action missing
                '{"op":"act","id":3,"token":"a","action":"press","extra":1}',
                '{"op":"rm -rf"}', "not json"):
        with pytest.raises(wire.WireError):
            wire.command(bad)
    with pytest.raises(wire.WireError):
        wire.event(wire.encode(act))  # a command isn't an event


# ── Geometry (spike 0b's measurements) ───────────────────────────────────────


def test_an_element_is_its_window_buffer_origin_plus_its_window_extents():
    window = geometry.Window(id=1, title="Calculator", pid=9, buffer=Rect(435, 83, 410, 666))
    assert geometry.element_point(window, Rect(24, 428, 64, 44)) == (491, 533)  # coords.json: hit at (491, 533)


def test_pointer_moves_are_frame_pixels_with_relative_motion_past_the_logical_size():
    plain = Stream(52, Rect(0, 0, 1920, 1080), 1920)
    assert geometry.pointer_moves(plain, 811, 673) == [("absolute", 811, 673)]
    at_125 = Stream(44, Rect(1024, 0, 1536, 864), 1920)
    assert geometry.pointer_moves(at_125, 1643, 557) == [("absolute", pytest.approx(773.75), pytest.approx(696.25))]
    at_150 = Stream(44, Rect(960, 0, 1280, 720), 1920)
    reachable = geometry.pointer_moves(at_150, 1451, 432)  # C: hit with absolute motion at (736, 648)
    assert reachable == [("absolute", pytest.approx(736.5), pytest.approx(648))]
    (_, ax, ay), (kind, dx, dy) = geometry.pointer_moves(at_150, 1451, 480)  # 7: refused at y = 720
    assert (ax, ay) == (pytest.approx(736.5), 719) and kind == "relative" and dy == pytest.approx(1 / 1.5)
    corner = geometry.pointer_moves(at_150, 960 + 1279, 719)
    assert corner[0][1:] == (1279, 719) and corner[1][1:] == (pytest.approx(1918.5 / 1.5 - 1279 / 1.5),
                                                              pytest.approx(1078.5 / 1.5 - 719 / 1.5))
    with pytest.raises(ValueError):
        geometry.pointer_moves(at_150, 10, 10)  # not on this monitor


def test_the_whole_screen_is_one_picture_whatever_the_monitors_scaling():
    """Two monitors side by side, the second at 150 %: one picture at one scale, and each point in it maps
    back to the logical point under it on the right monitor."""
    left = geometry.Stream(1, Rect(0, 0, 1280, 800), 1280)
    right = geometry.Stream(2, Rect(1280, 0, 1280, 800), 1920)  # 150 %: its frames are 1920 wide
    picture, places = geometry.screen_picture([left, right], 1600)
    assert (picture.width, picture.height) == (1600, 500) and picture.per_pixel == 1.6
    assert places == [(left, Rect(0, 0, 800, 500)), (right, Rect(800, 0, 800, 500))]
    assert picture.logical(400, 250) == (640.0, 400.0)  # the middle of the left monitor
    assert picture.logical(1200, 250) == (1920.0, 400.0)  # the middle of the right one
    above = geometry.Stream(3, Rect(0, -600, 800, 600), 800)  # a smaller one above: the space beside it stays dark
    picture, places = geometry.screen_picture([left, above], 4000)
    assert (picture.width, picture.height) == (1280, 1400) and places[1][1] == Rect(0, 0, 800, 600)


def test_a_window_picture_maps_back_to_logical_points():
    window = geometry.Window(id=1, title="w", pid=1, buffer=Rect(1059, 27, 410, 666))
    stream = Stream(44, Rect(960, 0, 1280, 720), 1920)
    crop, picture = geometry.window_picture(window, stream, max_width=300)
    assert crop == Rect(round(99 * 1.5), round(27 * 1.5), round(410 * 1.5), round(666 * 1.5))
    assert picture.width == 300 and picture.logical(0, 0) == (1059, 27)
    x, y = picture.logical(150, 100)
    assert x == pytest.approx(1059 + 150 * 410 / 300) and y == pytest.approx(27 + 100 * 410 / 300)
    with pytest.raises(ValueError):
        picture.logical(300, 0)
    assert geometry.window_picture(window, Stream(1, Rect(0, 0, 900, 600), 900), 300) is None


# ── Judging an act from what was observed (§10.4) ────────────────────────────

FIELD = {"id": "e1", "role": "text", "name": "Name", "actions": [], "editable": True}
SECRET = {"id": "e2", "role": "password text", "name": "Password", "actions": [], "editable": True}
SUBMIT = {"id": "e3", "role": "button", "name": "Send", "actions": ["click"]}
UNKNOWN_BUTTON = {"id": "e4", "role": "button", "name": "Continue", "actions": ["click"]}
CHECKBOX = {"id": "e5", "role": "check box", "name": "Remember me", "actions": ["click"]}
SWITCH = {"id": "e6", "role": "switch", "name": "Wi-Fi", "actions": []}


def act(action, element="", **kw) -> ActParams:
    return ActParams(snapshot="t1", action=action, element=element, **kw)


def test_an_act_is_unknown_unless_the_element_shows_it_is_low_risk():
    assert judge(act("press", "e4"), UNKNOWN_BUTTON, "App").mutates == "unknown"
    assert judge(act("toggle", "e5"), CHECKBOX, "App").mutates == "local"
    assert judge(act("set_text", "e1", text="Ada"), FIELD, "App").mutates == "local"
    assert judge(act("type", "e1", text="Ada\n"), FIELD, "App").mutates == "unknown"  # a newline can submit
    assert judge(act("key", text="Return"), None, "App").mutates == "unknown"
    assert judge(act("key", "e1", text="Tab"), FIELD, "App").mutates == "local"
    assert judge(act("key", "e1", text="ctrl+a"), FIELD, "App").mutates == "unknown"  # shortcuts can do anything
    assert judge(act("click", point=[3, 4]), None, "App").mutates == "unknown"
    assert judge(act("set_text", "e2", text="hunter2"), SECRET, "App") == READ_ONLY  # nothing is typed: hand-off


def test_outward_labels_and_messaging_apps_only_make_it_stricter():
    assert judge(act("press", "e3"), SUBMIT, "App").visibility == "others"
    assert judge(act("set_text", "e1", text="hi"), FIELD, "Telegram").visibility == "others"
    assert judge(act("toggle", "e5"), CHECKBOX, "App").visibility == "private"


def test_an_unknown_effect_asks_under_every_preset():
    facts = Facts(capability="desktop.act", meta=False, effects=judge(act("press", "e4"), UNKNOWN_BUTTON, "App"),
                  subjects=(Subject(kind="app", value="org.example.App", access="write", provenance="user"),),
                  tainted=False)
    rules = PathRules(Path("/home/u"), {}, [])
    for preset in PRESETS.values():
        d = evaluate(facts, preset, [], rules, Path("/home/u"))
        assert (d.decision, d.reason) == ("ask", "unknown_effect"), preset.name


def test_what_needs_the_screen_session():
    assert not needs_input(act("press", "e4"), UNKNOWN_BUTTON)  # an AT-SPI action
    assert needs_input(act("toggle", "e6"), SWITCH)  # a GTK4 switch has no action: a pointer click
    assert not needs_input(act("set_text", "e1", text="x"), FIELD)  # EditableText
    assert needs_input(act("set_text", "e1", text="x"), {**FIELD, "editable": False})  # Chrome: focus and keys
    assert needs_input(act("click", point=[1, 2]), None)


def test_picking_a_window_and_the_outline():
    windows = [Window(app_id="org.gnome.Calculator", title="Calculator", id=7, buffer={"x": 0}),
               Window(app_id="org.gnome.TextEditor", title="notes.txt", id=8, focused=True, buffer={"x": 0}),
               Window(app_id="org.gnome.Nautilus", title="Downloads", id=9)]  # no geometry: not offered
    assert pick_window(windows, "").id == 8
    assert pick_window(windows, "calculator").id == 7 and pick_window(windows, "7").id == 7
    with pytest.raises(CapabilityError):
        pick_window(windows, "Downloads")
    text = outline({"title": "Sign in", "app": "App", "token": "t1",
                    "nodes": [FIELD | {"text": "Ada", "states": ["focused"]}, SECRET | {"states": []}]})
    assert "e1 text “Name” = “Ada” [focused]" in text and "password: the person fills it in" in text


class FakeDesktop:
    """A desktop port with one window and a canned snapshot; records what it was asked to do."""

    def __init__(self, nodes: list[dict]) -> None:
        self.window = {"id": 7, "title": "Sign in", "pid": 42, "buffer": {"x": 0, "y": 0, "width": 400, "height": 300},
                       "focused": True, "app_id": "org.example.Login"}
        self.nodes = nodes
        self.acts: list[tuple] = []
        self.observed = 0
        self.locked = False
        self.active = False

    def person_active(self, idle_ms: int) -> bool:
        return self.active

    async def observe(self, window, monitors, *, picture, max_nodes=250, screen=False):
        self.observed += 1
        self.looked_at = "screen" if screen else window.get("title")
        data = {"token": f"t{self.observed}", "app": "Login", "title": "Sign in", "nodes": [] if screen else self.nodes}
        if screen:
            self.screen_token = data["token"]
            data["picture"] = {"png": base64.b64encode(b"\x89PNG fake").decode(), "width": 1600, "height": 500}
            return data
        if picture:
            data["picture"] = {"png": base64.b64encode(b"\x89PNG fake").decode(), "width": 4, "height": 3}
        return data

    async def act(self, token, action, **kw):
        self.acts.append((token, action, kw.get("element"), kw.get("text")))
        self.act_window = kw.get("window")
        return {"how": "text", "changes": ["e1 text “Name”: now “Ada”"], "token": "", "nodes": []}

    def seen(self, token):
        if token != f"t{self.observed}":
            return None
        if token == getattr(self, "screen_token", None):
            return Seen(token, {"id": 0, "title": "the screen"}, "", {}, (1600, 500))
        return Seen(token, self.window, "Login", {n["id"]: n for n in self.nodes})


class Bridge:
    def __init__(self, window: dict) -> None:
        self.window = window

    async def list_windows(self):
        w = self.window
        return [Window(app_id=w["app_id"], title=w["title"], focused=True, id=w["id"], pid=w["pid"],
                       buffer=w["buffer"])]

    async def monitors(self):
        return [{"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0}]

    async def idle_ms(self):
        return 100


def computer_harness(tmp_path, script, see_without_asking=True, **kw) -> tuple[Harness, FakeDesktop]:
    """Looking needs no asking here unless `see_without_asking` is False (the default people get)."""
    h = Harness(tmp_path, script=script, **kw)
    desktop = FakeDesktop([FIELD | {"states": []}, SECRET | {"states": []}, UNKNOWN_BUTTON | {"states": []}])
    h.env.desktop = desktop
    bridge = Bridge(desktop.window)
    h.env.bridge = lambda: bridge
    config = h.engine.get_config()
    doc = config["config"] if isinstance(config.get("config"), dict) else msgspec.to_builtins(config["config"])
    doc["computer"] = msgspec.to_builtins(ComputerSettings(enabled=True, see_without_asking=see_without_asking))
    h.engine.update_config(msgspec.convert({"revision": config["revision"], "config": doc}, UpdateConfigArgs))
    return h, desktop


async def test_a_password_field_is_handed_to_the_person(tmp_path):
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe")),
        turn(call("desktop_act", snapshot="t1", action="set_text", element="e1", text="Ada")),
        turn(call("desktop_act", snapshot="t1", action="set_text", element="e2", text="hunter2")),
        {"text": "Signed in."}])
    r = h.submit("sign me in to Login as Ada")
    assert await h.until(r["task_id"]) == S.WAITING_INPUT
    assert desktop.acts == [("t1", "set_text", "e1", "Ada")]  # the password never reached the desktop
    h.answer(r["task_id"], HANDOFF_DONE)
    assert await h.until(r["task_id"]) == S.COMPLETED
    actions = h.actions(r["task_id"])
    assert [a["execution"] for a in actions[1:]] == [E.SUCCEEDED, E.SUCCEEDED]
    assert any(t["role"] == "tool" and "filled it in themselves" in t["content"] for t in h.requests()[-1]["turns"])


async def test_turned_off_and_stale_snapshots_are_refused(tmp_path):
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe")), turn(call("desktop_observe")),
        turn(call("desktop_act", snapshot="t1", action="set_text", element="e1", text="Ada")),
        {"text": "Couldn't."}])
    r = h.submit("type Ada into Login")
    assert await h.until(r["task_id"]) == S.COMPLETED
    stale = h.actions(r["task_id"])[2]
    assert stale["execution"] == E.REJECTED and "no longer current" in stale["error"] and desktop.acts == []

    off = Harness(tmp_path / "off", script=[turn(call("desktop_observe")), {"text": "No."}])
    off.env.desktop = FakeDesktop([])
    r = off.submit("look at my screen")
    assert await off.until(r["task_id"]) == S.COMPLETED
    assert off.actions(r["task_id"])[0]["execution"] == E.REJECTED  # computer use isn't allowed in Settings
    assert "desktop_observe" not in off.requests()[0]["tools"]


async def test_an_unfamiliar_button_asks_even_hands_off(tmp_path):
    h, desktop = computer_harness(tmp_path, preset="hands_off", script=[
        turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t1", action="press", element="e4")),
        {"text": "Pressed."}])
    r = h.submit("press Continue in Login")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    assert desktop.acts == []
    assert h.actions(r["task_id"])[1]["decision_reason"] == "unknown_effect"


# ── The controller, against a fake worker ────────────────────────────────────

FAKE_PROXY = """
import os, select, socket, sys
fd = int(sys.argv[1].split("=")[1])
listening = socket.socket(socket.AF_UNIX)
listening.bind(sys.argv[2])
os.write(fd, b"x")
p = select.poll(); p.register(fd, 0); p.poll()  # until the core closes its end
"""

FAKE_WORKER = """
import json, sys, threading, time
log = open(sys.argv[1], "a")
print(json.dumps({"op": "ready", "version": 1, "accessibility": True}), flush=True)
for line in sys.stdin:
    m = json.loads(line)
    log.write(json.dumps({**m, "t": time.monotonic()}) + "\\n"); log.flush()
    if m["op"] == "observe":
        print(json.dumps({"op": "reply", "id": m["id"], "ok": True,
                          "data": {"token": "s1", "app": "A", "nodes": [{"id": "e1", "role": "button"}]}}), flush=True)
    elif m["op"] == "act" and m["action"] == "hang":
        pass
    elif m["op"] == "act" and m["action"] == "die":
        sys.exit(3)
    elif m["op"] == "act":  # answered later, as the real worker does while its reader keeps reading leases
        reply = json.dumps({"op": "reply", "id": m["id"], "ok": True, "data": {"changes": []}})
        threading.Timer(0.8, lambda r=reply: print(r, flush=True)).start()
    elif m["op"] == "close_session":
        print(json.dumps({"op": "reply", "id": m["id"], "ok": True, "data": {}}), flush=True)
    elif m["op"] == "open_session":
        print(json.dumps({"op": "reply", "id": m["id"], "ok": True, "data": {"restore_token": "next"}}), flush=True)
    elif m["op"] == "quit":
        break
    if m["op"] == "act" and m.get("text") == "revoke":
        print(json.dumps({"op": "revoked", "reason": "stopped from the Shell"}), flush=True)
"""


class Tokens:
    def __init__(self, token: str = "first") -> None:
        self.token = token

    async def get(self) -> str:
        return self.token

    async def put(self, token: str) -> None:
        self.token = token


@pytest.fixture
def fake_desktop(tmp_path, monkeypatch):
    log = tmp_path / "worker.jsonl"
    proxy, worker = tmp_path / "proxy.py", tmp_path / "worker.py"
    proxy.write_text(FAKE_PROXY)
    worker.write_text(FAKE_WORKER)
    monkeypatch.setattr(jail, "missing", lambda: "")
    monkeypatch.setattr(jail, "proxy_argv",
                        lambda _address, socket, fd: [sys.executable, str(proxy), f"--fd={fd}", str(socket)])
    revoked: list[str] = []

    def on_revoked(reason: str, _by_person: bool) -> None:
        revoked.append(reason)

    async def a11y() -> str:
        return "unix:path=/nonexistent/at-spi/bus"

    run = Path(tempfile.mkdtemp(prefix="mei-t", dir="/tmp"))  # short: a socket's path is at most 108 bytes
    shown: list[bool] = []

    async def overlay(active: bool) -> None:
        shown.append(active)

    desktop = Desktop("unix:path=/nonexistent", a11y, Tokens(), run, revoked=on_revoked,
                      argv=lambda _socket, _a11y: [sys.executable, str(worker), str(log)], overlay=overlay)
    desktop.shown = shown
    desktop.revoked_reasons = revoked

    def logged() -> list[dict]:
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    desktop.logged = logged
    yield desktop
    shutil.rmtree(run, ignore_errors=True)


async def test_the_controller_keeps_snapshots_renews_the_lease_and_keeps_the_new_token(fake_desktop):
    d = fake_desktop
    data = await d.observe({"id": 1}, [], picture=False)
    assert data["token"] == "s1" and d.seen("s1").nodes["e1"]["role"] == "button" and d.seen("nope") is None
    await d.act("s1", "press", element="e1", needs_input=True)
    assert d._tokens.token == "next"  # each start returns a new token, which is kept
    await asyncio.sleep(0.1)  # the worker logs what it read
    leases = [m for m in d.logged() if m["op"] == "lease"]
    renewals = [m for m in leases if m["valid_ms"] == ctl.LEASE_VALID_MS]
    assert len(renewals) >= 3 and leases[-1]["valid_ms"] == 0  # renewed while acting, ended after
    gaps = [b["t"] - a["t"] for a, b in zip(renewals, renewals[1:])]
    assert max(gaps) < ctl.LEASE_VALID_MS / 1000  # never long enough to lapse
    await d.act("s1", "press", element="e1", needs_input=False)
    assert not any(m["op"] == "lease" and m["generation"] == 2 for m in d.logged())  # AT-SPI only: no lease
    await d.stop()


async def test_two_tasks_input_never_overlaps_and_no_window_means_no_input(fake_desktop):
    """Decision 0033: one act holds the pointer and keys from making way to the end of its lease."""
    d = fake_desktop
    await d.observe({"id": 1}, [], picture=False)
    await asyncio.gather(d.act("s1", "press", element="e1", needs_input=True),
                         d.act("s1", "press", element="e1", needs_input=True))
    await asyncio.sleep(0.1)
    leases = [m for m in d.logged() if m["op"] == "lease"]
    first_end = next(i for i, m in enumerate(leases) if m["valid_ms"] == 0)
    assert all(m["generation"] == leases[0]["generation"] for m in leases[:first_end + 1])  # one, then the other

    async def no_shell(_window_id: int) -> None:
        raise RuntimeError("the Shell didn't answer")
    d._make_way = no_shell
    before = len(d.logged())
    with pytest.raises(DesktopError, match="front"):
        await d.act("s1", "press", element="e1", needs_input=True)
    await asyncio.sleep(0.1)
    assert not any(m["op"] in ("lease", "act") for m in d.logged()[before:])
    await d.stop()


async def test_a_dying_worker_fails_what_waits_and_starts_again(fake_desktop):
    d = fake_desktop
    await d.observe({"id": 1}, [], picture=False)
    with pytest.raises(DesktopError) as e:
        await d.act("s1", "die", needs_input=False)
    assert e.value.error == "unavailable"
    assert (await d.observe({"id": 1}, [], picture=False))["token"] == "s1"  # a new worker
    await d.stop()


async def test_the_kill_switch_kills_at_once_and_a_revoke_is_reported(fake_desktop):
    d = fake_desktop
    await d.act("s0", "press", text="revoke", needs_input=False)
    await asyncio.sleep(0.1)
    assert d.revoked_reasons == ["stopped from the Shell"]
    waiting = asyncio.ensure_future(d.act("s1", "hang", needs_input=False))
    await asyncio.sleep(0.2)
    started = time.monotonic()
    await d.kill("Super+Escape")
    assert time.monotonic() - started < 0.2
    with pytest.raises(DesktopError):
        await waiting


async def test_a_task_never_shows_the_portal_dialog(fake_desktop):
    d = fake_desktop
    d._tokens.token = ""
    with pytest.raises(DesktopError) as e:
        await d.act("s1", "click", point=[1, 2])
    assert "setup" in e.value.message
    await d.ensure_session(ask=True)  # setup may ask
    assert d._tokens.token == "next"
    await d.stop()


async def test_the_chip_shows_for_a_period_of_use_and_the_person_counts_as_active(fake_desktop):
    d = fake_desktop
    await d.observe({"id": 1}, [], picture=False)
    await d.act("s1", "press", element="e1", needs_input=True)
    assert d.shown == [True]  # once for the whole period, not per act
    assert not d.person_active(idle_ms=50)  # the Shell's idle clock saw Mei's own click
    d._last_input -= 5  # five seconds since Mei's last event…
    assert d.person_active(idle_ms=200)  # …but someone moved the pointer 0.2 s ago
    assert not d.person_active(idle_ms=4000)
    await d.set_locked(True)
    with pytest.raises(DesktopError) as e:
        await d.observe({"id": 1}, [], picture=False)
    assert "locked" in e.value.message
    await d.set_locked(False)
    await d.stop()
    assert d.shown == [True, False]


async def reaches(h: Harness, task_id: str, state: str, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while h.task(task_id)["state"] != state:
            await asyncio.sleep(0.02)


@pytest.mark.parametrize("how", ["they stop", "Resume"])
async def test_a_pointer_act_waits_while_the_person_uses_the_computer(tmp_path, how):
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t1", action="click", element="e4")),
        {"text": "Done."}])
    desktop.active = True
    r = h.submit("click Continue in Login")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    await reaches(h, r["task_id"], S.WAITING_RESOURCE)
    assert h.task(r["task_id"])["error"] == "Paused while you use the computer" and desktop.acts == []
    if how == "they stop":
        desktop.active = False  # it goes on by itself
    else:
        h.engine.resume(TaskCommandArgs(command_id="c-resume", task_id=r["task_id"]))  # the person says go on now
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert [a[1] for a in desktop.acts] == ["click"]


async def test_turned_off_while_it_waited_the_act_does_not_run(tmp_path):
    """Decision 0031: judged again right before it runs, after any wait; turned off means it doesn't."""
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t1", action="click", element="e4")),
        {"text": "Couldn't."}])
    desktop.active = True
    r = h.submit("click Continue in Login")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    await reaches(h, r["task_id"], S.WAITING_RESOURCE)
    config = h.engine.get_config()
    doc = config["config"] if isinstance(config.get("config"), dict) else msgspec.to_builtins(config["config"])
    doc["computer"] = msgspec.to_builtins(ComputerSettings(enabled=False))
    h.engine.update_config(msgspec.convert({"revision": config["revision"], "config": doc}, UpdateConfigArgs))
    desktop.active = False
    assert await h.until(r["task_id"]) == S.COMPLETED
    act = h.actions(r["task_id"])[1]
    assert desktop.acts == [] and act["execution"] == E.POLICY_DENIED and "turned off" in act["error"], act["error"]


async def test_looking_again_after_acting_is_not_a_loop(tmp_path):
    """Decision 0035: the owner's tasks of 2026-10-26 stopped with "kept repeating the same step" because a
    third look at the same window was refused, though each click between had worked and changed it."""
    looks = [turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t1", action="set_text", element="e1",
                                                         text="Ada"))]
    h, desktop = computer_harness(tmp_path, looks + [
        turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t2", action="set_text", element="e1",
                                                  text="Bea")),
        turn(call("desktop_observe")), {"text": "Done."}])
    r = h.submit("type Ada, then Bea, into Login")
    assert await h.until(r["task_id"]) in (S.COMPLETED, S.WAITING_APPROVAL)
    observes = [a for a in h.actions(r["task_id"]) if a["capability"] == "desktop.observe"]
    assert len(observes) == 3 and all(a["execution"] == E.SUCCEEDED for a in observes), \
        [(a["execution"], a["error"]) for a in observes]


async def test_the_model_is_told_it_can_see_the_screen_only_when_it_can(tmp_path):
    """Decision 0035: with no word about it, models said "I can't see your screen" with the tool in hand."""
    h, _desktop = computer_harness(tmp_path, [{"text": "A login form."}])
    r = h.submit("what's on my screen?")
    await h.until(r["task_id"])
    assert "desktop_observe" in h.requests()[-1]["turns"][0]["content"]
    off = Harness(tmp_path / "off", script=[{"text": "Hi."}])
    r = off.submit("hello")
    await off.until(r["task_id"])
    assert "desktop_observe" not in off.requests()[-1]["turns"][0]["content"]


async def test_a_window_with_no_controls_to_see_is_looked_at_as_a_picture(tmp_path):
    """Decision 0035: Chrome's web pages showed Mei one element, the window frame, and the owner's tasks
    looped clicking by point on snapshots without a picture."""
    h, desktop = computer_harness(tmp_path, [turn(call("desktop_observe")), {"text": "A web page."}])
    desktop.nodes = [{"id": "e1", "role": "frame", "name": "Antigravity - Google Chrome", "states": []}]
    r = h.submit("what's on my screen?")
    assert await h.until(r["task_id"]) == S.COMPLETED
    observed = h.actions(r["task_id"])[0]
    assert observed["execution"] == E.SUCCEEDED and desktop.observed == 2  # the elements, then a picture of it
    seen = h.store.read_one("SELECT content FROM messages WHERE action_id = ?", (observed["id"],))["content"]
    assert "Picture: 4×3 pixels" in seen


async def test_the_whole_screen_is_a_look_of_its_own_and_a_point_in_it_can_be_clicked(tmp_path):
    """Decision 0036: notifications, the top bar and every window, not only one window's inside."""
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe", screen=True)),
        turn(call("desktop_act", snapshot="t1", action="click", point=[800, 20])),
        {"text": "Clicked the notification."}])
    r = h.submit("open the notification on my screen")
    assert await h.until(r["task_id"]) in (S.COMPLETED, S.WAITING_APPROVAL)
    if h.task(r["task_id"])["state"] == S.WAITING_APPROVAL:
        h.approve(r["task_id"])
        assert await h.until(r["task_id"]) == S.COMPLETED
    look, click = h.actions(r["task_id"])[:2]
    seen = h.store.read_one("SELECT content FROM messages WHERE action_id = ?", (look["id"],))["content"]
    assert desktop.looked_at == "screen" and "The whole screen" in seen and "Sign in" in seen  # the windows, listed
    assert "Picture: 1600×500 pixels" in seen
    assert click["execution"] == E.SUCCEEDED and desktop.act_window is None  # a point on the screen, not a window


async def test_the_kill_switch_stops_the_tasks_that_used_the_computer(tmp_path):
    h, desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe")), turn(call("desktop_act", snapshot="t1", action="press", element="e4")),
        {"text": "Pressed."}])
    r = h.submit("press Continue in Login")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    assert h.engine.stop_computer_use() == [r["task_id"]]
    assert h.task(r["task_id"])["state"] == S.CANCELLED and desktop.acts == []
    assert h.engine.stop_computer_use() == []  # finished tasks aren't touched again



@pytest.mark.parametrize("vision", [True, False])
async def test_only_the_latest_picture_goes_to_the_model(tmp_path, vision):
    h, _desktop = computer_harness(tmp_path, [
        turn(call("desktop_observe", picture=True)), turn(call("desktop_observe", picture=True)),
        {"text": "I see it."}], no_images=not vision)
    r = h.submit("what's in the Login window?")
    assert await h.until(r["task_id"]) == S.COMPLETED  # a model that can't see images is asked again without them
    pictures = [t.get("images", 0) for t in h.requests()[-1]["turns"] if t["role"] == "tool"]
    assert pictures == ([0, 1] if vision else [0, 0])
    kept = list((h.env.data_dir / "artifacts").rglob("*.png"))
    assert len(kept) == 2 and kept[0].read_bytes() == b"\x89PNG fake"  # kept with the conversation, not the ledger


SYSTEM_GI = subprocess.run(["/usr/bin/python3", "-c", "import gi"], capture_output=True).returncode == 0 \
    if Path("/usr/bin/python3").exists() else False


@pytest.mark.skipif(not SYSTEM_GI, reason="the desktop worker runs on the system's Python with PyGObject")
def test_control_ends_quietly_when_released_and_says_so_when_it_runs_out():
    script = """
import sys, time
sys.path.insert(0, sys.argv[1])
from mei.computer.worker.control import Control, ControlLost
said = []
c = Control(lambda reason, by: said.append(f"{by}: {reason}"))
c._shell_owner = ":1.1"  # as if the Shell watcher found it
c.lease(1, 600); c.check()
c.lease(1, 0)  # the act is done
try:
    c.check(); print("still allowed")
except ControlLost:
    pass
c.lease(2, 50); time.sleep(0.1)
c.revoke("the core stopped renewing control", "lease")  # what the watcher does when a lease runs out
c.revoke("again")  # once per period
print(said)
"""
    src = str(Path(__file__).resolve().parents[1] / "src")
    out = subprocess.run(["/usr/bin/python3", "-c", script, src], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "['lease: the core stopped renewing control']", out.stderr


# ── Seeing the screen (decision 0029) ───────────────────────────────────────


async def test_asked_in_chat_mei_asks_before_it_looks_and_an_always_grant_holds(tmp_path):
    script = [turn(call("desktop_observe")), {"text": "It's a login form."}]
    h, desktop = computer_harness(tmp_path, script * 2, see_without_asking=False)
    r = h.submit("what's on my screen?")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    approval = h.approval(r["task_id"])
    assert "Mei would see what's on your screen" in str(approval["card"])
    h.approve(r["task_id"], scope="always")
    assert await h.until(r["task_id"]) == S.COMPLETED
    r = h.submit("and now?")
    assert await h.until(r["task_id"]) == S.COMPLETED  # always: no second card


@pytest.mark.parametrize("source", ["text", "voice"])
async def test_the_screen_switch_alone_decides_whether_mei_asks(tmp_path, source):
    """Decision 0039: nothing about how it was asked (typed, Live, "Hey Mei") lets Mei look unasked."""
    from mei.protocol import SubmitInputArgs
    script = [turn(call("desktop_observe")), {"text": "A login form."}]
    for on, state in ((False, S.WAITING_APPROVAL), (True, S.COMPLETED)):
        h, desktop = computer_harness(tmp_path / str(on), script, see_without_asking=on)
        r = h.engine.submit_input(SubmitInputArgs(command_id="ask-1", text="what's on my screen?", source=source))
        assert await h.until(r["task_id"]) == state
