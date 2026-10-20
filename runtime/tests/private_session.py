"""Run a scenario script on a fully private session: private bus, private XDG dirs, and a throwaway
unlocked gnome-keyring behind a short private XDG_RUNTIME_DIR (so the real keyring can't be found).
The runtime is started by D-Bus activation from this checkout. Returns the scenario's last JSON line
and its stderr (which includes the runtime's log)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TOOLS_PRESENT = all(shutil.which(t) for t in ("dbus-run-session", "gnome-keyring-daemon")) \
    and Path("/usr/bin/dconf").exists()


def run_private(scenario: str, tmp_path: Path, **env_extra: str) -> tuple[dict, str]:
    runtime_dir = tempfile.mkdtemp(prefix="mks.", dir=f"/run/user/{os.getuid()}")  # short: socket paths
    try:
        services = tmp_path / "data" / "dbus-1" / "services"
        services.mkdir(parents=True)
        (services / "com.andystmc.Mei1.service").write_text(
            f"[D-BUS Service]\nName=com.andystmc.Mei1\nExec={sys.executable} -m mei serve\n")
        env = {k: v for k, v in os.environ.items() if k not in ("GNOME_KEYRING_CONTROL", "SSH_AUTH_SOCK", "GSETTINGS_BACKEND")}
        env.update(XDG_RUNTIME_DIR=runtime_dir, XDG_DATA_HOME=str(tmp_path / "data"), XDG_CONFIG_HOME=str(tmp_path / "config"),
                   MEI_DATA_DIR=str(tmp_path / "mei"), MEI_LOG_LEVEL="info", **env_extra)
        script = (f"echo -n test | gnome-keyring-daemon --unlock --components=secrets --daemonize >/dev/null 2>&1; "
                  f"for i in $(seq 50); do gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus "
                  f"--method org.freedesktop.DBus.NameHasOwner org.freedesktop.secrets 2>/dev/null | grep -q true && break; sleep 0.1; done; "
                  f"exec {sys.executable} {HERE / scenario} {tmp_path}")
        proc = subprocess.run(["dbus-run-session", "--", "bash", "-c", script], env=env, capture_output=True, text=True,
                              timeout=120)
        lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
        assert proc.returncode == 0 and lines, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-3000:]}"
        return json.loads(lines[-1]), proc.stderr
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
