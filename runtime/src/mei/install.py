"""Per-user install and uninstall (ADR 0004): service files, the bundled extension, enabled-extensions.

Everything goes under the user's XDG directories; nothing needs root. System GNOME tools are called
by absolute path because the ones on PATH may be Homebrew's, Nix's, or conda's (Stage 0a).
"""

import asyncio
import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from dbus_fast import BusType
from dbus_fast.aio import MessageBus
from dbus_fast.errors import AuthError, DBusError, InvalidAddressError

from mei import paths as xdg
from mei.legacy import DCONF_DIR, gvariant_string, parse_gvariant_string
from mei.protocol import BUS_NAME, EXTENSION_UUID
from mei.secrets import KeyringUnavailable, delete_provider_keys

UNIT_NAME = "mei-runtime.service"
TOOL_ERRORS = (OSError, subprocess.SubprocessError, ValueError)  # a system tool missing, failing, or odd output


# ── Paths and file contents ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Paths:
    unit: Path
    dbus_service: Path
    extensions: Path
    data: Path

    @property
    def extension(self) -> Path:
        return self.extensions / EXTENSION_UUID


def paths() -> Paths:
    return Paths(unit=xdg.config_home() / "systemd/user" / UNIT_NAME,
                 dbus_service=xdg.data_home() / "dbus-1/services" / f"{BUS_NAME}.service",
                 extensions=xdg.data_home() / "gnome-shell/extensions",
                 data=xdg.data_dir())


def systemd_unit(python: str = sys.executable) -> str:
    return f"""[Unit]
Description=Mei agent runtime
Documentation=https://github.com/AndysTMC/Mei

[Service]
Type=dbus
BusName={BUS_NAME}
ExecStart={python} -m mei serve
Restart=on-failure
RestartSec=1s
"""


def dbus_service(python: str = sys.executable) -> str:
    return f"""[D-BUS Service]
Name={BUS_NAME}
Exec={python} -m mei serve
SystemdService={UNIT_NAME}
"""


def bundled_extension() -> Path | None:
    """The extension built into this wheel by scripts/build-release.sh (absent in a source checkout)."""
    path = Path(str(files("mei") / "extension"))
    return path if (path / "metadata.json").is_file() else None


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


# ── GVariant string arrays (what `gsettings get` prints for `as` keys) ───────


def parse_strv(text: str) -> list[str]:
    t = text.strip().removeprefix("@as").strip()
    if not (t.startswith("[") and t.endswith("]")):
        raise ValueError(f"not a string array: {text!r}")
    out, i, body = [], 0, t[1:-1]
    while i < len(body):
        if body[i] in "'\"":
            quote, j = body[i], i + 1
            while j < len(body) and body[j] != quote:
                j += 2 if body[j] == "\\" else 1
            out.append(parse_gvariant_string(body[i:j + 1]))
            i = j + 1
        else:
            i += 1  # commas and spaces
    return out


def format_strv(values: list[str]) -> str:
    return "[" + ", ".join(gvariant_string(v) for v in values) + "]" if values else "@as []"


# ── The host: every outside effect, so tests can replace it ──────────────────


class Host:
    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True, text=True, check=check, timeout=30)

    def gsettings_get(self, schema: str, key: str) -> str:
        return self._run("/usr/bin/gsettings", "get", schema, key).stdout.strip()

    def gsettings_set(self, schema: str, key: str, value: str) -> None:
        self._run("/usr/bin/gsettings", "set", schema, key, value)

    def dconf_reset_dir(self, path: str) -> None:
        self._run("/usr/bin/dconf", "reset", "-f", path)

    def systemctl(self, *args: str) -> bool:
        try:
            return self._run("/usr/bin/systemctl", "--user", *args, check=False).returncode == 0
        except TOOL_ERRORS:
            return False

    def reload_buses(self) -> bool:
        """Make systemd and the session bus see changed unit and service files. False if systemd didn't."""
        try:
            self._run("/usr/bin/gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                      "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.ReloadConfig", check=False)
        except TOOL_ERRORS:
            pass  # the bus also notices new service files on its own; systemd is the one that matters
        return self.systemctl("daemon-reload")

    def shell_has_extension(self) -> bool:
        """Whether the running Shell loaded the extension at login (if not, it appears after the next one)."""
        try:
            out = self._run("/usr/bin/gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions",
                            "--object-path", "/org/gnome/Shell/Extensions", "--method",
                            "org.gnome.Shell.Extensions.GetExtensionInfo", EXTENSION_UUID).stdout
        except TOOL_ERRORS:
            return False
        return f"'{EXTENSION_UUID}'" in out

    def delete_keys(self) -> tuple[int, int]:
        async def go() -> tuple[int, int]:
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            try:
                return await delete_provider_keys(bus)
            finally:
                bus.disconnect()

        return asyncio.run(go())


# ── Install / uninstall ──────────────────────────────────────────────────────


@dataclass
class Result:
    lines: list[str] = field(default_factory=list)  # what was done
    notes: list[str] = field(default_factory=list)  # done, but the user should know something
    errors: list[str] = field(default_factory=list)  # a step failed
    log_out: bool = False

    def say(self, line: str) -> None:
        self.lines.append(line)


def install_service(host: Host, p: Paths, python: str, r: Result) -> None:
    """Write the systemd unit and D-Bus activation file for `python -m mei serve`."""
    for path, text in ((p.unit, systemd_unit(python)), (p.dbus_service, dbus_service(python))):
        if path.is_file() and path.read_text() == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)
        r.say(f"wrote {path}")
    if not host.reload_buses():
        r.notes.append("systemd didn't reload its units; Mei starts after your next login")


def remove_service(host: Host, p: Paths, r: Result) -> None:
    host.systemctl("stop", UNIT_NAME)
    for path in (p.unit, p.dbus_service):
        if path.exists():
            path.unlink()
            r.say(f"removed {path}")
    host.reload_buses()


def _copy_extension(p: Paths, src: Path, force: bool, r: Result) -> bool:
    """Install the extension files. Returns True if they changed."""
    target = p.extension
    if target.is_symlink() and not force:
        r.notes.append(f"{target} is a symlink (a development install); left it alone. Use --force to replace it.")
        return False
    if target.is_dir() and not target.is_symlink() and tree_hash(target) == tree_hash(src):
        return False
    # Stage next to the extensions folder (same filesystem, but not inside it: the Shell would
    # try to load the staging directory), then swap it in, putting the old one back on failure.
    staging, old = p.extensions.parent / ".mei-extension.new", p.extensions.parent / ".mei-extension.old"
    for d in (staging, old):
        shutil.rmtree(d, ignore_errors=True)
    p.extensions.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, staging)
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.rename(old)
    try:
        staging.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)
        raise
    shutil.rmtree(old, ignore_errors=True)
    r.say(f"installed the extension in {target}")
    return True


def _set_enabled(host: Host, enable: bool, r: Result) -> bool:
    """Add the extension to enabled-extensions (and take it out of disabled-extensions), or remove it."""
    changed = False
    enabled = parse_strv(host.gsettings_get("org.gnome.shell", "enabled-extensions"))
    if enable and EXTENSION_UUID not in enabled:
        host.gsettings_set("org.gnome.shell", "enabled-extensions", format_strv(enabled + [EXTENSION_UUID]))
        r.say(f"added {EXTENSION_UUID} to the enabled extensions")
        changed = True
    elif not enable and EXTENSION_UUID in enabled:
        # Leaving enabled-extensions makes the running Shell disable it at once.
        host.gsettings_set("org.gnome.shell", "enabled-extensions",
                           format_strv([u for u in enabled if u != EXTENSION_UUID]))
        r.say(f"removed {EXTENSION_UUID} from the enabled extensions")
        changed = True
    if enable:
        disabled = parse_strv(host.gsettings_get("org.gnome.shell", "disabled-extensions"))
        if EXTENSION_UUID in disabled:
            host.gsettings_set("org.gnome.shell", "disabled-extensions",
                               format_strv([u for u in disabled if u != EXTENSION_UUID]))
            changed = True
        if host.gsettings_get("org.gnome.shell", "disable-user-extensions") == "true":
            r.notes.append("Extensions are switched off for this user, so Mei won't appear. "
                           "Turn on Extensions in the Extensions app.")
    return changed


def install(host: Host | None = None, *, extension: Path | None = None, force: bool = False,
            python: str = sys.executable, p: Paths | None = None) -> Result:
    host, p, r = host or Host(), p or paths(), Result()
    src = extension or bundled_extension()
    if src is None:
        r.errors.append("this mei-runtime has no bundled extension (a source checkout?); "
                        "pass --extension DIR, for example the repository's dist/")
        return r
    if not (src / "metadata.json").is_file():
        r.errors.append(f"{src} is not a built extension (no metadata.json)")
        return r

    install_service(host, p, python, r)
    try:
        changed = _copy_extension(p, src, force, r)
    except OSError as e:
        r.errors.append(f"couldn't install the extension in {p.extension}: {e}")
        return r
    try:
        newly_enabled = _set_enabled(host, True, r)
    except TOOL_ERRORS as e:
        r.errors.append(f"couldn't add {EXTENSION_UUID} to the enabled extensions: {e}")
        return r
    host.systemctl("try-restart", UNIT_NAME)  # a running runtime picks up the new code now
    r.log_out = changed or newly_enabled or not host.shell_has_extension()
    return r


def uninstall(host: Host | None = None, *, purge: bool = False, p: Paths | None = None) -> Result:
    host, p, r = host or Host(), p or paths(), Result()
    remove_service(host, p, r)
    try:
        _set_enabled(host, False, r)
    except TOOL_ERRORS as e:
        r.errors.append(f"couldn't remove {EXTENSION_UUID} from the enabled extensions: {e}")
    if p.extension.is_symlink():
        p.extension.unlink()  # a development install: remove the link, never what it points to
        r.say(f"removed the link {p.extension}")
    elif p.extension.exists():
        shutil.rmtree(p.extension)
        r.say(f"removed {p.extension}")

    if not purge:
        r.say(f"kept your conversations and settings in {p.data} (delete them with --purge)")
        return r
    if p.data.exists():
        shutil.rmtree(p.data)
        r.say(f"deleted Mei's data in {p.data}")
    try:
        host.dconf_reset_dir(DCONF_DIR)
    except TOOL_ERRORS as e:
        r.errors.append(f"couldn't clear Mei's settings from dconf: {e}")
    try:
        deleted, left = host.delete_keys()
    except (KeyringUnavailable, OSError, AuthError, InvalidAddressError, DBusError) as e:
        r.notes.append(f"couldn't reach the keyring ({type(e).__name__}), so no API keys were deleted")
    else:
        r.say(f"deleted {deleted} API key{'s' if deleted != 1 else ''} from the keyring")
        if left:
            r.notes.append(f"{left} key{'s' if left != 1 else ''} stayed in the keyring because it is locked; "
                           "unlock it and run uninstall --purge again")
    return r
