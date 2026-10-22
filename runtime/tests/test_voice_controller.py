"""Voice in the core (Stage 5): a spoken request answered out loud, follow-up listening, "cancel
that" stopping a task, the screen lock, and missing models. The real worker runs on recorded
audio; the model is the scripted one."""

import asyncio
import json
import sys

import numpy as np
import pytest

pytest.importorskip("sherpa_onnx")

from mei.protocol import ProtocolError, VoiceSettings  # noqa: E402
from mei.store import repo  # noqa: E402
from mei.voice.controller import STOP, Fanout, VoiceController  # noqa: E402

from agent_harness import Harness  # noqa: E402
from test_voice import models, say, voice  # noqa: E402,F401  (fixtures)

WORKER = [sys.executable, "-m", "mei.voice.worker"]


def controller(h: Harness, models_root, tmp_path, mic: np.ndarray):
    seen: list[tuple[str, dict]] = []
    (tmp_path / "mic.f32").write_bytes(mic.astype(np.float32).tobytes())
    v = VoiceController(h.engine, lambda kind, payload: seen.append((kind, payload)), lambda _s, _m: WORKER,
                        models_root, load_extra={"source_file": str(tmp_path / "mic.f32"), "source_realtime": False,
                                                 "sink_file": str(tmp_path / "played.f32")})
    h.engine.publisher = Fanout(h.rec, v)
    return v, seen


def states(seen) -> list[str]:
    return [p["state"] for kind, p in seen if kind == "voice.state"]


async def until(check, timeout: float = 40.0) -> None:
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.05)


async def test_a_spoken_question_is_answered_out_loud_then_mei_listens_a_moment_more(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": "It will be sunny tomorrow. Around eighteen degrees."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "What's the weather like tomorrow?", 8.0))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: "speaking" in states(seen) and states(seen)[-1] == "idle")
    after = states(seen)[states(seen).index("listening"):]
    assert after == ["listening", "thinking", "speaking", "listening", "idle"]  # the second listening: the follow-up
    [conversation] = repo.list_conversations(h.store)
    user = next(m for m in repo.history(h.store, conversation["id"]) if m["role"] == "user")
    assert user["content"].lower().startswith("what's the weather like tomorrow") and user["metadata"]["source"] == "voice"
    assert "talking to you by voice" in h.requests()[0]["turns"][0]["content"]
    finals = [p["text"] for kind, p in seen if kind == "voice.partial" and p["final"]]
    assert finals and finals[0].lower().startswith("what's the weather")
    assert len(np.fromfile(tmp_path / "played.f32", dtype=np.float32)) / 16000 > 2.0  # both sentences spoken
    await v.stop()


async def test_saying_stop_stops_the_task_without_asking_the_model(tmp_path, models, voice):
    long = "Here is a very long answer that keeps going. " * 20
    h = Harness(tmp_path, script=[{"text": long}], delay_ms=150, chunk_chars=8)
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Tell me a long story.", 1.0, "Stop.", 3.0))
    await v.apply(VoiceSettings(enabled=True, speak_replies=False))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: states(seen)[-1:] == ["idle"] and "thinking" not in states(seen)[-1:] and
                len(repo.list_conversations(h.store)) == 1)
    [conversation] = repo.list_conversations(h.store)
    task = h.store.read_one("SELECT id, state FROM tasks WHERE conversation_id = ?", (conversation["id"],))
    assert task["state"] not in ("CANCELLED",)  # still answering
    await v.listen(conversation["id"])
    await until(lambda: h.store.read_one("SELECT state FROM tasks WHERE id = ?", (task["id"],))["state"] == "CANCELLED")
    assert len(h.requests()) == 1  # "stop" never reached the model
    await v.stop()


async def test_the_microphone_is_closed_while_the_screen_is_locked(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": "Hi."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Hello.", 2.0))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.set_locked(True)
    await until(lambda: states(seen)[-1] == "suspended")
    with pytest.raises(ProtocolError):
        await v.listen(None)
    await v.set_locked(False)
    await until(lambda: states(seen)[-1] == "idle")
    await v.stop()


async def test_without_the_models_voice_says_what_to_download(tmp_path):
    h = Harness(tmp_path)
    seen = []
    v = VoiceController(h.engine, lambda kind, payload: seen.append(payload), lambda _s, _m: WORKER, tmp_path / "none")
    await v.apply(VoiceSettings(enabled=True))
    assert v.state == "unavailable" and "download the voice models" in v.note and "speech to text" in v.note
    await v.apply(VoiceSettings(enabled=False))
    assert v.state == "off"


def test_the_stop_words():
    for said in ("Stop", "cancel that.", "Never mind", "nevermind", "forget it", "That's enough!"):
        assert STOP.match(said), said
    for said in ("stop the music", "cancel my dentist appointment", "never mind the weather, what time is it"):
        assert not STOP.match(said), said


async def test_only_the_shell_can_open_the_microphone(tmp_path):
    from mei.ipc.service import RuntimeService

    async def not_shell(_sender: str) -> bool:
        return False
    h = Harness(tmp_path)
    service = RuntimeService(bus=None, engine=h.engine, is_shell=not_shell, voice=None)
    with pytest.raises(ProtocolError) as err:
        await service._voice_listen(":1.9", json.dumps({}))
    assert err.value.name == "AccessDenied"
    assert service._voice_status(":1.9", "") == {"state": "unavailable", "note": "voice isn't installed"}
