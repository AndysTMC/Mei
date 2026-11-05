"""Running desktop tools (desktop/run.py): their output is bounded as it is read, not after (F12)."""

import time
import tracemalloc

import pytest

from mei.desktop.run import ToolFailed, checked_bytes, run

SH = "/bin/sh"
LOUD = "head -c 8388608 /dev/zero"  # 8 MiB


async def test_text_past_the_limit_is_dropped_as_it_arrives_never_held():
    tracemalloc.start()
    try:
        out = await run([SH, "-c", f"{LOUD}; {LOUD} >&2"], max_output=16)
        _now, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out.code == 0 and len(out.stdout) == 16 and len(out.stderr) <= 64 * 1024
    assert peak < 2 * 1024 * 1024, f"held {peak} bytes"


async def test_binary_output_past_the_limit_stops_the_tool_at_once():
    started = time.monotonic()
    with pytest.raises(ToolFailed, match="more than 16 bytes"):
        await checked_bytes(["/usr/bin/yes"], max_output=16, timeout=10)  # never ends by itself
    assert time.monotonic() - started < 3


async def test_output_within_the_limit_is_kept_whole():
    assert await checked_bytes([SH, "-c", "printf abc"], max_output=3) == b"abc"
    out = await run([SH, "-c", "printf hello; echo oops >&2; exit 2"])
    assert (out.code, out.stdout, out.stderr) == (2, "hello", "oops\n")


def test_a_runtime_dir_without_a_user_manager_runs_commands_in_a_process_group(tmp_path, monkeypatch):
    """A private session (or a CI runner) has XDG_RUNTIME_DIR but no systemd user manager in it:
    `systemd-run --user` would fail every command, so Mei doesn't use it there."""
    from mei.desktop.apps import Launcher
    from mei.desktop.run import user_manager
    from mei.desktop.sandbox import Sandbox
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert not user_manager()
    assert Sandbox(systemd_run="/bin/true")._scope is None
    assert Launcher(systemd_run="/bin/true")._systemd_run is None
    (tmp_path / "systemd").mkdir()
    (tmp_path / "systemd" / "private").touch()
    assert user_manager() and Sandbox(systemd_run="/bin/true")._scope == "/bin/true"
