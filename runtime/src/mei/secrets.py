"""Provider API keys from the Secret Service, under the schema the extension already uses.

Stage 0a: a locked collection makes GetSecrets return nothing *without an error*, so locked items
are checked explicitly and reported as `KeyringLocked`, never as a missing key.
"""

from dbus_fast import Message, MessageType, Variant
from dbus_fast.aio import MessageBus

SERVICE = "org.freedesktop.secrets"
SERVICE_PATH = "/org/freedesktop/secrets"
SERVICE_IFACE = "org.freedesktop.Secret.Service"
SCHEMA = "com.andystmc.mei.provider-api-key"
EXTENSION_ID = "mei@andystmc.com"


class KeyringLocked(Exception):
    pass


class KeyringUnavailable(Exception):
    pass


async def _call(bus: MessageBus, path: str, iface: str, member: str, signature: str = "", body: list | None = None):
    reply = await bus.call(Message(destination=SERVICE, path=path, interface=iface, member=member,
                                   signature=signature, body=body or []))
    if reply.message_type == MessageType.ERROR:
        raise KeyringUnavailable(f"{reply.error_name}: {reply.body[0] if reply.body else ''}")
    return reply.body


async def lookup_provider_key(bus: MessageBus, provider_id: str) -> str | None:
    attrs = {"xdg:schema": SCHEMA, "extension": EXTENSION_ID, "provider": provider_id}
    _output, session = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "OpenSession", "sv", ["plain", Variant("s", "")])
    try:
        unlocked, locked = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "SearchItems", "a{ss}", [attrs])
        if unlocked:
            (secrets,) = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "GetSecrets", "aoo", [unlocked[:1], session])
            if secrets:
                _session, _params, value, _content_type = next(iter(secrets.values()))
                return bytes(value).decode("utf-8")
        if locked:
            raise KeyringLocked("the keyring is locked")
        return None
    finally:
        await _call(bus, session, "org.freedesktop.Secret.Session", "Close")
