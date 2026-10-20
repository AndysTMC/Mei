"""Provider-neutral model interface (architecture §16)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ModelRequest:
    messages: list[ChatTurn]


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ThinkingDelta:
    text: str


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Done:
    reason: str = "stop"


ModelEvent = TextDelta | ThinkingDelta | Usage | Done


@dataclass
class ProviderError(Exception):
    message: str
    retryable: bool = False
    status: int | None = None
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


class Provider(Protocol):
    label: str
    model: str

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
