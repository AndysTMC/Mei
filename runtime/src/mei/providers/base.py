"""Provider-neutral model interface (architecture §16).

A request is a list of turns plus the tools the model may call. Tool calls come back as complete
`ToolCalled` events (adapters assemble streamed argument fragments). Some providers need data from
an assistant turn sent back verbatim on the next request (Anthropic thinking signatures, OpenRouter
reasoning details, DeepSeek reasoning); adapters return it as a `Replay` and only the adapter of the
same wire format reads it back.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolSpec:
    name: str  # wire name: letters, digits, `_` and `-`, at most 64 characters (every provider accepts that)
    description: str
    parameters: dict  # JSON Schema of an object, in the portable subset (see capabilities.registry)


@dataclass(frozen=True)
class ToolCall:
    id: str  # the provider's call id, or one the adapter made up when the provider has none
    name: str
    arguments: str  # JSON text as the model wrote it; the runtime validates it, the adapter doesn't
    signature: str = ""  # Gemini's thought signature for this call, which must be sent back with it


@dataclass(frozen=True)
class Replay:
    format: str  # the wire format that produced it: "anthropic", "openai_chat"
    data: dict


@dataclass(frozen=True)
class ChatTurn:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()  # assistant turns
    tool_call_id: str = ""  # tool turns: the call this answers
    name: str = ""  # tool turns: the tool's wire name (Gemini and Ollama match results by name)
    is_error: bool = False  # tool turns: the call failed or was refused
    images: tuple[str, ...] = ()  # tool turns: base64 PNGs (a window's picture), for a model that sees images
    replay: Replay | None = None  # assistant turns


@dataclass(frozen=True)
class ModelRequest:
    messages: list[ChatTurn]
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ThinkingDelta:
    text: str


@dataclass(frozen=True)
class ToolCalled:
    call: ToolCall


@dataclass(frozen=True)
class ReplayData:
    replay: Replay


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Done:
    reason: str = "stop"  # "stop" or "tool_calls"


ModelEvent = TextDelta | ThinkingDelta | ToolCalled | ReplayData | Usage | Done


@dataclass
class ProviderError(Exception):
    message: str
    retryable: bool = False
    status: int | None = None
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class IncompleteResponse(ProviderError):
    """The stream ended without the provider's end-of-reply marker: the answer may be cut off."""

    @classmethod
    def of(cls, label: str) -> "IncompleteResponse":
        return cls(f"{label}: the reply was cut off before it finished", retryable=True)


class Provider(Protocol):
    label: str
    model: str

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...


def replay_for(turn: ChatTurn, wire_format: str) -> dict | None:
    """The turn's replay data if this wire format produced it; data from another format is useless."""
    return turn.replay.data if turn.replay is not None and turn.replay.format == wire_format else None


def tool_groups(messages: list[ChatTurn]) -> list[ChatTurn | list[ChatTurn]]:
    """Messages with each run of consecutive tool results gathered into one list.

    Anthropic and Gemini want every result for one assistant turn in a single message.
    """
    out: list[ChatTurn | list[ChatTurn]] = []
    for turn in messages:
        if turn.role == "tool" and out and isinstance(out[-1], list):
            out[-1].append(turn)
        else:
            out.append([turn] if turn.role == "tool" else turn)
    return out


def arguments_object(arguments: str) -> dict:
    """A call's arguments as an object, for wire formats that carry them as one (not as JSON text).

    Invalid arguments become `{}`: the runtime has already answered that call with an error, and
    the provider rejects anything but an object in that position.
    """
    try:
        value = json.loads(arguments)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def without_images(messages: list[ChatTurn]) -> list[ChatTurn]:
    """The same conversation with no pictures, for a model that turns images away."""
    return [replace(t, images=()) if t.images else t for t in messages]
