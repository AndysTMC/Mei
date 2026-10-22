"""Cloud speech (decision 0017): the right request to each provider's fixed endpoint with its own
key, audio decoded either way; and the worker asking the core for speech through its pipe."""

import base64
import json
import wave
import io

import httpx
import numpy as np
import pytest

pytest.importorskip("numpy")

from mei.protocol import VoiceSettings  # noqa: E402
from mei.voice.cloud import STT, TTS, CloudSpeech  # noqa: E402
from mei.voice.parts import Speech, VoiceError  # noqa: E402


def speech(seen: list[httpx.Request], respond) -> CloudSpeech:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return respond(request)

    async def key_for(provider: str) -> str:
        return {"groq": "gsk-test", "openai": "sk-test", "gemini": "gm-test"}.get(provider, "")
    return CloudSpeech(httpx.AsyncClient(transport=httpx.MockTransport(handle)), key_for)


async def test_transcription_sends_a_wav_to_the_providers_endpoint_with_its_key():
    seen: list[httpx.Request] = []
    cloud = speech(seen, lambda r: httpx.Response(200, json={"text": " Pause the music. "}))
    text = await cloud.transcribe("groq", np.zeros(16000, np.float32))
    assert text == "Pause the music."
    [request] = seen
    assert str(request.url) == STT["groq"].url and request.headers["authorization"] == "Bearer gsk-test"
    body = request.content
    assert b"whisper-large-v3-turbo" in body and b"RIFF" in body  # the model, and a WAV file


async def test_openai_and_gemini_speech_come_back_as_samples():
    tone = (np.sin(np.arange(2400) / 10) * 0.5).astype(np.float32)
    s16 = (tone * 32767).astype("<i2").tobytes()
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if "googleapis" in str(request.url):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {
                "mimeType": "audio/L16;codec=pcm;rate=24000", "data": base64.b64encode(s16).decode()}}]}}]})
        return httpx.Response(200, content=s16)
    cloud = speech(seen, respond)
    for backend in ("openai", "gemini"):
        out = await cloud.synthesize(backend, "Hello there.")
        assert out.rate == 24000 and np.allclose(out.samples, tone, atol=1e-3)
    openai, gemini = seen
    assert json.loads(openai.content)["response_format"] == "pcm" and openai.headers["authorization"] == "Bearer sk-test"
    assert str(gemini.url) == TTS["gemini"].url and gemini.headers["x-goog-api-key"] == "gm-test"
    assert json.loads(gemini.content)["generationConfig"]["responseModalities"] == ["AUDIO"]

    # A voice chosen for one provider, after switching to the other: that provider's default.
    await cloud.synthesize("gemini", "Hi.", "nova")
    await cloud.synthesize("openai", "Hi.", "nova")
    gemini_voice = json.loads(seen[2].content)["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]
    assert gemini_voice["voiceName"] == "Kore" and json.loads(seen[3].content)["voice"] == "nova"


async def test_missing_keys_and_errors_say_what_is_wrong():
    cloud = speech([], lambda r: httpx.Response(429))
    with pytest.raises(VoiceError, match="HTTP 429"):
        await cloud.synthesize("openai", "Hi.")

    async def no_key(_provider: str) -> str:
        return ""
    with pytest.raises(VoiceError, match="no Groq key"):
        await CloudSpeech(httpx.AsyncClient(), no_key).transcribe("groq", np.zeros(10, np.float32))


async def test_through_the_worker_the_core_hears_and_speaks_for_it(tmp_path):
    """stt and tts in the cloud: the worker sends the utterance up and asks for each sentence."""
    sherpa = pytest.importorskip("sherpa_onnx")  # noqa: F841
    from test_voice import models as _m, say  # noqa: F401
    from test_voice_controller import controller, states, until
    from agent_harness import Harness
    from pathlib import Path
    from mei.voice import local
    root = Path.home() / ".cache/mei-spikes/0c/models"
    if not (root / "silero_vad.onnx").exists():
        pytest.skip("voice models not downloaded")

    class FakeCloud:
        heard: list[int] = []
        said: list[str] = []

        async def transcribe(self, backend, audio):
            self.heard.append(len(audio))
            return "What's the weather like?"

        async def synthesize(self, backend, text, voice=""):
            self.said.append(text)
            return Speech(np.zeros(8000, np.float32), 16000)

    h = Harness(tmp_path, script=[{"text": "Sunny. Warm too."}])
    mic = await say(local.piper(root), 0.3, "What's the weather like?", 8.0)
    v, seen = controller(h, root, tmp_path, mic)
    cloud = FakeCloud()
    v._cloud = cloud
    await v.apply(VoiceSettings(enabled=True, stt="groq", tts="openai"))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: "speaking" in states(seen) and states(seen)[-1] == "idle")
    assert cloud.heard and cloud.heard[0] > 16000  # the whole utterance went up once
    assert cloud.said == ["Sunny.", "Warm too."]
    assert len(np.fromfile(tmp_path / "played.f32", dtype=np.float32)) == 16000  # both sentences played
    await v.stop()


async def test_when_the_cloud_fails_this_computer_hears_and_speaks_instead(tmp_path):
    """No key, offline, or an HTTP error: Kroko writes the utterance down and Piper says the reply,
    and voice's note says why, until the cloud answers again."""
    pytest.importorskip("sherpa_onnx")
    from test_voice import say
    from test_voice_controller import controller, states, until
    from agent_harness import Harness
    from pathlib import Path
    from mei.voice import local
    from mei.store import repo
    root = Path.home() / ".cache/mei-spikes/0c/models"
    if not (root / "silero_vad.onnx").exists():
        pytest.skip("voice models not downloaded")

    class DownCloud:
        async def transcribe(self, backend, audio):
            raise VoiceError("cloud speech", "Groq can't be reached (ConnectError)")

        async def synthesize(self, backend, text, voice=""):
            raise VoiceError("cloud speech", "no OpenAI key: add one in Settings → Model provider")

    h = Harness(tmp_path, script=[{"text": "Sunny and warm."}])
    v, seen = controller(h, root, tmp_path, await say(local.piper(root), 0.3, "What's the weather like?", 8.0))
    v._cloud = DownCloud()
    await v.apply(VoiceSettings(enabled=True, stt="groq", tts="openai"))
    await v.wait_ready()
    await v.listen(None)
    await until(lambda: "speaking" in states(seen) and states(seen)[-1] == "idle")
    [conversation] = repo.list_conversations(h.store)
    user = next(m for m in repo.history(h.store, conversation["id"]) if m["role"] == "user")
    assert "weather" in user["content"].lower()  # written down by Kroko
    assert len(np.fromfile(tmp_path / "played.f32", dtype=np.float32)) > 8000  # said by Piper
    assert v.note.startswith("no OpenAI key") and v.note.endswith("Mei spoke with this computer's voice")
    await v.stop()
