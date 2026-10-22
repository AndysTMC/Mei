"""The runtime's D-Bus surface: `com.andystmc.Mei1` (architecture §12, ADR 0003).

Handlers are synchronous. In a single-threaded runtime that makes `Attach` atomic: the client is
registered, the snapshot is taken at seq N, and the reply is queued before any later event can
be emitted, so nothing falls between the snapshot and live delivery.
"""

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import msgspec
from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.constants import NameFlag, RequestNameReply

from mei import protocol
from mei.capabilities.base import Notifier
from mei.core.engine import Engine
from mei.obs import RECENT
from mei.protocol import (AnswerInputArgs, AttachArgs, ConversationCommandArgs, Envelope, ForgetMemoryArgs,
                          GetLogsArgs, HelloArgs, ListModelsArgs, MemoriesArgs, ProtocolError, ResolveApprovalArgs,
                          RevokeGrantArgs, SetupApplyArgs, SubmitInputArgs, TaskCommandArgs, TestProviderArgs,
                          UpdateConfigArgs, UpdateMemoryArgs, VoiceDownloadArgs, VoiceListenArgs, decode_args,
                          encode)
from mei.providers.profiles import PROFILES
from mei.setup import Setup
from mei.store import repo

from .bridge import ShellBridgeClient
from .notices import Notices
from .peers import shell_check

log = logging.getLogger("mei.ipc")
MAX_REPLAY_EVENTS = 5000
RUNTIME_VERSION = "0.1.0"


class NameTaken(RuntimeError):
    pass


@dataclass
class Client:
    scope: str
    kind: str = ""


class RuntimeService:
    def __init__(self, bus: MessageBus, engine: Engine,
                 list_models: Callable[[str, str], Awaitable[dict]] | None = None,
                 setup: Setup | None = None,
                 test_provider: Callable[[str], Awaitable[dict]] | None = None,
                 is_shell: Callable[[str], Awaitable[bool]] | None = None,
                 notifier: Notifier | None = None, voice=None) -> None:
        self._bus = bus
        self._engine = engine
        self._is_shell = is_shell or shell_check(bus)
        self.bridge: ShellBridgeClient | None = None
        self._notices = Notices(notifier, self._conversation_title)
        self._list_models = list_models
        self._setup = setup
        self._test_provider = test_provider
        self._voice = voice  # VoiceController, or None where voice can't run
        self._store = engine.store
        self.clients: dict[str, Client] = {}
        self._kinds: dict[str, str] = {}
        self._methods = {
            "Hello": self._hello, "Attach": self._attach, "Detach": self._detach,
            "GetConversation": self._get_conversation, "SubmitInput": self._submit_input,
            "Cancel": self._cancel, "Resume": self._resume, "DeleteConversation": self._delete_conversation,
            "GetConfig": self._get_config, "UpdateConfig": self._update_config, "Ping": self._ping,
            "ListProviders": self._list_providers, "ListModels": self._models, "GetLogs": self._get_logs,
            "ClearLogs": self._clear_logs, "SetupStatus": self._setup_status, "SetupApply": self._setup_apply,
            "TestProvider": self._test, "ResolveApproval": self._resolve_approval, "AnswerInput": self._answer_input,
            "ListGrants": self._list_grants, "RevokeGrant": self._revoke_grant,
            "Memories": self._memories, "UpdateMemory": self._update_memory, "ForgetMemory": self._forget_memory,
            "VoiceListen": self._voice_listen, "VoiceStop": self._voice_stop, "VoiceStatus": self._voice_status,
            "VoiceModels": self._voice_models, "VoiceDownload": self._voice_download, "VoiceCheckMic": self._voice_check_mic,
            "VoiceFixMic": self._voice_fix_mic, "VoiceTestSpeaker": self._voice_test_speaker,
            "VoiceDevices": self._voice_devices, "VoiceRemove": self._voice_remove,
        }

    async def start(self) -> None:
        self._bus.add_message_handler(self._on_message)
        await self._bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                     interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                                     body=["type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged'"]))
        reply = await self._bus.request_name(protocol.BUS_NAME, NameFlag.DO_NOT_QUEUE)
        if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
            raise NameTaken(f"{protocol.BUS_NAME} is owned by another process")
        log.info("serving %s as %s", protocol.BUS_NAME, self._bus.unique_name)

    # ── Publisher (used by the engine) ──────────────────────────────────────

    def publish(self, events: list[Envelope]) -> None:
        for event in events:
            self._send(event)
        # The verified bridge, not a client's own claim to be the Shell: a program pretending to be
        # it must not be able to silence these.
        self._notices.on_events(events, shell_attached=self.bridge is not None and self.bridge.name in self.clients)

    def _conversation_title(self, conversation_id: str) -> str:
        row = repo.get_conversation(self._store, conversation_id)
        return row["title"] if row is not None else ""

    def publish_ephemeral(self, event: Envelope) -> None:
        self._send(event)

    def _send(self, event: Envelope) -> None:
        body = encode(event)
        for name, client in self.clients.items():
            if client.scope == "all" or event.conversation_id in (None, client.scope):
                self._bus.send(Message(message_type=MessageType.SIGNAL, destination=name,
                                       path=protocol.OBJECT_PATH, interface=protocol.INTERFACE,
                                       member="Event", signature="s", body=[body]))

    # ── Dispatch ────────────────────────────────────────────────────────────

    def _on_message(self, msg: Message):
        if msg.message_type == MessageType.SIGNAL:
            if msg.member == "NameOwnerChanged" and msg.sender == "org.freedesktop.DBus":
                name, _old, new = msg.body
                if not new and self.bridge is not None and self.bridge.name == name:
                    self.bridge = None  # the Shell went away: windows, clipboard, and launching go with it
                    log.info("the Shell bridge left")
                if not new and (self.clients.pop(name, None) or self._kinds.pop(name, None)):
                    log.info("client %s left", name)
            return None
        if msg.message_type != MessageType.METHOD_CALL or msg.path != protocol.OBJECT_PATH \
                or msg.interface != protocol.INTERFACE:
            return None
        handler = self._methods.get(msg.member)
        if handler is None:
            return Message.new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod", f"no method {msg.member}")
        if msg.signature != "s":
            return Message.new_error(msg, "org.freedesktop.DBus.Error.InvalidArgs", "expected one JSON string")
        if inspect.iscoroutinefunction(handler):
            # Network-bound methods (ListModels) reply later; everything else stays synchronous.
            asyncio.ensure_future(self._reply_async(msg, handler))
            return True
        return self._reply(msg, lambda: handler(msg.sender, msg.body[0]))

    def _reply(self, msg: Message, produce):
        try:
            return Message.new_method_return(msg, "s", [encode(produce())])
        except ProtocolError as e:
            return Message.new_error(msg, f"{protocol.ERROR_PREFIX}.{e.name}", e.message)
        except Exception:
            log.exception("%s failed", msg.member)
            return Message.new_error(msg, f"{protocol.ERROR_PREFIX}.Internal", "internal error (see the runtime log)")

    async def _reply_async(self, msg: Message, handler) -> None:
        try:
            result = await handler(msg.sender, msg.body[0])
            reply = self._reply(msg, lambda: result)
        except ProtocolError as e:
            reply = Message.new_error(msg, f"{protocol.ERROR_PREFIX}.{e.name}", e.message)
        except Exception:
            log.exception("%s failed", msg.member)
            reply = Message.new_error(msg, f"{protocol.ERROR_PREFIX}.Internal", "internal error (see the runtime log)")
        self._bus.send(reply)

    # ── Methods ─────────────────────────────────────────────────────────────

    def _hello(self, sender: str, data: str) -> dict:
        args = decode_args(data, HelloArgs)
        if args.protocol[0] != protocol.PROTOCOL_MAJOR:
            raise ProtocolError("Unsupported", f"runtime speaks protocol {protocol.PROTOCOL_MAJOR}.x")
        self._kinds[sender] = args.client.kind
        if args.bridge:
            asyncio.ensure_future(self._attach_bridge(sender, args.bridge))
        return {"epoch": self._store.epoch, "protocol": [protocol.PROTOCOL_MAJOR, protocol.PROTOCOL_MINOR],
                "runtime_version": RUNTIME_VERSION, "seq": self._store.last_seq(), "pid": os.getpid()}

    def _attach(self, sender: str, data: str) -> dict:
        args = decode_args(data, AttachArgs)
        if args.scope != "all" and repo.get_conversation(self._store, args.scope) is None:
            raise ProtocolError("NotFound", "no such conversation")
        self.clients[sender] = Client(args.scope, self._kinds.get(sender, ""))
        seq = self._store.last_seq()
        streams = self._streams(args.scope)
        if 0 < args.after_seq <= seq and seq - args.after_seq <= MAX_REPLAY_EVENTS:
            events = repo.events_after(self._store, args.after_seq, args.scope)
            return {"epoch": self._store.epoch, "seq": seq, "mode": "replay",
                    "events": [msgspec.to_builtins(e) for e in events], "streams": streams}
        snapshot = ({"conversations": repo.list_conversations(self._store)} if args.scope == "all"
                    else repo.conversation_snapshot(self._store, args.scope))
        return {"epoch": self._store.epoch, "seq": seq, "mode": "snapshot", "snapshot": snapshot, "streams": streams}

    def _detach(self, sender: str, _data: str) -> dict:
        self.clients.pop(sender, None)
        return {}

    def _get_conversation(self, _sender: str, data: str) -> dict:
        conversation_id = msgspec.json.decode(data).get("conversation_id", "") if data else ""
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ProtocolError("InvalidArgument", "conversation_id is required")
        return {"epoch": self._store.epoch, "seq": self._store.last_seq(),
                **repo.conversation_snapshot(self._store, conversation_id),
                "streams": self._streams(conversation_id)}

    async def _submit_input(self, sender: str, data: str) -> dict:
        args = decode_args(data, SubmitInputArgs)
        await self._input_allowed(sender)
        return self._engine.submit_input(args)

    def _cancel(self, _sender: str, data: str) -> dict:
        return self._engine.cancel(decode_args(data, TaskCommandArgs))

    async def _resume(self, sender: str, data: str) -> dict:
        args = decode_args(data, TaskCommandArgs)
        await self._input_allowed(sender)
        return self._engine.resume(args)

    async def _input_allowed(self, sender: str) -> None:
        """New requests (and resuming one) act with the person's authority: Shell only, unless the
        person let other programs in (§13.7)."""
        _revision, config = repo.get_config(self._store)
        if not config.clients.external_input and not await self._is_shell(sender):
            raise ProtocolError("AccessDenied", "only Mei in the top bar can give Mei requests; other programs "
                                                "can be allowed in Mei's settings (clients.external_input)")

    async def _delete_conversation(self, sender: str, data: str) -> dict:
        args = decode_args(data, ConversationCommandArgs)
        await self._shell_only(sender, "delete conversations")
        return self._engine.delete_conversation(args)

    def _get_config(self, _sender: str, _data: str) -> dict:
        return self._engine.get_config()

    async def _update_config(self, sender: str, data: str) -> dict:
        """Settings may change any setting, except who may give Mei requests: a program allowed to
        change that could let itself in (§13.7). Only the Shell turns it on."""
        args = decode_args(data, UpdateConfigArgs)
        _revision, current = repo.get_config(self._store)
        if args.config.clients.external_input and not current.clients.external_input:
            await self._shell_only(sender, "let other programs give Mei requests")
        return self._engine.update_config(args)

    def _ping(self, _sender: str, _data: str) -> dict:
        return {"seq": self._store.last_seq()}

    def _list_providers(self, _sender: str, _data: str) -> dict:
        return {"providers": [{"id": p.id, "label": p.label, "type": p.type, "auth": p.auth, "selectable": p.selectable,
                               "unavailable": p.unavailable, "default_url": p.chat_url,
                               "fallback_models": list(p.fallback_models)} for p in PROFILES.values()]}

    async def _models(self, _sender: str, data: str) -> dict:
        args = decode_args(data, ListModelsArgs)
        if args.provider not in PROFILES:
            raise ProtocolError("NotFound", f"no provider {args.provider!r}")
        if self._list_models is None:
            raise ProtocolError("Unsupported", "model discovery is not available")
        return await self._list_models(args.provider, args.url)

    def _need_setup(self) -> Setup:
        if self._setup is None:
            raise ProtocolError("Unsupported", "setup is not available")
        return self._setup

    async def _setup_status(self, _sender: str, _data: str) -> dict:
        return await self._need_setup().status()

    async def _setup_apply(self, _sender: str, data: str) -> dict:
        args = decode_args(data, SetupApplyArgs)
        return await self._need_setup().apply(args.step, args.choices)

    async def _test(self, _sender: str, data: str) -> dict:
        args = decode_args(data, TestProviderArgs)
        if args.provider and args.provider not in PROFILES:
            raise ProtocolError("NotFound", f"no provider {args.provider!r}")
        if self._test_provider is None:
            raise ProtocolError("Unsupported", "provider tests are not available")
        return await self._test_provider(args.provider)

    def _get_logs(self, _sender: str, data: str) -> dict:
        entries = RECENT.after(decode_args(data, GetLogsArgs).after)
        return {"entries": entries, "last": entries[-1]["id"] if entries else 0}

    def _clear_logs(self, _sender: str, _data: str) -> dict:
        RECENT.clear()
        return {}

    async def _attach_bridge(self, sender: str, path: str) -> None:
        """Only the Shell's own bridge is used: another program offering one could feed Mei false
        window lists or launch things in the Shell's name."""
        if not path.startswith("/") or not await self._is_shell(sender):
            log.warning("ignored a Shell bridge offered by %s", sender)
            return
        self.bridge = ShellBridgeClient(self._bus, sender, path)
        log.info("the Shell bridge is attached")

    # ── Voice (2.4) ──────────────────────────────────────────────────────────

    async def _voice_listen(self, sender: str, data: str) -> dict:
        args = decode_args(data, VoiceListenArgs)
        await self._shell_only(sender, "listen")  # it opens the microphone, and what is said is a request
        voice = self._voice_required()
        await voice.listen(args.conversation_id)
        return {"state": voice.state}

    async def _voice_stop(self, sender: str, _data: str) -> dict:
        await self._shell_only(sender, "stop voice")
        if self._voice is not None:
            await self._voice.hush()
        return {}

    def _voice_status(self, _sender: str, _data: str) -> dict:
        if self._voice is None:
            return {"state": "unavailable", "note": "voice isn't installed"}
        return {"state": self._voice.state, "note": self._voice.note}

    # Setup and Settings (not only the Shell): none of these hands anyone audio. The microphone check
    # returns a level in dB; downloads come from pinned URLs.

    def _voice_models(self, _sender: str, _data: str) -> dict:
        return self._voice_required().models()

    def _voice_download(self, _sender: str, data: str) -> dict:
        args = decode_args(data, VoiceDownloadArgs)
        self._voice_required().download(args.models)
        return {}

    async def _voice_check_mic(self, _sender: str, _data: str) -> dict:
        return await self._voice_required().check_mic()

    async def _voice_fix_mic(self, _sender: str, _data: str) -> dict:
        return await self._voice_required().fix_mic()

    async def _voice_test_speaker(self, _sender: str, _data: str) -> dict:
        await self._voice_required().test_speaker()
        return {}

    async def _voice_devices(self, _sender: str, _data: str) -> dict:
        return await self._voice_required().devices()

    async def _voice_remove(self, _sender: str, data: str) -> dict:
        await self._voice_required().remove(decode_args(data, VoiceDownloadArgs).models)
        return {}

    def _voice_required(self):
        if self._voice is None:
            raise ProtocolError("Unavailable", "voice isn't installed")
        return self._voice

    async def _shell_only(self, sender: str, what: str) -> None:
        if not await self._is_shell(sender):
            raise ProtocolError("AccessDenied", f"only Mei in the top bar can {what}")

    async def _resolve_approval(self, sender: str, data: str) -> dict:
        args = decode_args(data, ResolveApprovalArgs)
        await self._shell_only(sender, "approve actions")
        return self._engine.resolve_approval(args, decided_by=sender)

    async def _answer_input(self, sender: str, data: str) -> dict:
        args = decode_args(data, AnswerInputArgs)
        await self._shell_only(sender, "answer Mei's questions")
        return self._engine.answer_input(args)

    def _memories(self, _sender: str, data: str) -> dict:
        return self._engine.memories(decode_args(data, MemoriesArgs))

    async def _update_memory(self, sender: str, data: str) -> dict:
        args = decode_args(data, UpdateMemoryArgs)
        return self._engine.update_memory(args, from_shell=await self._is_shell(sender))

    def _forget_memory(self, _sender: str, data: str) -> dict:
        return self._engine.forget_memory(decode_args(data, ForgetMemoryArgs))

    def _list_grants(self, _sender: str, _data: str) -> dict:
        return self._engine.list_grants()

    def _revoke_grant(self, _sender: str, data: str) -> dict:
        return self._engine.revoke_grant(decode_args(data, RevokeGrantArgs))

    def _streams(self, scope: str) -> list[dict]:
        return [s.view() for s in self._engine.streams.values() if scope in ("all", s.conversation_id)]
