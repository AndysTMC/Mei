"""Process-level tests: the real runtime on a private session bus, started by D-Bus activation."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
pytestmark = pytest.mark.skipif(shutil.which("dbus-run-session") is None, reason="needs dbus-run-session")


def run(scenario: str, tmp_path: Path) -> dict:
    services = tmp_path / "xdg-data" / "dbus-1" / "services"
    services.mkdir(parents=True)
    (services / "com.andystmc.Mei1.service").write_text(
        f"[D-BUS Service]\nName=com.andystmc.Mei1\nExec={sys.executable} -m mei serve\n")
    env = {**os.environ, "XDG_DATA_HOME": str(tmp_path / "xdg-data"), "MEI_DATA_DIR": str(tmp_path / "mei"),
           "MEI_LOG_LEVEL": "warning"}
    proc = subprocess.run(["dbus-run-session", "--", sys.executable, str(HERE / "ipc_scenarios.py"), scenario,
                           str(tmp_path)], env=env, capture_output=True, text=True, timeout=90)
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert proc.returncode == 0 and lines, f"scenario failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr[-3000:]}"
    return json.loads(lines[-1])


def test_stream_end_to_end(tmp_path):
    r = run("stream", tmp_path)
    assert r == {"mode": "snapshot", "seq_contiguous": True, "state": "COMPLETED", "deltas_match": True,
                 "chunks_contiguous": True}


def test_reattach_mid_stream_loses_nothing(tmp_path):
    r = run("reattach", tmp_path)
    assert r["mode"] == "replay"
    assert {"conversation.created", "message.completed", "task.accepted"} <= set(r["replayed_types"])
    assert r["replay_starts_after_cursor"] and r["replay_contiguous"]
    assert r["partial_at_attach"] and r["reassembled_matches"]
    assert r["deltas_during_detach"] == 0  # a detached client gets nothing, as intended


def test_kill_mid_stream_interrupts_and_never_resends(tmp_path):
    r = run("crash", tmp_path)
    assert r["new_pid"] and r["new_epoch"]
    assert r["state_after_restart"] == "INTERRUPTED" and r["draft_is_prefix"]
    assert r["calls_before_resume"] == 1 and r["calls_after_resume"] == 2


def test_duplicate_commands(tmp_path):
    r = run("duplicate", tmp_path)
    assert r == {"same_task": True, "second_duplicate": True, "conflict": "com.andystmc.Mei1.Error.Conflict"}


def test_second_instance_exits_on_the_writer_lock(tmp_path):
    r = run("lock", tmp_path)
    assert r["exit_code"] == 75 and r["said_why"] and r["seconds"] < 10
