"""The desktop worker's jail (§5.4, decision 0022), as measured in spike 0b.

- **bubblewrap:** no network, none of the person's files, a private /tmp.
- **The session bus** only through `xdg-dbus-proxy`. The worker may talk to the portal and the
  accessibility bus's launcher, see the Shell's name (to notice it going), and hear the Shell's
  `ControlRevoked` broadcast; nothing else. Keyring, Shell methods and other apps stay out of reach.
- **The accessibility bus** itself is bound in unfiltered: reading and acting on accessible apps is
  what "using the computer" consents to.
- **Only Mei's own code:** the worker runs on the system's Python (it has PyGObject), with only Mei's
  package bound in.
"""

import os
from pathlib import Path

import mei

BWRAP = "/usr/bin/bwrap"
PROXY = "/usr/bin/xdg-dbus-proxy"
PYTHON = "/usr/bin/python3"
SHELL = "org.gnome.Shell"
CODE = "/run/mei/code"
BUS = "/run/mei/bus"


def missing() -> str:
    """What's missing for computer use here, or "". (PyGObject is checked when the worker starts.)"""
    for tool, package in ((BWRAP, "bubblewrap"), (PROXY, "xdg-dbus-proxy"), (PYTHON, "python3")):
        if not os.access(tool, os.X_OK):
            return f"{package} isn't installed"
    return ""


def proxy_argv(bus_address: str, socket: Path, ready_fd: int) -> list[str]:
    """xdg-dbus-proxy for the worker: it writes a byte to `ready_fd` once listening, and exits when that
    fd's other end closes (when the core stops it or dies)."""
    return [PROXY, f"--fd={ready_fd}", bus_address, str(socket), "--filter",
            "--talk=org.freedesktop.portal.Desktop", "--talk=org.a11y.Bus", f"--see={SHELL}",
            f"--broadcast={SHELL}=com.andystmc.Mei1.Control.*@/com/andystmc/Mei1/Control"]


def a11y_socket(address: str) -> Path | None:
    """The accessibility bus's socket file, from its address; None for an abstract socket (which a
    jail without the network namespace can't reach)."""
    for part in address.split(";")[0].removeprefix("unix:").split(","):
        if part.startswith("path="):
            return Path(part.removeprefix("path="))
    return None


def worker_argv(proxy_socket: Path, a11y_address: str) -> list[str]:
    package = Path(mei.__file__).resolve().parent
    args = [BWRAP, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/nonexistent", "--setenv", "LANG", "C.UTF-8",
            "--setenv", "PYTHONPATH", CODE, "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "DBUS_SESSION_BUS_ADDRESS", f"unix:path={BUS}", "--setenv", "GST_REGISTRY", "/tmp/gst.bin",
            "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--ro-bind-try", "/etc/pipewire", "/etc/pipewire", "--ro-bind-try", "/etc/fonts", "/etc/fonts",
            "--setenv", "XDG_CACHE_HOME", "/tmp/cache",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run/mei",
            "--bind", str(proxy_socket), BUS, "--ro-bind", str(package), f"{CODE}/mei"]
    socket = a11y_socket(a11y_address)
    if socket is not None:
        args += ["--bind", str(socket), str(socket), "--setenv", "AT_SPI_BUS_ADDRESS", a11y_address]
    return args + [PYTHON, "-s", "-m", "mei.computer.worker"]
