"""When the audio programs fail (F14): a recorder or player that stops by itself is an error the
person is told about, not silence or a reply taken as heard, and Live stops listening rather than
listen again and again. The real pw-record and pw-cat are replaced by /bin/false: nothing opens a
microphone or plays a sound."""

import asyncio

import numpy as np
import pytest

from mei.voice import pipewire, wire
from mei.voice.parts import Speech, VoiceError
from mei.voice.pipeline import Speaker

from test_voice_cancel import controller


async def test_a_recorder_that_stops_by_itself_is_an_error_not_silence(monkeypatch):
    monkeypatch.setattr(pipewire, "PW_RECORD", "/bin/false")
    source = pipewire.PipeWireSource()
    await source.start()
    with pytest.raises(VoiceError, match="microphone"):
        async for _chunk in source.chunks():
            pass


async def test_stopping_the_recorder_on_purpose_is_quiet():
    source = pipewire.PipeWireSource()
    source._proc = await asyncio.create_subprocess_exec("/bin/sleep", "30", stdout=asyncio.subprocess.PIPE)
    chunks = source.chunks()
    reading = asyncio.ensure_future(chunks.__anext__())
    await asyncio.sleep(0.1)
    await source.stop()
    with pytest.raises(StopAsyncIteration):
        await reading


async def test_a_player_that_fails_is_an_error_not_a_reply_heard(monkeypatch):
    monkeypatch.setattr(pipewire, "PW_CAT", "/bin/false")
    sink = pipewire.PipeWireSink()
    with pytest.raises(VoiceError, match="speaker"):
        for _ in range(50):  # the first writes may land before it has exited
            await sink.play(Speech(np.zeros(4800, dtype=np.float32), 24000))
            await asyncio.sleep(0.02)
        await sink.drain()


async def test_speech_that_cannot_be_played_says_so_once_and_still_finishes():
    class Gone:
        async def play(self, speech):
            raise VoiceError("speaker", "playing stopped")

        async def drain(self):
            raise VoiceError("speaker", "playing stopped")

        async def stop(self):
            pass

    errors, done = [], asyncio.Event()
    speaker = Speaker(None, Gone(), lambda: None, done.set, on_error=errors.append)
    for _ in range(3):
        speaker.say(Speech(np.zeros(10, dtype=np.float32), 24000))
    speaker.end()
    await asyncio.wait_for(done.wait(), 2)
    assert len(errors) == 1 and not speaker.pending
    await speaker.stop()


async def test_listening_that_ends_on_an_error_ends_live_and_says_why(tmp_path):
    _h, v, _seen, sent = controller(tmp_path)
    v._ready.set()
    v.state, v._session = "listening", "button"
    await v._on_worker(wire.Failed(part="microphone", message="recording stopped", ended=True))
    assert (v.state, v._session) == ("idle", None) and "microphone" in v.note
    assert "Listen" not in sent  # not another round of listening


async def test_a_note_while_listening_goes_on_does_not_end_live(tmp_path):
    _h, v, _seen, _sent = controller(tmp_path)
    v._ready.set()
    v.state, v._session = "listening", "button"
    await v._on_worker(wire.Failed(part="speech", message="the GPU voice is off; using the CPU"))
    assert (v.state, v._session) == ("listening", "button")
