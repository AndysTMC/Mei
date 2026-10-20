"""The shared fixtures (also replayed by the TypeScript projection tests) must match protocol.py."""

import json
from pathlib import Path

import msgspec
import pytest

from mei.protocol import DURABLE_EVENTS, EPHEMERAL_EVENTS, Envelope

FIXTURES = sorted((Path(__file__).resolve().parents[2] / "protocol" / "v1" / "fixtures").glob("*.json"))


def test_fixtures_exist():
    assert {f.stem for f in FIXTURES} >= {"turn_completed", "turn_cancelled", "interrupted_then_resumed",
                                          "reattach_mid_stream"}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_events_are_valid_envelopes(path):
    data = json.loads(path.read_text())
    items = data.get("before", []) + data["attach"].get("events", []) + data["events"]
    for item in items:
        env = msgspec.convert(item, Envelope)
        if env.seq is None:
            assert env.type in EPHEMERAL_EVENTS
        else:
            assert env.type in DURABLE_EVENTS
    seqs = [i["seq"] for i in items if i["seq"] is not None]
    assert seqs == list(range(seqs[0], seqs[0] + len(seqs))), "durable seq must be contiguous"
    assert data["attach"]["mode"] in ("snapshot", "replay")
