"""Listening that goes on until the person ends it (decision 0026).

With the real worker on recorded audio and a scripted model: a conversation the voice button
started listens again after each reply and never times out; the shortcut's ends after 30 s with
nothing said; pressing again sends at once instead of waiting out the 8 s pause; the screen lock
and another app recording pause it, and it comes back after.

In a private PipeWire (pipewire_lab.py): dictation keeps one microphone stream open across pauses,
and Mei's stream closes while another app records and opens again after. Nothing plays aloud and no
real microphone opens.
"""

import asyncio
import json
import subprocess
import sys
import time

import numpy as np
import pytest

pytest.importorskip("sherpa_onnx")

from mei.core.fanout import Fanout  # noqa: E402
from mei.protocol import VoiceSettings  # noqa: E402
from mei.store import repo  # noqa: E402
from mei.voice.controller import PAUSED_NOTE, QUIET_S, VoiceController  # noqa: E402

import pipewire_lab  # noqa: E402
from agent_harness import Harness  # noqa: E402
from test_voice import models, say, voice  # noqa: E402,F401  (fixtures)
from test_voice_controller import QUIET_GRAPH, WORKER, states, until  # noqa: E402

ANSWER = "It will be sunny tomorrow. Around eighteen degrees."


def controller(h: Harness, models_root, tmp_path, mic: np.ndarray | None, realtime: bool = False,
               pw_dump: tuple[str, ...] = QUIET_GRAPH):
    """The controller and the worker; `mic`: recorded audio standing in for the microphone (None:
    the real one, in a private PipeWire)."""
    seen: list[tuple[str, dict]] = []
    extra = {}
    if mic is not None:
        (tmp_path / "mic.f32").write_bytes(mic.astype(np.float32).tobytes())
        extra = {"source_file": str(tmp_path / "mic.f32"), "source_realtime": realtime,
                 "sink_file": str(tmp_path / "played.f32")}
    v = VoiceController(h.engine, lambda kind, payload: seen.append((kind, payload)), lambda *_: WORKER,
                        models_root, load_extra=extra, gpu_engine_for=lambda *_: None, pw_dump=pw_dump)
    h.engine.publisher = Fanout(h.rec, v)
    return v, seen


def finals(seen) -> list[dict]:
    return [p for kind, p in seen if kind == "voice.partial" and p["final"]]


# ── Recorded audio ───────────────────────────────────────────────────────────

async def test_a_conversation_the_button_started_listens_again_and_never_times_out(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": ANSWER}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "What's the weather like tomorrow?",
                                                        2 * QUIET_S))
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None, by="button")
    await until(lambda: "speaking" in states(seen) and states(seen)[-1] == "listening")
    await asyncio.sleep(1.5)  # a minute of quiet after the reply (read at once): still listening
    assert states(seen)[-1] == "listening" and "idle" not in states(seen)[states(seen).index("listening"):]
    await v.listen(None, by="button")  # the button again, with nothing said: closed
    await until(lambda: states(seen)[-1] == "idle")
    await v.stop()


async def test_a_conversation_the_shortcut_started_ends_after_30_s_of_quiet(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": ANSWER}, {"text": "You're welcome."}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, "What's the weather like tomorrow?", 3.0,
                                                        "Thank you.", 2 * QUIET_S))
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: len(h.requests()) == 2 and states(seen)[-1] == "idle", 60)
    # Not after one task: it listened on, heard the thanks, answered, then went quiet for 30 s.
    after = states(seen)[states(seen).index("listening"):]
    assert after == ["listening", "thinking", "speaking", "listening", "thinking", "speaking", "listening", "idle"], after
    await v.stop()


async def test_pressing_again_sends_at_once_instead_of_waiting_out_the_pause(tmp_path, models, voice):
    """The 8 s pause (decision 0026) costs replies speed; pressing again is the way not to wait."""
    question = await say(voice, 0.3, "What's the weather like tomorrow?")
    spoken_s = len(question) / 16000
    timing = {}
    for press in (True, False):
        h = Harness(tmp_path / str(press), script=[{"text": ANSWER}])
        (tmp_path / str(press)).mkdir(exist_ok=True)
        v, seen = controller(h, models, tmp_path / str(press), np.concatenate([question, np.zeros(16000 * 12, np.float32)]),
                             realtime=True)
        await v.apply(VoiceSettings(enabled=True))  # the default pause: 8 s
        await v.wait_ready()
        t0 = time.monotonic()
        await v.listen(None, by="button")
        await asyncio.sleep(spoken_s + 0.3 - (time.monotonic() - t0))  # just after the last word
        pressed = time.monotonic()
        if press:
            await v.listen(None, by="button")
        await until(lambda: finals(seen), 20)
        timing[press] = time.monotonic() - pressed
        await v.stop()
    print(f"\nfinal text after pressing again: {timing[True] * 1000:.0f} ms; waiting out the pause: {timing[False]:.1f} s")
    assert timing[True] < 1.5 and 7.5 < timing[False] < 10.0, timing


async def test_the_lock_pauses_a_conversation_and_unlocking_brings_it_back(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": ANSWER}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, *([1.0] * 60)))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None, by="button")
    await until(lambda: states(seen)[-1] == "listening")
    await v.set_locked(True)
    await until(lambda: states(seen)[-1] == "suspended")  # the microphone closes: 0018's rule
    await v.set_locked(False)
    await until(lambda: states(seen)[-1] == "listening")  # and the conversation goes on
    await v.stop()


def scripted_graph(tmp_path, *steps: tuple[float, list]) -> tuple[str, ...]:
    """A stand-in for `pw-dump --monitor`: after each delay, a batch."""
    script = tmp_path / "pw-dump"
    lines = [f"#!{sys.executable}", "import time"]
    for delay, batch in steps:
        lines += [f"time.sleep({delay})", f"print({json.dumps(json.dumps(batch, indent=2))}, flush=True)"]
    lines.append("time.sleep(3600)")
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return (str(script),)


CALL = {"id": 90, "type": "PipeWire:Interface:Node", "info": {"props": {
    "media.class": "Stream/Input/Audio", "node.name": "Firefox", "application.name": "Firefox"}}}


async def test_another_app_recording_pauses_a_conversation_and_mei_comes_back_after(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": ANSWER}])
    graph = scripted_graph(tmp_path, (0.0, []), (3.0, [CALL]), (3.0, [{"id": 90, "info": None}]))
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, *([1.0] * 60)), pw_dump=graph)
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None, by="button")
    await until(lambda: states(seen)[-1] == "paused", 10)
    assert v.note == PAUSED_NOTE
    await until(lambda: states(seen)[-1] == "listening", 10)
    assert v.note == ""
    await v.stop()


async def test_the_shortcut_still_listens_while_another_app_records(tmp_path, models, voice):
    h = Harness(tmp_path, script=[{"text": ANSWER}])
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, *([1.0] * 60)),
                         pw_dump=scripted_graph(tmp_path, (0.0, [CALL])))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await asyncio.sleep(0.5)
    await v.listen(None)  # asked: the person wants Mei now
    await until(lambda: states(seen)[-1] == "listening")
    await v.stop()


# ── In a private PipeWire ────────────────────────────────────────────────────

@pytest.fixture
def lab():
    if why := pipewire_lab.missing():
        pytest.skip(f"no private PipeWire: {why}")
    with pipewire_lab.Lab() as lab, lab.environ():
        yield lab


def meis_stream(lab) -> int | None:
    """The id of Mei's microphone stream in the lab's graph, if it has one."""
    dump = json.loads(lab.run("pw-dump"))
    return next((o["id"] for o in dump if o.get("type") == "PipeWire:Interface:Node"
                 and ((o.get("info") or {}).get("props") or {}).get("node.name") == "mei.microphone"), None)


async def wait_for(check, timeout: float = 10.0) -> float:
    t0 = time.monotonic()
    while not check():
        if time.monotonic() - t0 > timeout:
            raise TimeoutError
        await asyncio.sleep(0.02)
    return time.monotonic() - t0


async def test_dictation_keeps_one_microphone_stream_across_pauses(tmp_path, models, voice, lab):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, None, pw_dump=("pw-dump", "--monitor", "--no-colors"))
    await v.apply(VoiceSettings(enabled=True, mic=pipewire_lab.MIC, output=pipewire_lab.SPEAKER, end_pause_ms=500))
    await v.wait_ready()
    await v.listen(None, dictate=True)
    await wait_for(lambda: meis_stream(lab) is not None)
    stream = meis_stream(lab)
    for i, words in enumerate(("Remind me to buy milk.", "And eggs for the weekend.")):
        said = await voice.synthesize(words)
        lab.talk(said.samples, said.rate, 0.5)
        await wait_for(lambda: len(finals(seen)) == i + 1, 20)
        await asyncio.sleep(1.5)  # a pause
        assert meis_stream(lab) == stream and states(seen)[-1] == "listening"  # never closed, never reopened
    await v.listen(None, dictate=True)
    await wait_for(lambda: meis_stream(lab) is None)
    assert "eggs" in finals(seen)[1]["text"].lower()
    await v.stop()


async def test_mei_lets_go_of_the_microphone_while_another_app_records(tmp_path, models, lab):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, None, pw_dump=("pw-dump", "--monitor", "--no-colors"))
    await v.apply(VoiceSettings(enabled=True, mic=pipewire_lab.MIC, output=pipewire_lab.SPEAKER))
    await v.wait_ready()
    await v.listen(None, by="button")
    await wait_for(lambda: meis_stream(lab) is not None)
    call = subprocess.Popen(["pw-record", "--target", pipewire_lab.MIC, "-P", "{ node.name = callapp }", "/dev/null"],
                            env=lab.env, stderr=subprocess.DEVNULL)
    try:
        let_go = await wait_for(lambda: meis_stream(lab) is None)
        assert states(seen)[-1] == "paused"
    finally:
        call.kill()
        call.wait()
    back = await wait_for(lambda: meis_stream(lab) is not None)
    await wait_for(lambda: states(seen)[-1] == "listening")
    print(f"\nlet go of the microphone {let_go * 1000:.0f} ms after the call began; back {back * 1000:.0f} ms after it ended")
    assert let_go < 1.0 and back < 1.0
    await v.stop()


async def test_a_setting_changed_mid_dictation_doesnt_end_it(tmp_path, models, voice):
    h = Harness(tmp_path)
    v, seen = controller(h, models, tmp_path, await say(voice, 0.3, *([1.0] * 60)))
    await v.apply(VoiceSettings(enabled=True))
    await v.wait_ready()
    await v.listen(None, dictate=True)
    await until(lambda: states(seen)[-1] == "listening")
    await v.apply(VoiceSettings(enabled=True, end_pause_ms=1000))  # the worker reloads, closing the microphone
    await asyncio.sleep(2.0)
    assert states(seen)[-1] == "listening" and "idle" not in states(seen)[states(seen).index("listening"):]
    await v.listen(None, dictate=True)
    await until(lambda: states(seen)[-1] == "idle")
    await v.stop()
