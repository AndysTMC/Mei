"""The voice worker's protocol with the core: one JSON object per line on the worker's stdin
(commands) and stdout (events). Typed both ways, so neither side acts on a malformed message."""

from typing import Literal

import msgspec

from .parts import Device


class Command(msgspec.Struct, tag_field="op", kw_only=True):
    pass


class Load(Command, tag="load"):
    models: str
    # "core": a cloud backend in the core does it (the worker has no network): the worker sends the
    # utterance up (Transcribe), or asks for each sentence's audio (Synthesize). Kroko still gives
    # the live partials either way.
    stt: Literal["kroko", "core"] = "kroko"
    tts: Literal["piper", "kokoro", "core"] = "piper"
    voice: str = "amy"  # Piper voice
    speaker: int = 0  # Kokoro speaker id
    speed: float = 1.0
    device: Device = "auto"
    wake: bool = False
    wake_threshold: float = 0.25
    barge_in: bool = False  # interrupt by talking: only with earphones (spike 0c)
    end_silence_s: float = 0.5
    mic: str = ""  # PipeWire node; "" = the default
    output: str = ""
    # Test and setup-check backends (recorded.py): never used for real conversations.
    source_file: str = ""
    source_realtime: bool = True
    sink_file: str = ""


class Listen(Command, tag="listen"):
    pass


class DoneTalking(Command, tag="done_talking"):
    pass


class CancelListen(Command, tag="cancel_listen"):
    pass


class Say(Command, tag="say"):
    text: str


class End(Command, tag="end"):
    pass


class StopSpeaking(Command, tag="stop_speaking"):
    pass


class Arm(Command, tag="arm"):
    on: bool


class Suspend(Command, tag="suspend"):
    pass


class Resume(Command, tag="resume"):
    pass


class Diagnose(Command, tag="diagnose"):
    pass


class Quit(Command, tag="quit"):
    pass


class Transcript(Command, tag="transcript"):
    """The core's answer to Transcribe."""
    id: str
    text: str = ""
    error: str = ""


class Audio(Command, tag="audio"):
    """The core's answer to Synthesize: mono float32 samples, base64."""
    id: str
    rate: int = 0
    pcm: str = ""
    error: str = ""


AnyCommand = (Load | Listen | DoneTalking | CancelListen | Say | End | StopSpeaking | Arm | Suspend | Resume
              | Diagnose | Quit | Transcript | Audio)


class Event(msgspec.Struct, tag_field="ev", kw_only=True):
    pass


class Ready(Event, tag="ready"):
    stt: str
    tts: str
    device: str  # where speech is synthesized: "cpu" or "gpu"
    note: str = ""  # why not the GPU, if it was wanted
    wake: bool = False


class Failed(Event, tag="error"):
    part: str
    message: str


class Listening(Event, tag="listening"):
    pass


class SpeechStarted(Event, tag="speech_started"):
    pass


class Partial(Event, tag="partial"):
    text: str


class Final(Event, tag="final"):
    text: str


class NoSpeech(Event, tag="no_speech"):
    pass


class Speaking(Event, tag="speaking"):
    pass


class Spoken(Event, tag="spoken"):
    stopped: bool = False


class BargeIn(Event, tag="barge_in"):
    pass


class Woke(Event, tag="woke"):
    pass


class Suspended(Event, tag="suspended"):
    pass


class Transcribe(Event, tag="transcribe"):
    """Speech to text by the core: one utterance, mono float32 at 16 kHz, base64."""
    id: str
    pcm: str


class Synthesize(Event, tag="synthesize"):
    """Text to speech by the core: answer with Audio."""
    id: str
    text: str


class Diagnosis(Event, tag="diagnosis"):
    network: bool
    home_visible: bool
    session_bus: bool
    pulse_socket: bool


AnyEvent = (Ready | Failed | Listening | SpeechStarted | Partial | Final | NoSpeech | Speaking | Spoken | BargeIn | Woke
            | Suspended | Diagnosis | Transcribe | Synthesize)

# One message per line; a line can carry audio (up to a 30 s utterance or a long sentence, base64).
MAX_LINE = 8 << 20

_commands = msgspec.json.Decoder(AnyCommand)
_events = msgspec.json.Decoder(AnyEvent)
_encoder = msgspec.json.Encoder()


def encode(message: Command | Event) -> bytes:
    return _encoder.encode(message) + b"\n"


def command(line: bytes) -> Command:
    return _commands.decode(line)


def event(line: bytes) -> Event:
    return _events.decode(line)
