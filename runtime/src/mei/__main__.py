"""`mei-runtime` command line."""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from mei.obs import setup_logging


def _report(result) -> int:
    """Print what an install step did. Returns the exit code: 1 if any step failed."""
    for line in result.lines:
        print(line)
    for note in result.notes:
        print(f"note: {note}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if result.errors else 0


def install_dev() -> int:
    """Register this interpreter's runtime as the session service (development installs)."""
    from mei import install
    result = install.Result()
    install.install_service(install.Host(), install.paths(), sys.executable, result)
    return _report(result)


def uninstall_dev() -> int:
    from mei import install
    result = install.Result()
    install.remove_service(install.Host(), install.paths(), result)
    return _report(result)


def run_install(args) -> int:
    from mei import install
    result = install.install(extension=Path(args.extension).resolve() if args.extension else None,
                             force=args.force)
    if _report(result):
        print("\nMei isn't fully installed; see the errors above. Running the installer again is safe.",
              file=sys.stderr)
        return 1
    if result.log_out:
        print("\nLog out and back in (or restart) to finish. Mei's setup opens on your next login.")
    else:
        print("\nMei is up to date and running; no log-out needed.")
    return 0


def run_uninstall(args) -> int:
    from mei import install
    result = install.uninstall(purge=args.purge)
    if _report(result):
        return 1
    print("\nMei is uninstalled." + ("" if args.purge else " Your data is still there."))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mei-runtime")
    parser.add_argument("--log-level", default=os.environ.get("MEI_LOG_LEVEL", "info"))
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the runtime on the session bus (default)")
    sub.add_parser("schema", help="print the IPC protocol's JSON Schema")
    inst = sub.add_parser("install", help="install the service and the bundled extension for this user")
    inst.add_argument("--extension", metavar="DIR", help="install this built extension instead of the bundled one")
    inst.add_argument("--force", action="store_true", help="replace a symlinked (development) extension")
    uninst = sub.add_parser("uninstall", help="remove the service and the extension")
    uninst.add_argument("--purge", action="store_true", help="also delete conversations, settings, and API keys")
    sub.add_parser("install-dev", help="register this checkout as the session's Mei runtime")
    sub.add_parser("uninstall-dev", help="remove the development registration")
    args = parser.parse_args(argv)
    setup_logging(args.log_level)

    if args.command == "schema":
        from mei.protocol import json_schema
        print(json.dumps(json_schema(), indent=2))
        return 0
    if args.command == "install":
        return run_install(args)
    if args.command == "uninstall":
        return run_uninstall(args)
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
