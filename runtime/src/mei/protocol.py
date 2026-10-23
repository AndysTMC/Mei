"""The IPC protocol between the runtime and its clients (architecture §12, ADR 0003).

Methods take one JSON string and return one JSON string. Events are `Event(s)` signals sent
unicast to attached clients. This module is the single definition of those shapes; the
TypeScript side mirrors it in src/runtime/protocol.ts and both are checked against the shared
fixtures in protocol/fixtures/.
"""

from typing import Annotated, Literal

import msgspec

PROTOCOL_MAJOR = 2  # 2.0: the runtime owns all provider settings (Config.active + Config.providers)
PROTOCOL_MINOR = 4  # 2.4: voice; 2.3: memory; 2.2: the agent loop (actions, approvals, questions, grants)
BUS_NAME = "com.andystmc.Mei1"
EXTENSION_UUID = "mei@andystmc.com"  # the Shell extension this runtime pairs with
OBJECT_PATH = "/com/andystmc/Mei1"
INTERFACE = "com.andystmc.Mei1.Runtime"
ERROR_PREFIX = "com.andystmc.Mei1.Error"

MAX_INPUT_CHARS = 100_000
MAX_ATTACHMENT_CHARS = 8_000
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
    # 2.2: the agent loop
    "plan.updated",
    "action.proposed",
    "policy.decided",
    "action.started",
    "action.updated",
    "action.finished",
    "approval.requested",
    "approval.resolved",
    "input.requested",
    "input.answered",
    "grant.created",
    "grant.revoked",
    # 2.3: memory
    "memory.saved",
    "memory.pending_review",
    "memory.updated",
    "memory.deleted",
})
EPHEMERAL_EVENTS = frozenset({"message.delta", "runtime.notice", "voice.state", "voice.partial"})


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

    def __init__(self, name: Literal["InvalidArgument", "NotFound", "Conflict", "Busy", "Unsupported", "AccessDenied"],
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
    bridge: str = ""  # the Shell's ShellBridge object path on its own connection (§12.6)


class AttachArgs(msgspec.Struct):
    scope: str = "all"  # "all" or a conversation id
    after_seq: int = 0


class Attachment(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """What "Ask about this" attaches (§18.4): the focused window and the selected text. The person
    chose to attach it, but others wrote it (a web page, a document), so it is untrusted content."""

    kind: Literal["selection"] = "selection"
    app_id: Annotated[str, msgspec.Meta(max_length=200)] = ""
    window_title: Annotated[str, msgspec.Meta(max_length=500)] = ""
    text: Annotated[str, msgspec.Meta(max_length=MAX_ATTACHMENT_CHARS)] = ""


class SubmitInputArgs(msgspec.Struct):
    command_id: str
    text: str
    conversation_id: str | None = None
    attachment: Attachment | None = None  # 2.3
    source: Literal["text", "voice"] = "text"  # 2.4: spoken (the reply is spoken back, kept short)


class TaskCommandArgs(msgspec.Struct):
    command_id: str
    task_id: str


class ConversationCommandArgs(msgspec.Struct):
    command_id: str
    conversation_id: str


class ResolveApprovalArgs(msgspec.Struct):
    command_id: str
    approval_id: str
    decision: Literal["allow", "deny"]
    scope: Literal["once", "task", "always"] = "once"


class AnswerInputArgs(msgspec.Struct):
    command_id: str
    request_id: str
    value: str | dict[str, str | bool]


class RevokeGrantArgs(msgspec.Struct):
    command_id: str
    grant_id: str


class MemoriesArgs(msgspec.Struct):
    query: str = ""
    status: Literal["active", "pending_review", "archived", ""] = ""


class MemoryPatch(msgspec.Struct, kw_only=True, omit_defaults=True):
    text: str | None = None
    status: Literal["active", "archived"] | None = None
    pinned: bool | None = None
    sensitivity: Literal["normal", "local_only"] | None = None


class UpdateMemoryArgs(msgspec.Struct):
    command_id: str
    memory_id: str
    patch: MemoryPatch


class ForgetMemoryArgs(msgspec.Struct):
    command_id: str
    memory_id: str | None = None  # None with `everything`: forget every memory
    everything: bool = False


class ProviderConfig(msgspec.Struct, kw_only=True):
    """The user's provider preferences. No secrets: the key is looked up in the keyring by `id`.

    The runtime resolves endpoint, wire format, auth style and headers from its provider profiles.
    """

    id: str = ""  # a provider profile id ("gemini", "openrouter", …), "fake", or "" for none
    model: str = ""
    url: str = ""  # optional override of the profile's endpoint
    mode: str = ""  # unused since OpenCode was retired; kept so stored settings still decode
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
    # What file contents may go to a cloud model (§13.5): only from files the person pointed at
    # (the default), any file Mei reads, or none. Local models always see what Mei reads.
    cloud_files: Literal["pointed", "always", "never"] = "pointed"


class Approvals(msgspec.Struct, kw_only=True):
    # Which actions go ahead without a card (§13.2). The floor rules hold under every preset.
    preset: Literal["cautious", "balanced", "hands_off"] = "balanced"


class Clients(msgspec.Struct, kw_only=True):
    # Whether programs other than Mei's own Shell extension may give Mei requests (§13.7). Off by
    # default: a request carries the person's authority, so any local program could otherwise
    # have Mei act on things "the person named".
    external_input: bool = False


class MemorySettings(msgspec.Struct, kw_only=True):
    enabled: bool = True  # recall memories into tasks, and let Mei save new ones
    auto_save: bool = True  # save facts Mei infers, not only what the person asks it to remember (§17.4)


class VoiceSettings(msgspec.Struct, kw_only=True):
    # Voice (§11, decision 0017). Off until the person turns it on in setup or Settings.
    enabled: bool = False
    speak_replies: bool = True  # answer out loud when spoken to
    # Speech to text: on this computer (Kroko), or a cloud provider, which then hears the person's voice.
    stt: Literal["local", "openai", "groq"] = "local"
    # Speech: Piper starts at once; Kokoro sounds more natural (slower on a CPU); cloud voices get Mei's replies.
    tts: Literal["piper", "kokoro", "openai", "gemini"] = "piper"
    voice: str = "amy"  # Piper voice
    cloud_voice: str = ""  # the provider's voice name; "" = its default
    kokoro_speaker: int = 0
    speed: Annotated[float, msgspec.Meta(ge=0.5, le=2.0)] = 1.0
    # For Kokoro (decision 0019): "auto"/"gpu", the GPU on demand when there is one and its engine is
    # downloaded, woken while the person talks, let go after gpu_idle_min unused; "cpu", never.
    device: Literal["auto", "cpu", "gpu"] = "auto"
    gpu_idle_min: Annotated[int, msgspec.Meta(ge=1, le=60)] = 5
    # Interrupt by talking over Mei. Off by default: with speakers it relies on echo cancellation,
    # which hasn't been measured in a real room (decision 0021); with earphones it is reliable.
    barge_in: bool = False
    # While Mei speaks, hear the microphone with Mei's own voice taken out (PipeWire's echo
    # canceller), so talking over it works with speakers too (decision 0021).
    echo_cancel: bool = True
    wake_word: bool = False  # "Hey Mei": off by default, it misses the latency target (decision 0017)
    wake_pause: bool = True  # stop listening for "Hey Mei" while another app records (decision 0023)
    end_silence_ms: Annotated[int, msgspec.Meta(ge=300, le=2000)] = 500
    mic: str = ""  # a PipeWire node name; "" follows the system default
    output: str = ""


class VoiceDownloadArgs(msgspec.Struct):
    models: list[str]  # ids from VoiceModels (VoiceDownload and VoiceRemove)


class VoiceListenArgs(msgspec.Struct):
    conversation_id: str | None = None  # the conversation the popup shows; None starts a new one
    # Dictation (the mic button): hear one utterance and hand its words back (voice.partial with
    # "dictation"), to go into the input box; nothing is sent and nothing is said.
    dictate: bool = False


class Config(msgspec.Struct, kw_only=True):
    active: str = ""  # provider id used for new tasks
    providers: dict[str, ProviderSettings] = msgspec.field(default_factory=dict)
    privacy: Privacy = msgspec.field(default_factory=Privacy)
    approvals: Approvals = msgspec.field(default_factory=Approvals)
    clients: Clients = msgspec.field(default_factory=Clients)
    memory: MemorySettings = msgspec.field(default_factory=MemorySettings)
    voice: VoiceSettings = msgspec.field(default_factory=VoiceSettings)


def active_provider(config: Config) -> ProviderConfig:
    return provider_config(config, config.active)


def provider_config(config: Config, provider_id: str) -> ProviderConfig:
    settings = config.providers.get(provider_id, ProviderSettings())
    return ProviderConfig(id=provider_id, **msgspec.structs.asdict(settings))


class UpdateConfigArgs(msgspec.Struct):
    revision: int
    config: Config


class ListModelsArgs(msgspec.Struct):
    provider: str
    url: str = ""


class GetLogsArgs(msgspec.Struct):
    after: int = 0


class SetupApplyArgs(msgspec.Struct):
    step: str
    choices: dict = msgspec.field(default_factory=dict)


class TestProviderArgs(msgspec.Struct):
    provider: str = ""  # empty: the active provider


def decode_args(data: str, kind: type):
    try:
        args = msgspec.json.decode(data or "{}", type=kind)
    except msgspec.ValidationError as e:
        raise ProtocolError("InvalidArgument", str(e)) from None
    except msgspec.DecodeError as e:
        raise ProtocolError("InvalidArgument", f"invalid JSON: {e}") from None
    for field in ("command_id", "task_id", "conversation_id", "approval_id", "request_id", "grant_id", "memory_id"):
        value = getattr(args, field, None)
        if value is not None and (not value or len(value) > MAX_ID_CHARS):
            raise ProtocolError("InvalidArgument", f"{field} must be 1–{MAX_ID_CHARS} characters")
    return args


def encode(value) -> str:
    return msgspec.json.encode(value).decode()


def json_schema() -> dict:
    """JSON Schema for the commands and the event envelope, for tooling and docs."""
    kinds = [Envelope, HelloArgs, AttachArgs, SubmitInputArgs, TaskCommandArgs,
             ConversationCommandArgs, UpdateConfigArgs, Config, ListModelsArgs, GetLogsArgs, SetupApplyArgs,
             TestProviderArgs, ResolveApprovalArgs, AnswerInputArgs, RevokeGrantArgs, MemoriesArgs,
             UpdateMemoryArgs, ForgetMemoryArgs]
    _schemas, components = msgspec.json.schema_components(kinds)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"Mei runtime protocol {PROTOCOL_MAJOR}.{PROTOCOL_MINOR}",
            "$defs": components}
