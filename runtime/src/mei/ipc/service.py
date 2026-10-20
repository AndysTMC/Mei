"""The runtime's D-Bus surface: `com.andystmc.Mei1` (architecture §12, ADR 0003).

Handlers are synchronous. In a single-threaded runtime that makes `Attach` atomic: the client is
registered, the snapshot is taken at seq N, and the reply is queued before any later event can
be emitted, so nothing falls between the snapshot and live delivery.
"""

import logging
import os
from dataclasses import dataclass

import msgspec
from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.constants import NameFlag, RequestNameReply

from mei import protocol
from mei.core.engine import Engine
from mei.protocol import (AttachArgs, ConversationCommandArgs, Envelope, HelloArgs, ProtocolError,
                          SubmitInputArgs, TaskCommandArgs, UpdateConfigArgs, decode_args, encode)
from mei.store import repo

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
    def __init__(self, bus: MessageBus, engine: Engine) -> None:
        self._bus = bus
        self._engine = engine
        self._store = engine.store
        self.clients: dict[str, Client] = {}
        self._kinds: dict[str, str] = {}
        self._methods = {
            "Hello": self._hello, "Attach": self._attach, "Detach": self._detach,
            "GetConversation": self._get_conversation, "SubmitInput": self._submit_input,
            "Cancel": self._cancel, "Resume": self._resume, "DeleteConversation": self._delete_conversation,
            "GetConfig": self._get_config, "UpdateConfig": self._update_config, "Ping": self._ping,
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
        try:
            return Message.new_method_return(msg, "s", [encode(handler(msg.sender, msg.body[0]))])
        except ProtocolError as e:
            return Message.new_error(msg, f"{protocol.ERROR_PREFIX}.{e.name}", e.message)
        except Exception:
            log.exception("%s failed", msg.member)
            return Message.new_error(msg, f"{protocol.ERROR_PREFIX}.Internal", "internal error (see the runtime log)")

    # ── Methods ─────────────────────────────────────────────────────────────

    def _hello(self, sender: str, data: str) -> dict:
        args = decode_args(data, HelloArgs)
        if args.protocol[0] != protocol.PROTOCOL_MAJOR:
            raise ProtocolError("Unsupported", f"runtime speaks protocol {protocol.PROTOCOL_MAJOR}.x")
        self._kinds[sender] = args.client.kind
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

    def _submit_input(self, _sender: str, data: str) -> dict:
        return self._engine.submit_input(decode_args(data, SubmitInputArgs))

    def _cancel(self, _sender: str, data: str) -> dict:
        return self._engine.cancel(decode_args(data, TaskCommandArgs))

    def _resume(self, _sender: str, data: str) -> dict:
        return self._engine.resume(decode_args(data, TaskCommandArgs))

    def _delete_conversation(self, _sender: str, data: str) -> dict:
        return self._engine.delete_conversation(decode_args(data, ConversationCommandArgs))

    def _get_config(self, _sender: str, _data: str) -> dict:
        return self._engine.get_config()

    def _update_config(self, _sender: str, data: str) -> dict:
        return self._engine.update_config(decode_args(data, UpdateConfigArgs))

    def _ping(self, _sender: str, _data: str) -> dict:
        return {"seq": self._store.last_seq()}

    def _streams(self, scope: str) -> list[dict]:
        return [s.view() for s in self._engine.streams.values() if scope in ("all", s.conversation_id)]
