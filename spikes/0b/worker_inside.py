"""Spike 0b, inside the desktop worker's jail: is AT-SPI reachable (the a11y bus), does the portal
start with the restore token and no dialog, does a pointer click through it land, and is the rest of
the session bus closed (the keyring, the Shell)? Prints one JSON line."""

import json
import sys
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")


def frame(bus, session: str, node: int) -> dict:
    """One frame of the session's ScreenCast stream, through the portal's PipeWire fd (GStreamer from
    the system: no PipeWire socket in the jail). Its size says whether frames are logical or physical."""
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    t0 = time.monotonic()
    reply, fds = bus.call_with_unix_fd_list_sync(PORTAL[0], PORTAL[1], "org.freedesktop.portal.ScreenCast",
                                                 "OpenPipeWireRemote", GLib.Variant("(oa{sv})", (session, {})),
                                                 GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, 5000, None, None)
    fd = fds.get(reply.unpack()[0])
    out: dict = {"open_s": round(time.monotonic() - t0, 3)}
    src = Gst.ElementFactory.make("pipewiresrc")
    src.set_property("fd", fd)
    # The portal gives a node id, which only `path` takes (`target-object` wants a serial or a name,
    # and a miss falls back to the default video source: a camera). Never fall back.
    src.set_property("path", str(node))
    src.set_property("stream-properties", Gst.Structure.new_from_string(
        "props, node.dont-fallback=(boolean)true, node.dont-reconnect=(boolean)true"))
    src.set_property("num-buffers", 1)
    convert, sink = Gst.ElementFactory.make("videoconvert"), Gst.ElementFactory.make("appsink")
    sink.set_property("caps", Gst.Caps.from_string("video/x-raw,format=RGB"))
    pipe = Gst.Pipeline()
    for e in (src, convert, sink):
        pipe.add(e)
    src.link(convert)
    convert.link(sink)
    out["playing"] = str(pipe.set_state(Gst.State.PLAYING))
    out["playing_s"] = round(time.monotonic() - t0, 3)
    sample = sink.emit("try-pull-sample", 10 * Gst.SECOND)
    msg = pipe.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
    if msg is not None:
        out["message"] = str(msg.parse_error()[1] if msg.type == Gst.MessageType.ERROR else msg.parse_warning()[1])[:300]
    if sample is not None:
        s = sample.get_caps().get_structure(0)
        data = sample.get_buffer().extract_dup(0, sample.get_buffer().get_size())
        out.update(width=s.get_value("width"), height=s.get_value("height"), bytes=len(data),
                   nonblack=sum(1 for b in data[::997] if b > 16))
    out["first_frame_s"] = round(time.monotonic() - t0, 3)
    pipe.set_state(Gst.State.NULL)
    return out


def press_seven() -> None:
    """Calculator's 7 through AT-SPI's action, from inside the jail."""
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is not None and "calculator" in (app.get_name() or "").lower():
            stack = [app]
            while stack:
                n = stack.pop()
                if n.get_role_name() == "button" and n.get_name() == "7":
                    Atspi.Action.do_action(n, 0)
                    time.sleep(0.3)
                    return
                stack.extend(c for c in (n.get_child_at_index(j) for j in range(n.get_child_count())) if c is not None)


def calculator_display() -> str:
    """Calculator's text nodes, read through AT-SPI from inside the jail."""
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is not None and "calculator" in (app.get_name() or "").lower():
            texts, stack = [], [app]
            while stack and len(texts) < 400:
                n = stack.pop()
                if n.get_role_name() in ("text", "label", "editbar"):
                    try:
                        texts.append(Atspi.Text.get_text(n, 0, -1))
                    except GLib.Error:
                        pass
                stack.extend(c for c in (n.get_child_at_index(j) for j in range(n.get_child_count())) if c is not None)
            return " | ".join(t for t in texts if t.strip())
    return ""


def main() -> None:
    token = sys.argv[1]
    out: dict = {}
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    # Closed: what the proxy doesn't allow.
    for name, path, iface, method in (("org.freedesktop.secrets", "/org/freedesktop/secrets", "org.freedesktop.Secret.Service", "OpenSession"),
                                      ("org.gnome.Shell", "/org/gnome/Shell", "org.freedesktop.DBus.Peer", "Ping")):
        try:
            bus.call_sync(name, path, iface, method, None, None, Gio.DBusCallFlags.NONE, 3000, None)
            out[f"reached {name}"] = True
        except GLib.Error as e:
            out[f"reached {name}"] = False
            out[f"{name} error"] = e.message[:120]
    # AT-SPI: find Calculator and read its display.
    Atspi.init()
    desktop = Atspi.get_desktop(0)
    apps = [desktop.get_child_at_index(i).get_name() for i in range(desktop.get_child_count())]
    out["atspi_apps"] = apps
    # The portal, with the token: no dialog expected.
    sender = bus.get_unique_name().lstrip(":").replace(".", "_")
    results: dict = {}

    def request(iface, method, sig, args, options, token_name):
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token_name}"
        loop = GLib.MainLoop()
        got = {}

        def on(_c, _s, _p, _i, _sig, params, _u):
            got["code"], got["res"] = params.unpack()
            loop.quit()
        sub = bus.signal_subscribe(PORTAL[0], "org.freedesktop.portal.Request", "Response", path, None,
                                   Gio.DBusSignalFlags.NONE, on, None)
        opts = dict(options)
        opts["handle_token"] = GLib.Variant("s", token_name)
        bus.call_sync(PORTAL[0], PORTAL[1], iface, method, GLib.Variant(f"({sig}a{{sv}})", (*args, opts)), None,
                      Gio.DBusCallFlags.NONE, 30000, None)
        GLib.timeout_add(30000, loop.quit)
        loop.run()
        bus.signal_unsubscribe(sub)
        return got.get("code", -1), got.get("res", {})

    rd, sc = "org.freedesktop.portal.RemoteDesktop", "org.freedesktop.portal.ScreenCast"
    t0 = time.monotonic()
    code, res = request(rd, "CreateSession", "", (), {"session_handle_token": GLib.Variant("s", "w1")}, "w0")
    if code == 0:
        session = res["session_handle"]
        request(rd, "SelectDevices", "o", (session,), {"types": GLib.Variant("u", 3), "persist_mode": GLib.Variant("u", 2),
                                                        "restore_token": GLib.Variant("s", token)}, "w2")
        request(sc, "SelectSources", "o", (session,), {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", True)}, "w3")
        code, res = request(rd, "Start", "os", (session, ""), {}, "w4")
        results = {"start": code, "start_s": round(time.monotonic() - t0, 2), "devices": res.get("devices"),
                   "streams": [(s[0], dict(s[1])) for s in res.get("streams", [])]}
        x, y = float(sys.argv[2]), float(sys.argv[3])  # where Calculator's 7 is, from outside
        inside = [(n, p) for n, p in results["streams"] if p["position"][0] <= x < p["position"][0] + p["size"][0]
                  and p["position"][1] <= y < p["position"][1] + p["size"][1]]
        if code == 0 and inside:
            node, props = inside[0]
            results["stream_used"] = node
            results["point"] = [round(x), round(y)]
            pos = props.get("position", (0, 0))
            results["frame"] = frame(bus, session, node)
            # Logical (the stream's size) or physical (its frames' size)? Click 7 each way; read the display.
            scale = results["frame"].get("width", props["size"][0]) / props["size"][0]
            results["clicks"] = []
            for space, k in (("logical", 1.0), ("physical", scale)):
                before = calculator_display()
                try:
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerMotionAbsolute",
                                  GLib.Variant("(oa{sv}udd)", (session, {}, node, (x - pos[0]) * k, (y - pos[1]) * k)), None, 0, 5000, None)
                except GLib.Error as e:
                    results["clicks"].append({"space": space, "at": [round((x - pos[0]) * k), round((y - pos[1]) * k)],
                                              "error": e.message[-60:]})
                    continue
                for state in (1, 0):
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerButton",
                                  GLib.Variant("(oa{sv}iu)", (session, {}, 272, state)), None, 0, 5000, None)
                time.sleep(0.6)
                after = calculator_display()
                results["clicks"].append({"space": space, "at": [round((x - pos[0]) * k), round((y - pos[1]) * k)],
                                          "hit": after.count("7") > before.count("7")})
                if k == 1.0 and scale == 1.0:
                    break
            # 7 again where absolute motion is refused: absolute to the nearest allowed point, then relative
            # motion for the rest (in logical or in physical units?).
            tx, ty = (x - pos[0]) * scale, (y - pos[1]) * scale
            w, h = props["size"][0] - 1, props["size"][1] - 1
            if scale != 1.0 and (tx > w or ty > h):
                for units, k in (("logical", 1 / scale), ("physical", 1.0)):
                    before = calculator_display()
                    # From the stream's corner, so the whole distance is relative and the units tell apart.
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerMotionAbsolute",
                                  GLib.Variant("(oa{sv}udd)", (session, {}, node, 0.0, 0.0)), None, 0, 5000, None)
                    time.sleep(0.1)
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerMotion",
                                  GLib.Variant("(oa{sv}dd)", (session, {}, tx * k, ty * k)), None, 0, 5000, None)
                    time.sleep(0.1)
                    for state in (1, 0):
                        bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerButton",
                                      GLib.Variant("(oa{sv}iu)", (session, {}, 272, state)), None, 0, 5000, None)
                    time.sleep(0.6)
                    after = calculator_display()
                    results["clicks"].append({"target": "7 via relative", "units": units, "hit": after.count("7") > before.count("7")})
            # "C", which clears the display: a target whose physical offset fits inside the logical size.
            cx, cy = float(sys.argv[4]), float(sys.argv[5])
            for space, k in (("logical", 1.0), ("physical", scale)):
                press_seven()
                before = calculator_display()
                try:
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerMotionAbsolute",
                                  GLib.Variant("(oa{sv}udd)", (session, {}, node, (cx - pos[0]) * k, (cy - pos[1]) * k)), None, 0, 5000, None)
                except GLib.Error as e:
                    results["clicks"].append({"target": "C", "space": space, "error": e.message[-40:]})
                    continue
                for state in (1, 0):
                    bus.call_sync(PORTAL[0], PORTAL[1], rd, "NotifyPointerButton",
                                  GLib.Variant("(oa{sv}iu)", (session, {}, 272, state)), None, 0, 5000, None)
                time.sleep(0.6)
                after = calculator_display()
                results["clicks"].append({"target": "C", "space": space, "at": [round((cx - pos[0]) * k), round((cy - pos[1]) * k)],
                                          "hit": "7" in before and after.count("7") < before.count("7")})
                if k == 1.0 and scale == 1.0:
                    break
            results["clicked"] = True
    else:
        results = {"create": code}
    out["portal"] = results
    print(json.dumps(out, default=str), flush=True)


if __name__ == "__main__":
    main()
