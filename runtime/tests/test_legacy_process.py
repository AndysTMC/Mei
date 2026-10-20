"""The legacy import and key migration with the real tools, on a fully private session.

Private bus, private dconf database (XDG_CONFIG_HOME), a throwaway unlocked gnome-keyring behind a
short private XDG_RUNTIME_DIR (so the real keyring can't be found), and MEI_LEGACY_IMPORT=1.
The test also checks the user's real dconf database is untouched.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).parent
REAL_DCONF = Path.home() / ".config" / "dconf" / "user"
pytestmark = pytest.mark.skipif(not all(shutil.which(t) for t in ("dbus-run-session", "gnome-keyring-daemon"))
                                or not Path("/usr/bin/dconf").exists(), reason="needs dbus, dconf and gnome-keyring")


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_import_and_key_migration_end_to_end(tmp_path):
    before = digest(REAL_DCONF)
    runtime_dir = tempfile.mkdtemp(prefix="mks.", dir=f"/run/user/{os.getuid()}")  # short: socket paths
    try:
        services = tmp_path / "data" / "dbus-1" / "services"
        services.mkdir(parents=True)
        (services / "com.andystmc.Mei1.service").write_text(
            f"[D-BUS Service]\nName=com.andystmc.Mei1\nExec={sys.executable} -m mei serve\n")
        env = {k: v for k, v in os.environ.items() if k not in ("GNOME_KEYRING_CONTROL", "SSH_AUTH_SOCK", "GSETTINGS_BACKEND")}
        env.update(XDG_RUNTIME_DIR=runtime_dir, XDG_DATA_HOME=str(tmp_path / "data"), XDG_CONFIG_HOME=str(tmp_path / "config"),
                   MEI_DATA_DIR=str(tmp_path / "mei"), MEI_LEGACY_IMPORT="1", MEI_LOG_LEVEL="warning")
        script = (f"echo -n test | gnome-keyring-daemon --unlock --components=secrets --daemonize >/dev/null 2>&1; "
                  f"for i in $(seq 50); do gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus "
                  f"--method org.freedesktop.DBus.NameHasOwner org.freedesktop.secrets 2>/dev/null | grep -q true && break; sleep 0.1; done; "
                  f"exec {sys.executable} {HERE / 'legacy_scenario.py'}")
        proc = subprocess.run(["dbus-run-session", "--", "bash", "-c", script], env=env, capture_output=True, text=True,
                              timeout=90)
        lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
        assert proc.returncode == 0 and lines, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-3000:]}"
        r = json.loads(lines[-1])
    finally:
        shutil.rmtree(runtime_dir, ignore_errors=True)
    assert digest(REAL_DCONF) == before, "the real dconf database must not change"
    assert r["active"] == "gemini" and r["providers"] == ["gemini", "openrouter"] and r["model"] == "gemini-x"
    assert r["keys_in_keyring"] == {"gemini": "AIza-test-secret", "openrouter": "sk-or-test-secret",
                                    "legacy": "sk-ancient-secret"}
    assert not r["plaintext_left_in_dconf"] and not r["legacy_api_key_left"] and r["non_secret_fields_kept"]
    assert r["imported_messages"] == ["hello", "hi"]
    assert r["second_run_revision_same"] and r["conversation_count_after_restart"] == 1
