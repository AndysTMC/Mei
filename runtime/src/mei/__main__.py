"""`mei-runtime` command line."""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from mei.obs import setup_logging

UNIT_NAME = "mei-runtime.service"


def _systemd_unit() -> str:
    return f"""[Unit]
Description=Mei agent runtime
Documentation=https://github.com/AndysTMC/Mei

[Service]
Type=dbus
BusName=com.andystmc.Mei1
ExecStart={sys.executable} -m mei serve
Restart=on-failure
RestartSec=1s
"""


def _dbus_service() -> str:
    return f"""[D-BUS Service]
Name=com.andystmc.Mei1
Exec={sys.executable} -m mei serve
SystemdService={UNIT_NAME}
"""


def _paths() -> tuple[Path, Path]:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return config / "systemd/user" / UNIT_NAME, data / "dbus-1/services/com.andystmc.Mei1.service"


def _reload() -> None:
    subprocess.run(["/usr/bin/systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["/usr/bin/gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                    "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.ReloadConfig"],
                   check=False, stdout=subprocess.DEVNULL)


def install_dev() -> int:
    """Register this interpreter's runtime as the session service (development installs)."""
    unit, service = _paths()
    for path, text in ((unit, _systemd_unit()), (service, _dbus_service())):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path}")
    _reload()
    return 0


def uninstall_dev() -> int:
    subprocess.run(["/usr/bin/systemctl", "--user", "stop", UNIT_NAME], check=False)
    for path in _paths():
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    _reload()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mei-runtime")
    parser.add_argument("--log-level", default=os.environ.get("MEI_LOG_LEVEL", "info"))
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the runtime on the session bus (default)")
    sub.add_parser("schema", help="print the IPC protocol's JSON Schema")
    sub.add_parser("install-dev", help="register this checkout as the session's Mei runtime")
    sub.add_parser("uninstall-dev", help="remove the development registration")
    args = parser.parse_args(argv)
    setup_logging(args.log_level)

    if args.command == "schema":
        from mei.protocol import json_schema
        print(json.dumps(json_schema(), indent=2))
        return 0
    if args.command == "install-dev":
        return install_dev()
    if args.command == "uninstall-dev":
        return uninstall_dev()

    from mei.app import EXIT_LOCKED, serve
    from mei.ipc.service import NameTaken
    from mei.store.db import WriterLockHeld
    try:
        return asyncio.run(serve())
    except WriterLockHeld as e:
        logging.getLogger("mei").error("%s", e)
        return EXIT_LOCKED
    except NameTaken as e:
        logging.getLogger("mei").error("%s", e)
        return EXIT_LOCKED


if __name__ == "__main__":
    sys.exit(main())
