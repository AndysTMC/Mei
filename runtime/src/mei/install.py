"""Per-user install and uninstall (ADR 0004): service files, the bundled extension, enabled-extensions.

Everything goes under the user's XDG directories; nothing needs root. System GNOME tools are called
by absolute path because the ones on PATH may be Homebrew's, Nix's, or conda's (Stage 0a).
"""

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from mei.legacy import gvariant_string, parse_gvariant_string

UUID = "mei@andystmc.com"
UNIT_NAME = "mei-runtime.service"
BUS_NAME = "com.andystmc.Mei1"
SETTINGS_DIR = "/org/gnome/shell/extensions/mei/"


# ── Paths and file contents ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Paths:
    unit: Path
    dbus_service: Path
    extensions: Path
    data: Path

    @property
    def extension(self) -> Path:
        return self.extensions / UUID


def paths() -> Paths:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return Paths(unit=config / "systemd/user" / UNIT_NAME,
                 dbus_service=data / "dbus-1/services" / f"{BUS_NAME}.service",
                 extensions=data / "gnome-shell/extensions",
                 data=Path(os.environ.get("MEI_DATA_DIR") or data / "mei"))


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
        self._run("/usr/bin/dconf", "reset", "-f", path, check=False)

    def systemctl(self, *args: str) -> None:
        self._run("/usr/bin/systemctl", "--user", *args, check=False)

    def reload_buses(self) -> None:
        self.systemctl("daemon-reload")
        self._run("/usr/bin/gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
                  "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.ReloadConfig", check=False)

    def shell_has_extension(self) -> bool:
        """Whether the running Shell loaded the extension at login (if not, it appears after the next one)."""
        try:
            out = self._run("/usr/bin/gdbus", "call", "--session", "--dest", "org.gnome.Shell.Extensions",
                            "--object-path", "/org/gnome/Shell/Extensions", "--method",
                            "org.gnome.Shell.Extensions.GetExtensionInfo", UUID).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return f"'{UUID}'" in out

    def delete_keys(self) -> tuple[int, int]:
        import asyncio

        from dbus_fast import BusType
        from dbus_fast.aio import MessageBus

        from mei.secrets import delete_provider_keys

        async def go():
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            try:
                return await delete_provider_keys(bus)
            finally:
                bus.disconnect()

        return asyncio.run(go())


# ── Install / uninstall ──────────────────────────────────────────────────────


@dataclass
class Result:
    lines: list[str] = field(default_factory=list)
    log_out: bool = False
    problems: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)


def _write_service_files(p: Paths, python: str, r: Result) -> None:
    for path, text in ((p.unit, systemd_unit(python)), (p.dbus_service, dbus_service(python))):
        if path.is_file() and path.read_text() == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(path)
        r.say(f"wrote {path}")


def _copy_extension(p: Paths, src: Path, force: bool, r: Result) -> bool:
    """Install the extension files. Returns True if they changed."""
    target = p.extension
    if target.is_symlink() and not force:
        r.problems.append(f"{target} is a symlink (a development install); left it alone. "
                          "Use --force to replace it.")
        return False
    if target.is_dir() and not target.is_symlink() and tree_hash(target) == tree_hash(src):
        return False
    # Stage next to the extensions folder (same filesystem, but not inside it: the Shell would
    # try to load the staging directory), then swap it in.
    staging, old = p.extensions.parent / ".mei-extension.new", p.extensions.parent / ".mei-extension.old"
    for d in (staging, old):
        shutil.rmtree(d, ignore_errors=True)
    p.extensions.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, staging)
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        target.rename(old)
    staging.rename(target)
    shutil.rmtree(old, ignore_errors=True)
    r.say(f"installed the extension in {target}")
    return True


def _enable(host: Host, r: Result) -> bool:
    """Add the extension to enabled-extensions (and out of disabled-extensions). True if it changed."""
    changed = False
    enabled = parse_strv(host.gsettings_get("org.gnome.shell", "enabled-extensions"))
    if UUID not in enabled:
        host.gsettings_set("org.gnome.shell", "enabled-extensions", format_strv(enabled + [UUID]))
        r.say(f"added {UUID} to the enabled extensions")
        changed = True
    disabled = parse_strv(host.gsettings_get("org.gnome.shell", "disabled-extensions"))
    if UUID in disabled:
        host.gsettings_set("org.gnome.shell", "disabled-extensions", format_strv([u for u in disabled if u != UUID]))
        changed = True
    if host.gsettings_get("org.gnome.shell", "disable-user-extensions") == "true":
        r.problems.append("Extensions are switched off for this user, so Mei won't appear. "
                          "Turn on Extensions in the Extensions app.")
    return changed


def install(host: Host | None = None, *, extension: Path | None = None, force: bool = False,
            python: str = sys.executable, p: Paths | None = None) -> Result:
    host, p, r = host or Host(), p or paths(), Result()
    src = extension or bundled_extension()
    if src is None:
        r.problems.append("this mei-runtime has no bundled extension (a source checkout?); "
                          "pass --extension DIR, for example the repository's dist/")
        return r
    if not (src / "metadata.json").is_file():
        r.problems.append(f"{src} is not a built extension (no metadata.json)")
        return r

    _write_service_files(p, python, r)
    host.reload_buses()
    changed = _copy_extension(p, src, force, r)
    newly_enabled = _enable(host, r)
    host.systemctl("try-restart", UNIT_NAME)  # a running runtime picks up the new code now
    r.log_out = changed or newly_enabled or not host.shell_has_extension()
    return r


def uninstall(host: Host | None = None, *, purge: bool = False, p: Paths | None = None) -> Result:
    host, p, r = host or Host(), p or paths(), Result()
    host.systemctl("stop", UNIT_NAME)
    for path in (p.unit, p.dbus_service):
        if path.exists():
            path.unlink()
            r.say(f"removed {path}")
    host.reload_buses()

    # Leaving enabled-extensions makes the running Shell disable it at once.
    enabled = parse_strv(host.gsettings_get("org.gnome.shell", "enabled-extensions"))
    if UUID in enabled:
        host.gsettings_set("org.gnome.shell", "enabled-extensions", format_strv([u for u in enabled if u != UUID]))
        r.say(f"removed {UUID} from the enabled extensions")
    if p.extension.is_symlink():
        p.extension.unlink()  # a development install: remove the link, never what it points to
        r.say(f"removed the link {p.extension}")
    elif p.extension.exists():
        shutil.rmtree(p.extension)
        r.say(f"removed {p.extension}")

    if purge:
        if p.data.exists():
            shutil.rmtree(p.data)
            r.say(f"deleted Mei's data in {p.data}")
        host.dconf_reset_dir(SETTINGS_DIR)
        try:
            deleted, left = host.delete_keys()
        except Exception as e:  # no keyring: nothing of ours can be in it
            r.say(f"could not reach the keyring ({type(e).__name__}); no keys deleted")
        else:
            r.say(f"deleted {deleted} API key{'s' if deleted != 1 else ''} from the keyring")
            if left:
                r.problems.append(f"{left} key{'s' if left != 1 else ''} stayed in the keyring because it is "
                                  "locked; unlock it and run uninstall --purge again")
    else:
        r.say(f"kept your conversations and settings in {p.data} (delete them with --purge)")
    return r
