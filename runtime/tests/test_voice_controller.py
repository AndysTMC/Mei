"""Voice in the core (Stage 5): a spoken request answered out loud, listening that goes on after
it (decision 0026; test_voice_sessions.py has the rest), "cancel that" stopping a task, the screen
lock, and missing models. The real worker runs on recorded audio; the model is the scripted one.
Recordings with several utterances use a short pause (end_pause_ms=500): with the 8 s default
they'd be one utterance."""

import asyncio
import json
import sys

import numpy as np
import pytest

pytest.importorskip("sherpa_onnx")

from mei.protocol import ProtocolError, VoiceSettings  # noqa: E402
from mei.store import repo  # noqa: E402
from mei.core.fanout import Fanout  # noqa: E402
from mei.voice.controller import STOP, VoiceController  # noqa: E402

from agent_harness import Harness  # noqa: E402
from test_voice import models, say, voice  # noqa: E402,F401  (fixtures)

WORKER = [sys.executable, "-m", "mei.voice.worker"]
# A graph with nobody else recording, so these tests never read the real one.
QUIET_GRAPH = ("/bin/sh", "-c", "printf '[\\n]\\n'; exec sleep 3600")


def controller(h: Harness, models_root, tmp_path, mic: np.ndarray):
    seen: list[tuple[str, dict]] = []
    (tmp_path / "mic.f32").write_bytes(mic.astype(np.float32).tobytes())
    v = VoiceController(h.engine, lambda kind, payload: seen.append((kind, payload)), lambda *_: WORKER,
                        models_root, load_extra={"source_file": str(tmp_path / "mic.f32"), "source_realtime": False,
                                                 "sink_file": str(tmp_path / "played.f32")},
                        gpu_engine_for=lambda *_: None, pw_dump=QUIET_GRAPH)
    h.engine.publisher = Fanout(h.rec, v)
    return v, seen


def states(seen) -> list[str]:
    return [p["state"] for kind, p in seen if kind == "voice.state"]


async def until(check, timeout: float = 40.0) -> None:
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.05)


async def test_dictation_goes_on_across_pauses_and_sends_nothing(tmp_path, models, voice):
    """The mic button: what's said goes into the input box, utterance after utterance, until the
    mic is pressed again; no request, no spoken reply, nothing closes it by itself."""
    h = Harness(tmp_path, script=[{"text": "This must not be asked."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Remind me to buy milk.", 2.0,
                                                        "And eggs for the weekend.", 40.0))
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None, dictate=True)
    finals = lambda: [p for kind, p in seen if kind == "voice.partial" and p["final"]]  # noqa: E731
    await until(lambda: len(finals()) == 2)
    await asyncio.sleep(1.0)  # 40 s of quiet go by (recorded audio, read at once): still dictating
    assert states(seen)[-1] == "listening" and states(seen).count("listening") == 1  # one opening, not reopened
    assert all(p["dictation"] for p in finals()) and "milk" in finals()[0]["text"].lower()
    assert "eggs" in finals()[1]["text"].lower()
    await v.listen(None, dictate=True)  # the mic again: done
    await until(lambda: states(seen)[-1] == "idle")
    assert repo.list_conversations(h.store) == [] and "thinking" not in states(seen)
    await v.stop()


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
    """Replies on screen only: Mei listens on at once, so "stop" is heard while it is still writing."""
    long = "Here is a very long answer that keeps going. " * 20
    h = Harness(tmp_path, script=[{"text": long}], delay_ms=150, chunk_chars=8)
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Tell me a long story.", 1.0, "Cancel that.", 3.0))
    await v.apply(VoiceSettings(enabled=True, speak_replies=False, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: len(repo.list_conversations(h.store)) == 1)
    [conversation] = repo.list_conversations(h.store)
    task = h.store.read_one("SELECT id FROM tasks WHERE conversation_id = ?", (conversation["id"],))
    try:
        await until(lambda: h.store.read_one("SELECT state FROM tasks WHERE id = ?", (task["id"],))["state"] == "CANCELLED")
    except TimeoutError:
        heard = [p["text"] for kind, p in seen if kind == "voice.partial" and p["final"]]
        pytest.fail(f"not cancelled; heard {heard}, states {states(seen)}")
    assert len(h.requests()) == 1  # "stop" never reached the model
    await until(lambda: states(seen)[-1] in ("listening", "idle"))  # stopping the task isn't closing voice
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
    v = VoiceController(h.engine, lambda kind, payload: seen.append(payload), lambda *_: WORKER, tmp_path / "none")
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


async def test_models_download_with_progress_then_voice_starts(tmp_path, monkeypatch):
    import hashlib
    from dataclasses import replace
    import httpx
    from mei.voice.models import CATALOG, SILERO
    body = b"silero bytes"
    fake = replace(SILERO, sha256=hashlib.sha256(body).hexdigest(), size=len(body))
    monkeypatch.setitem(CATALOG, "silero", fake)
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    h = Harness(tmp_path)
    v = VoiceController(h.engine, lambda *_: None, lambda *_: WORKER, tmp_path / "models", client=client,
                        gpu_engine_for=lambda *_: None)
    before = {m["id"]: m for m in v.models()["models"]}
    assert not before["silero"]["have"] and before["kokoro"]["size"] > 300_000_000
    v.download(["silero"])
    with pytest.raises(ProtocolError):
        v.download(["silero"])  # one download at a time
    await until(lambda: not v.models()["downloading"])
    after = {m["id"]: m for m in v.models()["models"]}
    assert after["silero"]["have"] and after["silero"]["got"] == len(body) and not after["silero"]["error"]
    with pytest.raises(ProtocolError):
        v.download(["not-a-model"])


async def test_one_model_failing_doesnt_stop_the_rest_downloading(tmp_path, monkeypatch):
    import hashlib
    from dataclasses import replace
    import httpx
    from mei.voice.models import CATALOG, GTCRN, SILERO
    body = b"model bytes"
    monkeypatch.setitem(CATALOG, "silero", replace(SILERO, sha256="0" * 64, size=len(body)))  # its checksum fails
    monkeypatch.setitem(CATALOG, "gtcrn", replace(GTCRN, sha256=hashlib.sha256(body).hexdigest(), size=len(body)))
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    v = VoiceController(Harness(tmp_path).engine, lambda *_: None, lambda *_: WORKER, tmp_path / "models",
                        client=client, gpu_engine_for=lambda *_: None)
    v.download(["silero", "gtcrn"])
    await until(lambda: not v.models()["downloading"])
    rows = {m["id"]: m for m in v.models()["models"]}
    assert rows["silero"]["error"] and not rows["silero"]["have"]
    assert rows["gtcrn"]["have"] and not rows["gtcrn"]["error"]


async def test_the_microphone_check_reports_numbers_and_spots_an_overdriven_input(tmp_path, models, monkeypatch):
    from mei.voice import controller as voice_controller
    h = Harness(tmp_path)
    quiet = np.random.default_rng(1).standard_normal(16000 * 5).astype(np.float32) * 0.001
    v, _seen = controller(h, models, tmp_path, quiet)
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    level = await v.check_mic(seconds=1.0)
    assert level["db"] < -50 and not level["overdriven"]
    await v.stop()

    loud = np.clip(np.random.default_rng(2).standard_normal(16000 * 5).astype(np.float32) * 0.8, -1, 1)
    v, _seen = controller(h, models, tmp_path, loud)
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    assert (await v.check_mic(seconds=1.0))["overdriven"]
    set_to = []

    class FakeWpctl:
        def __init__(self, node):
            assert node == "@DEFAULT_AUDIO_SOURCE@"

        async def set(self, percent, muted):
            set_to.append((percent, muted))
    monkeypatch.setattr(voice_controller, "Wpctl", FakeWpctl)
    await v.fix_mic()
    assert set_to == [(50, False)]
    await v.stop()


async def test_the_gpu_engine_is_offered_for_the_natural_voice_and_can_be_removed(tmp_path, monkeypatch):
    from mei.voice import gpu_engine
    monkeypatch.setattr(gpu_engine, "gpu_present", lambda: True)
    monkeypatch.setenv("MEI_GPU_ENGINE", str(tmp_path / "engine"))
    v = VoiceController(Harness(tmp_path).engine, lambda *_: None, lambda *_: WORKER, tmp_path / "models",
                        gpu_engine_for=lambda *_: None)
    def rows():
        return {m["id"]: m for m in v.models()["models"]}
    await v.apply(VoiceSettings(tts="kokoro"))
    assert v.models()["gpu"] and rows()["gpu-engine"]["offered"] and not rows()["gpu-engine"]["needed"]
    assert 1_800_000_000 < rows()["gpu-engine"]["size"] < 2_000_000_000
    await v.apply(VoiceSettings(tts="kokoro", device="cpu"))
    assert not rows()["gpu-engine"]["offered"]  # the person said never the GPU
    (gpu_engine.site(tmp_path / "engine")).mkdir(parents=True)
    (gpu_engine.site(tmp_path / "engine") / ".mei-gpu-engine").write_text(gpu_engine.VERSION)
    assert rows()["gpu-engine"]["have"]
    await v.remove(["gpu-engine"])
    assert not rows()["gpu-engine"]["have"] and not (tmp_path / "engine" / "site").exists()
    monkeypatch.setattr(gpu_engine, "gpu_present", lambda: False)
    assert not v.models()["gpu"] and "gpu-engine" not in rows()  # never offered without an NVIDIA GPU


async def test_the_worker_restarts_when_the_gpu_joins_or_leaves_its_jail(tmp_path, models, voice):
    jailed: list = []
    engine = {"path": None}
    v = VoiceController(Harness(tmp_path).engine, lambda *_: None, lambda _s, _m, gpu: jailed.append(gpu) or WORKER,
                        models, load_extra={"source_file": "", "sink_file": str(tmp_path / "played.f32")},
                        gpu_engine_for=lambda *_: engine["path"])
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    engine["path"] = tmp_path / "engine"  # the GPU engine was downloaded
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.apply(VoiceSettings(enabled=True, speed=1.1))  # an ordinary change: reloaded, not restarted
    await v.wait_ready()
    assert jailed == [None, tmp_path / "engine"]
    await v.stop()


def test_voices_to_choose_come_from_the_catalog_by_the_id_settings_keep():
    from mei.voice.controller import voice_choices
    choices = voice_choices()
    assert [o["id"] for o in choices["piper"]] == ["amy", "lessac"]
    assert choices["kokoro"][7] == {"id": "7", "label": "Emma (British, woman)"}
    assert choices["openai"][0] == {"id": "", "label": "Alloy (default)"} and {"id": "nova", "label": "Nova"} in choices["openai"]
    assert choices["gemini"][0]["label"] == "Kore (default)"


def test_turning_on_the_wake_word_or_cloud_listening_is_announced():
    from mei.core.engine import _loosened
    from mei.protocol import Config
    before = Config()
    assert "listens for “Hey Mei” all the time" in _loosened(before, Config(voice=VoiceSettings(enabled=True, wake_word=True)))
    assert "goes to Groq" in _loosened(before, Config(voice=VoiceSettings(stt="groq")))
    assert _loosened(before, Config(voice=VoiceSettings(enabled=True, tts="kokoro"))) == ""


async def test_a_spoken_yes_approves_only_what_a_voice_may(tmp_path, models, voice):
    """§11.6: Mei reads a local, undoable action back and "yes, do it" approves it."""
    from agent_harness import call, put, turn
    h = Harness(tmp_path, script=[turn(call("fs_trash", path="~/Music/old.txt")), {"text": "Done."}])
    put(h.env, "~/Music/old.txt", "old")
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Tidy up my downloads.", 2.5, "Yes, do it.", 4.0))
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: not h.env.path("~/Music/old.txt").exists() and states(seen)[-1] == "idle", 60)
    [approval] = h.store.read("SELECT state, decided_by FROM approvals")
    assert (approval["state"], approval["decided_by"]) == ("allowed", "voice")
    heard = [p["text"] for kind, p in seen if kind == "voice.partial" and p["final"]]
    # Kroko varies at the edges ("heidy up", a full stop): the words that matter are the request and the answer.
    assert "downloads" in heard[0].lower() and heard[1].lower().rstrip(".!") == "yes, do it"
    await v.stop()


async def test_a_spoken_yes_never_approves_a_command_on_the_computer(tmp_path, models, voice):
    from agent_harness import call, turn
    h = Harness(tmp_path, preset="hands_off", script=[turn(call("shell_run_host", command="echo hi", cwd="~")),
                                                      {"text": "Okay."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Run echo on my computer.", 2.5, "Yes, do it.", 4.0))
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: h.store.read_one("SELECT count(*) AS n FROM approvals")["n"] == 1, 60)
    # Mei says the card is on screen and listens on; the person says "yes, do it" anyway.
    await until(lambda: len([1 for kind, p in seen if kind == "voice.partial" and p["final"]]) >= 2, 30)
    await asyncio.sleep(1.0)
    states_ = {r["state"] for r in h.store.read("SELECT state FROM approvals")}
    assert "allowed" not in states_  # their words joined the task; the card was never approved by voice
    assert not any("hi" == (r["content"] or "").strip() for r in h.store.read(
        "SELECT content FROM messages WHERE role = 'tool'"))
    await v.stop()


def test_which_effects_a_voice_may_approve():
    from mei.voice.controller import spoken_ok
    assert spoken_ok({"mutates": "local", "undo": "recorded", "visibility": "private", "disclosure": "none"})
    for bad in ({"mutates": "unknown", "undo": "none", "loses_data": True}, {"mutates": "local", "undo": "none"},
                {"mutates": "local", "undo": "recorded", "disclosure": "off_machine"},
                {"mutates": "local", "undo": "recorded", "visibility": "others"},
                {"mutates": "external", "undo": "recorded"}, {"mutates": "local", "undo": "recorded", "loses_data": True}):
        assert not spoken_ok(bad), bad


# ── Read aloud, and a worker of another version (decision 0030) ─────────────


async def test_read_aloud_leaves_voice_idle_and_says_which_reply_it_reads(tmp_path, models, voice):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, np.zeros(16000, np.float32))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    before = len(states(seen))
    await v.read_aloud("m1", "## Done\nI moved **two** files. Here they are.")
    reading = lambda: [p for kind, p in seen if kind == "voice.reading"]  # noqa: E731
    await until(lambda: [p["reading"] for p in reading()] == [True, False])
    assert all(p["message_id"] == "m1" for p in reading())
    assert states(seen)[before:] == [] and v.state == "idle"  # Live never started: no speaking, no listening
    await v.stop()


async def test_read_aloud_waits_for_live_to_end(tmp_path, models, voice):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, np.zeros(16000 * 30, np.float32))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None, by="button")
    await until(lambda: v.state == "listening")
    with pytest.raises(ProtocolError, match="Live is on"):
        await v.read_aloud("m1", "Hello.")
    await v.hush()
    await v.stop()


async def test_a_worker_of_another_version_is_started_again_once_then_named(tmp_path):
    stale = tmp_path / "stale_worker.py"
    stale.write_text("import sys\nfor line in sys.stdin:\n    if '\"load\"' in line:\n"
                     "        print('{\"ev\":\"ready\",\"stt\":\"kroko\",\"tts\":\"piper\",\"device\":\"cpu\"}', flush=True)\n")
    spawned: list[int] = []

    def argv(*_):
        spawned.append(1)
        return [sys.executable, str(stale)]
    models_root = tmp_path / "models"
    for m in ("silero_vad.onnx", "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06", "vits-piper-en_US-amy-low"):
        (models_root / m).mkdir(parents=True)
    seen: list[tuple[str, dict]] = []
    v = VoiceController(Harness(tmp_path).engine, lambda kind, payload: seen.append((kind, payload)), argv,
                        models_root, gpu_engine_for=lambda *_: None, pw_dump=QUIET_GRAPH)
    await v.apply(VoiceSettings(enabled=True))
    await until(lambda: v.state == "unavailable", 10)
    assert len(spawned) == 2 and "log out and back in" in v.note
    await v.stop()


# ── The Live bar's loudness (decision 0040) ─────────────────────────────────


def test_loudness_is_numbers_from_0_to_1_every_25_ms():
    from mei.voice.parts import loudness
    t = np.arange(16000) / 16000
    quiet, speech = np.zeros(1600, np.float32), (0.05 * np.sin(2 * np.pi * 220 * t[:1600])).astype(np.float32)
    assert loudness(quiet, 16000) == [0.0] * 4  # 100 ms: four steps
    assert all(0.3 < x < 1 for x in loudness(speech, 16000))  # about −29 dBFS: speech, not the top
    assert len(loudness(np.zeros(24000, np.float32), 24000)) == 40  # a second of Mei's 24 kHz voice


async def test_live_sends_how_loud_the_person_then_mei_is(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": "It will be sunny tomorrow."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "What's the weather like tomorrow?", 8.0))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: "speaking" in states(seen) and states(seen)[-1] == "idle")
    levels = {src: [x for kind, p in seen if kind == "voice.level" and p["source"] == src for x in p["levels"]]
              for src in ("mic", "mei")}
    assert all(0 <= x <= 1 for xs in levels.values() for x in xs)
    assert max(levels["mic"]) > 0.3 and levels["mic"][0] < 0.1  # the 0.3 s of quiet first, then the question
    assert max(levels["mei"]) > 0.3  # the answer, as it played
    await v.stop()


async def test_dictation_and_read_aloud_send_no_loudness(tmp_path, models, voice):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "Buy milk.", 2.0))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None, dictate=True)
    await until(lambda: any(kind == "voice.partial" and p["final"] for kind, p in seen))
    await v.listen(None, dictate=True)  # done dictating
    await until(lambda: states(seen)[-1] == "idle")
    await v.read_aloud("m1", "I moved two files.")
    await until(lambda: [p["reading"] for kind, p in seen if kind == "voice.reading"] == [True, False])
    assert not [p for kind, p in seen if kind == "voice.level"]
    await v.stop()
