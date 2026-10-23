"""Spike 0b, the desktop worker's profile (§5.4): bubblewrap with no network and no files, the session
bus only through xdg-dbus-proxy (the portal and the a11y bus's address, nothing else), and the a11y
bus socket. From inside: AT-SPI, the RemoteDesktop portal with the restore token (no dialog), a click
through it, and the keyring and the Shell out of reach."""

import json
import os
import subprocess
import sys
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

from coords import apply_scales  # noqa: E402
from portals import Portal, activation_env, remote_session  # noqa: E402
from shell import Shell, app_named, find, press, save, text_of, walk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def display(app) -> str:
    return " | ".join(t for t in (text_of(n) for n in walk(app, 400) if n.get_role_name() in ("text", "label", "editbar"))
                      if t.strip())[:120]


def main() -> None:
    out = sys.argv[1]
    shell = Shell(out)
    shell.start()
    shell.enable_accessibility()
    activation_env(shell)
    Atspi.init()
    results: dict = {}
    proxy = None
    try:
        shell.launch(["gnome-calculator"])
        app = app_named("calculator", timeout=30)
        time.sleep(1.5)
        first = remote_session(Portal(shell), None)  # the one-time consent, as in setup
        token = first.pop("_token")
        results["consent"] = {k: first[k] for k in ("start", "restore_token")}
        if os.environ.get("MEI_0B_HOST_FRAME"):  # the same grab outside the jail, to tell the jail from GStreamer
            from worker_inside import frame
            results["host_frame"] = frame(shell.bus, first["session"], first["streams"][0][0])

        a11y = shell.call("GetAddress", iface=("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus"))[0]
        results["a11y_address"] = a11y
        socket_path = a11y.split("path=")[1].split(",")[0] if "path=" in a11y else ""
        proxy_sock = os.path.join(os.environ["XDG_RUNTIME_DIR"], "mei-worker-bus")  # short: sun_path is 108 bytes
        proxy = subprocess.Popen(["xdg-dbus-proxy", os.environ["DBUS_SESSION_BUS_ADDRESS"], proxy_sock, "--filter",
                                  "--talk=org.freedesktop.portal.Desktop", "--talk=org.a11y.Bus"])
        for _ in range(50):
            if os.path.exists(proxy_sock):
                break
            time.sleep(0.1)

        scale = float(os.environ.get("MEI_0B_SCALE", "1"))  # both monitors, after the consent
        if scale != 1:
            results["scales"] = apply_scales(shell, (scale, scale))
            time.sleep(2)
        results["monitors"] = shell.state().get("monitors")
        clear = find(app, "button", "C") or find(app, "button", "Clear")
        if clear:
            press(clear)
        seven = find(app, "button", "7")
        ext = Atspi.Component.get_extents(seven, Atspi.CoordType.WINDOW)
        buffer = shell.state()["window"]["buffer"]
        x, y = buffer["x"] + ext.x + ext.width / 2, buffer["y"] + ext.y + ext.height / 2
        before = display(app)

        argv = ["bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
                "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/nonexistent",
                "--setenv", "DBUS_SESSION_BUS_ADDRESS", "unix:path=/run/mei/bus", "--setenv", "GST_REGISTRY", "/tmp/gst.bin", "--setenv", "GST_DEBUG", "pipewiresrc:4,2",
                "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
                "--ro-bind-try", "/bin", "/bin", "--ro-bind", "/etc", "/etc", "--proc", "/proc", "--dev", "/dev",
                "--tmpfs", "/tmp", "--dir", "/run/mei", "--bind", proxy_sock, "/run/mei/bus",
                "--ro-bind", HERE, "/spike"]
        if socket_path:
            argv += ["--bind", socket_path, socket_path, "--setenv", "AT_SPI_BUS_ADDRESS", a11y]
        c = find(app, "button", "C")  # higher up: inside the logical size's bounds even as physical pixels
        cext = Atspi.Component.get_extents(c, Atspi.CoordType.WINDOW)
        cx, cy = buffer["x"] + cext.x + cext.width / 2, buffer["y"] + cext.y + cext.height / 2
        argv += ["/usr/bin/python3", "/spike/worker_inside.py", token, str(x), str(y), str(cx), str(cy)]
        t0 = time.monotonic()
        run = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        results["inside"] = json.loads(run.stdout.strip().splitlines()[-1]) if run.stdout.strip() else {"stderr": run.stderr[-800:]}
        results["inside_s"] = round(time.monotonic() - t0, 2)
        results["inside_stderr"] = run.stderr[-1500:]
        time.sleep(0.8)
        after = display(app)
        results["click_landed"] = "7" in after and after != before
        results["abstract_a11y_socket"] = not bool(socket_path)
    finally:
        if proxy:
            proxy.terminate()
        save(out, "worker", results)
        print(json.dumps(results, default=str)[:3000], flush=True)
        shell.stop()


if __name__ == "__main__":
    main()
