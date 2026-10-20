"""IPC protocol v1 between the runtime and its clients (architecture §12, ADR 0003).

Methods take one JSON string and return one JSON string. Events are `Event(s)` signals sent
unicast to attached clients. This module is the single definition of those shapes; the
TypeScript side mirrors it in src/runtime/protocol.ts and both are checked against the shared
fixtures in protocol/v1/fixtures/.
"""

from typing import Literal

import msgspec

PROTOCOL_MAJOR = 2  # 2.0: the runtime owns all provider settings (Config.active + Config.providers)
PROTOCOL_MINOR = 0
BUS_NAME = "com.andystmc.Mei1"
OBJECT_PATH = "/com/andystmc/Mei1"
INTERFACE = "com.andystmc.Mei1.Runtime"
ERROR_PREFIX = "com.andystmc.Mei1.Error"

MAX_INPUT_CHARS = 100_000
MAX_ID_CHARS = 128

# Durable events carry a global `seq`; ephemeral ones don't and may be lost on reconnect.
DURABLE_EVENTS = frozenset({
    "conversation.created",
    "conversation.deleted",
    "message.completed",
    "task.accepted",
    "task.state_changed",
    "model.started",
    "task.finished",
    "config.changed",
})
EPHEMERAL_EVENTS = frozenset({"message.delta", "runtime.notice"})


class Envelope(msgspec.Struct, kw_only=True):
    v: int = PROTOCOL_MAJOR
    type: str
    event_id: str
    epoch: str
    at: str
    required: bool = True
    seq: int | None = None
    conversation_id: str | None = None
    task_id: str | None = None
    payload: dict = msgspec.field(default_factory=dict)


class ProtocolError(Exception):
    """A request the runtime refuses. `name` becomes the D-Bus error suffix."""

    def __init__(self, name: Literal["InvalidArgument", "NotFound", "Conflict", "Busy", "Unsupported"],
                 message: str) -> None:
        super().__init__(message)
        self.name = name
        self.message = message


# ── Commands ────────────────────────────────────────────────────────────────


class ClientInfo(msgspec.Struct):
    kind: str
    version: str = ""


class HelloArgs(msgspec.Struct):
    client: ClientInfo
    protocol: tuple[int, int]


class AttachArgs(msgspec.Struct):
    scope: str = "all"  # "all" or a conversation id
    after_seq: int = 0


class SubmitInputArgs(msgspec.Struct):
    command_id: str
    text: str
    conversation_id: str | None = None


class TaskCommandArgs(msgspec.Struct):
    command_id: str
    task_id: str


class ConversationCommandArgs(msgspec.Struct):
    command_id: str
    conversation_id: str


class ProviderConfig(msgspec.Struct, kw_only=True):
    """The user's provider preferences. No secrets: the key is looked up in the keyring by `id`.

    The runtime resolves endpoint, wire format, auth style and headers from its provider profiles.
    """

    id: str = ""  # a provider profile id ("gemini", "openrouter", …), "fake", or "" for none
    model: str = ""
    url: str = ""  # optional override of the profile's endpoint
    mode: str = ""  # OpenCode: "go" or "zen"
    thinking: str = ""  # DeepSeek: "enabled", "disabled", or "" for the provider default
    reasoning_effort: str = ""  # DeepSeek: "low", "high", "max"
    options: dict = msgspec.field(default_factory=dict)  # fake provider script (tests, offline work)


class ProviderSettings(msgspec.Struct, kw_only=True):
    """What the user chose for one provider. Same fields as ProviderConfig, without the id."""

    model: str = ""
    url: str = ""
    mode: str = ""
    thinking: str = ""
    reasoning_effort: str = ""
    options: dict = msgspec.field(default_factory=dict)


class Privacy(msgspec.Struct, kw_only=True):
    # None keeps conversations until the user deletes them (the default, owner decision §14.4).
    conversation_retention_days: int | None = None


class Config(msgspec.Struct, kw_only=True):
    active: str = ""  # provider id used for new tasks
    providers: dict[str, ProviderSettings] = msgspec.field(default_factory=dict)
    privacy: Privacy = msgspec.field(default_factory=Privacy)


def active_provider(config: Config) -> ProviderConfig:
    settings = config.providers.get(config.active, ProviderSettings())
    return ProviderConfig(id=config.active, **msgspec.structs.asdict(settings))


class UpdateConfigArgs(msgspec.Struct):
    revision: int
    config: Config


class ListModelsArgs(msgspec.Struct):
    provider: str
    url: str = ""


class GetLogsArgs(msgspec.Struct):
    after: int = 0


def decode_args(data: str, kind: type):
    try:
        args = msgspec.json.decode(data or "{}", type=kind)
    except msgspec.ValidationError as e:
        raise ProtocolError("InvalidArgument", str(e)) from None
    except msgspec.DecodeError as e:
        raise ProtocolError("InvalidArgument", f"invalid JSON: {e}") from None
    for field in ("command_id", "task_id", "conversation_id"):
        value = getattr(args, field, None)
        if value is not None and (not value or len(value) > MAX_ID_CHARS):
            raise ProtocolError("InvalidArgument", f"{field} must be 1–{MAX_ID_CHARS} characters")
    return args


def encode(value) -> str:
    return msgspec.json.encode(value).decode()


def json_schema() -> dict:
    """JSON Schema for the commands and the event envelope, for tooling and docs."""
    kinds = [Envelope, HelloArgs, AttachArgs, SubmitInputArgs, TaskCommandArgs,
             ConversationCommandArgs, UpdateConfigArgs, Config, ListModelsArgs, GetLogsArgs]
    _schemas, components = msgspec.json.schema_components(kinds)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"Mei runtime protocol {PROTOCOL_MAJOR}.{PROTOCOL_MINOR}",
            "$defs": components}
