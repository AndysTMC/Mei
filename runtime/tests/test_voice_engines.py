"""The voice seams (decision 0029): the engine registry, the turn detector, and the clean-up chain.

The registry's contract: every engine the settings can name is in it, every local one has a builder
in the worker, and archived engines are never offered but stay buildable (so their tests keep running).
"""

import math
import typing

import numpy as np

from mei.protocol import VoiceSettings
from mei.voice import build, engines
from mei.voice.cleanup import Chain, Rules
from mei.voice.models import GTCRN, KOKORO, KROKO, KWS, PIPER, SILERO
from mei.voice.turns import WAIT, WordTurn


def _choices(field: str) -> set[str]:
    return set(typing.get_args(typing.get_type_hints(VoiceSettings)[field]))


def test_every_engine_the_settings_can_name_is_registered():
    assert {e.id for e in engines.ENGINES if e.part == "stt"} == _choices("stt")
    assert {e.id for e in engines.ENGINES if e.part == "tts"} == _choices("tts")


def test_every_local_engine_has_a_builder_in_the_worker():
    worker_id = {"stt": lambda e: "kroko" if e.id == "local" else "core", "tts": lambda e: "core" if e.cloud else e.id}
    for e in engines.ENGINES:
        match e.part:
            case "stt" | "tts":
                assert worker_id[e.part](e) in (build.STT if e.part == "stt" else build.TTS), e
            case "turn":
                assert e.id in build.TURN, e


def test_only_stable_engines_are_offered_unless_experimental_ones_are_asked_for():
    fake = (engines.Engine("a", "turn", "A"), engines.Engine("b", "turn", "B", status="experimental"),
            engines.Engine("c", "turn", "C", status="archived"))
    real, engines.ENGINES = engines.ENGINES, fake
    try:
        assert [e.id for e in engines.offered("turn")] == ["a"]
        assert [e.id for e in engines.offered("turn", experimental=True)] == ["a", "b"]
    finally:
        engines.ENGINES = real


def test_the_models_needed_follow_the_settings():
    assert engines.needed(VoiceSettings()) == (GTCRN, SILERO, KROKO, PIPER["amy"])
    assert engines.needed(VoiceSettings(tts="kokoro", wake_word=True)) == (GTCRN, SILERO, KROKO, KOKORO, KWS)
    assert engines.needed(VoiceSettings(stt="groq", tts="openai", voice="lessac")) == (GTCRN, SILERO, KROKO, PIPER["lessac"])
    # Noise suppression is offered, but voice starts without it.
    assert engines.needed(VoiceSettings(), required_only=True) == (SILERO, KROKO, PIPER["amy"])


# ── The turn detector ────────────────────────────────────────────────────────


class Recording:
    """A detector that says what it was asked, for the Listener's side of the contract."""

    name, audio_s = "recording", 2.0

    def __init__(self, answer: float) -> None:
        self.answer = answer
        self.asked: list[tuple[str, int]] = []

    def pause_for(self, said: str, audio: np.ndarray) -> float:
        self.asked.append((said, len(audio)))
        return self.answer


def test_the_word_list_detector_never_waits_forever():
    for said in ("", "and", "turn on dark mode", "I want um"):
        assert WordTurn(0.8).pause_for(said) < math.inf


async def test_the_listener_asks_the_detector_once_per_pause_and_honours_wait():
    from mei.voice.pipeline import Endpointing, Final, Listener
    from mei.voice.parts import CHUNK

    class Source:
        def __init__(self, pattern: list[bool]) -> None:
            self.pattern = pattern

        async def start(self) -> None: ...
        async def stop(self) -> None: ...

        async def chunks(self, samples: int = CHUNK):
            for loud in self.pattern:
                yield np.full(CHUNK, 0.5 if loud else 0.0, np.float32)

    class Vad:
        quiet = 0.0

        def is_speech(self, chunk) -> bool:
            loud = bool(chunk[0])
            self.quiet = 0.0 if loud else self.quiet + 0.1
            return loud

        def speaking_for(self) -> float:
            return 0.0

        def quiet_for(self) -> float:
            return self.quiet

        def reset(self) -> None:
            self.quiet = 0.0

    class Stt:
        name = "fake"

        def open(self):
            class T:
                async def accept(self, chunk):
                    return None

                async def finish(self):
                    return "hello there"
            return T()

    pattern = [True] * 5 + [False] * 20  # half a second of talk, then two seconds of quiet
    turn = Recording(answer=0.5)
    heard = [h async for h in Listener(Source(pattern), Vad(), Stt(), Endpointing(max_s=30), turn).listen()]
    assert isinstance(heard[-1], Final) and len(turn.asked) == 1  # asked once, when the pause began
    assert 0 < turn.asked[0][1] <= 2.0 * 16_000  # given this turn's audio, no more than it asked for

    waiting = Recording(answer=WAIT)
    heard = [h async for h in Listener(Source(pattern), Vad(), Stt(), Endpointing(max_s=30), waiting).listen()]
    assert len(waiting.asked) == 1 and heard  # waited out the whole recording: nothing ended the turn early


# ── The clean-up chain ───────────────────────────────────────────────────────


def test_fillers_and_stutters_go_and_the_raw_words_stay():
    cleaned = Chain([Rules()])("um I I want to uh go to the the store")
    assert cleaned.text == "I want to go to the store" and cleaned.raw == "um I I want to uh go to the the store"
    assert cleaned.changed


def test_words_meant_twice_and_words_that_look_like_fillers_are_kept():
    rules = Rules()
    assert rules.clean("very very good") == "Very very good"
    assert rules.clean("no no stop") == "No no stop"
    assert rules.clean("the hummus is good") == "The hummus is good"
    assert rules.clean("umbrella please") == "Umbrella please"
    assert rules.clean("i think i'm done, uh, thanks") == "I think I'm done, thanks"


def test_a_step_that_fails_or_empties_the_text_leaves_it_as_it_was():
    class Broken:
        name = "broken"

        def clean(self, text: str) -> str:
            raise RuntimeError("no")

    assert Chain([Broken(), Rules()])("uh hello").text == "Hello"
    assert Chain([Rules()])("mmm").text == "mmm"


# ── The words Mei listens for ───────────────────────────────────────────────


def test_misheard_names_are_put_back_and_ordinary_words_are_left_alone():
    from mei.voice.cleanup import Boost
    boost = Boost(["Mukesh Thatikonda", "Kokoro", "Krita", "Inkscape", "Firefox", "Files", "Settings"])
    assert boost.clean("send this to Mukes that aconda") == "send this to Mukesh Thatikonda"
    assert boost.clean("switch the voice to Kakoro") == "switch the voice to Kokoro"  # "to" isn't part of the name
    assert boost.clean("open Creta and make a canvas") == "open Krita and make a canvas"
    assert boost.clean("start inks cape please") == "start Inkscape please"
    assert boost.clean("open fire fox") == "open Firefox"
    for ordinary in ("a crate of apples", "I need to file this", "the setting sun", "open my files", "credit card"):
        assert boost.clean(ordinary) == ordinary


def test_the_words_come_from_apps_memories_and_recent_messages(tmp_path, monkeypatch):
    from mei.voice import boost
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "org.kde.krita.desktop").write_text("[Desktop Entry]\nName=Krita\nExec=krita\n")
    (apps / "hidden.desktop").write_text("[Desktop Entry]\nName=Secret Helper\nNoDisplay=true\n")
    (apps / "translated.desktop").write_text("[Desktop Entry]\nName=Inkscape\nName[de]=Inkskape\n[Desktop Action new]\nName=New\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    monkeypatch.setattr(boost.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(boost, "SYSTEM_FLATPAK", tmp_path / "none")
    assert boost.app_names() == ["Krita", "Inkscape"]

    class Store:
        def read(self, sql, params=()):
            if "memories" in sql:
                return [{"text": "The person's sister is called Anjali Rao."}]
            return [{"content": "Send the invoice to Anjali and to Thatikonda."}, {"content": "Open the Files app."}]
    assert boost.learned(Store()) == ["Anjali", "Thatikonda"]  # "Files" is an ordinary word; "Rao" too short
    found = boost.words(Store(), [" Kokoro ", ""])
    assert found["yours"] == ["Kokoro"] and found["learned"][0] == "Anjali"


# ── While Mei works on a spoken request ─────────────────────────────────────


async def test_the_tone_then_check_ins_until_stopped():
    import asyncio
    from mei.voice.waiting import Waiting
    cues: list[str] = []
    waiting = Waiting(cues.append, tone_after_s=0.05, check_ins=((0.15, "Still on it."), (0.3, "Still working.")))
    waiting.start()
    await asyncio.sleep(0.2)
    assert cues == ["", "Still on it."]
    waiting.start()  # thinking again (after an approval): the series starts over
    await asyncio.sleep(0.1)
    assert cues == ["", "Still on it.", ""]
    waiting.stop()  # Mei answered
    await asyncio.sleep(0.4)
    assert cues == ["", "Still on it.", ""] and not waiting.running
