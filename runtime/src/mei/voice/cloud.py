"""Cloud speech, in the core (decision 0017): the voice worker has no network, so it hands utterances
and sentences to these over its pipe. Keys are the providers' own, from the keyring, and go only to
each provider's fixed endpoint below (decision 0006).

Choosing a cloud backend sends the person's voice (speech to text) or Mei's replies (speech) to
that provider; Settings says so where the choice is made (§11.5).
"""

import base64
import io
import wave
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import numpy as np

from .parts import SAMPLE_RATE, Speech, VoiceError

KeyFor = Callable[[str], Awaitable[str]]
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class Endpoint:
    provider: str  # whose key: the same id as the chat provider
    label: str
    url: str
    model: str
    voice: str = ""  # the default
    voices: tuple[str, ...] = ()  # the provider's others, to choose from in Settings


STT = {"openai": Endpoint("openai", "OpenAI", "https://api.openai.com/v1/audio/transcriptions", "gpt-4o-mini-transcribe"),
       "groq": Endpoint("groq", "Groq", "https://api.groq.com/openai/v1/audio/transcriptions", "whisper-large-v3-turbo")}
TTS = {"openai": Endpoint("openai", "OpenAI", "https://api.openai.com/v1/audio/speech", "gpt-4o-mini-tts", "alloy",
                          ("ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")),
       "gemini": Endpoint("gemini", "Gemini", "https://generativelanguage.googleapis.com/v1beta/models/"
                          "gemini-2.5-flash-preview-tts:generateContent", "gemini-2.5-flash-preview-tts", "Kore",
                          ("Zephyr", "Puck", "Charon", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
                           "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
                           "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
                           "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"))}


class CloudSpeech:
    def __init__(self, client: httpx.AsyncClient, key_for: KeyFor) -> None:
        self._client = client
        self._key_for = key_for

    async def transcribe(self, backend: str, audio: np.ndarray) -> str:
        end = STT.get(backend)
        if end is None:
            raise VoiceError("speech to text", f"no cloud backend {backend!r}")
        key = await self._key(end)
        files = {"file": ("speech.wav", wav(audio), "audio/wav")}
        response = await self._post(end, files=files, data={"model": end.model, "response_format": "json"},
                                    headers={"Authorization": f"Bearer {key}"})
        return str(response.json().get("text", "")).strip()

    async def synthesize(self, backend: str, text: str, voice: str = "") -> Speech:
        end = TTS.get(backend)
        if end is None:
            raise VoiceError("speech", f"no cloud backend {backend!r}")
        key = await self._key(end)
        voice = voice if voice in end.voices else end.voice  # one of another provider's: this one's default
        if backend == "gemini":
            body = {"contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
            response = await self._post(end, json=body, headers={"x-goog-api-key": key})
            try:
                part = response.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            except (KeyError, IndexError, TypeError, ValueError):
                raise VoiceError("speech", f"{end.label} answered without audio") from None
            return Speech(from_s16(base64.b64decode(part["data"])), _rate(part.get("mimeType", ""), 24_000))
        body = {"model": end.model, "input": text, "voice": voice, "response_format": "pcm"}
        response = await self._post(end, json=body, headers={"Authorization": f"Bearer {key}"})
        return Speech(from_s16(response.content), 24_000)  # OpenAI's "pcm": 24 kHz, 16-bit, mono

    async def _key(self, end: Endpoint) -> str:
        key = await self._key_for(end.provider)
        if not key:
            raise VoiceError("cloud speech", f"no {end.label} key: add one in Settings → Model provider")
        return key

    async def _post(self, end: Endpoint, **kw) -> httpx.Response:
        try:
            response = await self._client.post(end.url, timeout=TIMEOUT, follow_redirects=False, **kw)
        except httpx.HTTPError as e:
            raise VoiceError("cloud speech", f"{end.label} can't be reached ({type(e).__name__})") from None
        if response.status_code != 200:
            raise VoiceError("cloud speech", f"{end.label}: HTTP {response.status_code}")
        return response


def wav(audio: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    """16-bit mono WAV, which every transcription API takes."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()


def from_s16(data: bytes) -> np.ndarray:
    return np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0


def _rate(mime: str, default: int) -> int:
    """`audio/L16;codec=pcm;rate=24000` → 24000."""
    for part in mime.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "rate" and value.isdigit():
            return int(value)
    return default
