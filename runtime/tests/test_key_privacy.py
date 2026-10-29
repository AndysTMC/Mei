"""No API key on Mei's bus or in its logs (Stage 2a acceptance; ADR 0005), checked with a bus monitor
on a private session with a real keyring. See key_scenario.py."""

import pytest

from private_session import TOOLS_PRESENT, run_private

pytestmark = pytest.mark.skipif(not TOOLS_PRESENT, reason="needs dbus, dconf and gnome-keyring")
KEY = "mei-test-key-7Q2x9Lp4Zr8Vn3Kd"


def test_the_key_never_crosses_the_mei_bus(tmp_path):
    r, stderr = run_private("key_scenario.py", tmp_path)
    # The key really was used, upstream, for listing, the setup test, and both turns...
    assert r["key_used_upstream"] >= 5 and r["models"] == ["mock-1", "mock-2"]
    assert r["setup_has_key"] is True and r["test_ok"] and r["turn_ok"] == "COMPLETED"
    # ...and the upstream echoing it back didn't carry it into the task's error.
    assert r["failed_error"].startswith("OpenAI rejected the API key (HTTP 401") and "[redacted]" in r["failed_error"]
    # The monitor saw the Mei traffic, including events, and none of it contained the key.
    assert r["mei_messages"] > 20 and r["mei_signals"] > 5
    assert r["leaks"] == []
    assert r["leaks_anywhere"] == [] and r["bus_messages"] > r["mei_messages"]  # keyring traffic is encrypted
    assert r["failed_in_stream_error"] and KEY not in r["failed_in_stream_error"]
    assert "[redacted]" in r["failed_in_stream_error"]
    assert r["deputy_error"].startswith("Save this endpoint") and r["key_sent_elsewhere"] == 0
    assert not r["key_in_stored_history"] and not r["key_in_logs"]
    assert KEY not in stderr  # the runtime's own log output
