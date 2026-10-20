"""Provider API keys from the Secret Service, under the schema the extension already uses.

Stage 0a: a locked collection makes GetSecrets return nothing *without an error*, so locked items
are checked explicitly and reported as `KeyringLocked`, never as a missing key.
"""

import asyncio

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


async def store_provider_key(bus: MessageBus, provider_id: str, value: str) -> None:
    """Store (or replace) a provider key in the default collection. Raises KeyringLocked if locked."""
    attrs = {"xdg:schema": SCHEMA, "extension": EXTENSION_ID, "provider": provider_id}
    _output, session = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "OpenSession", "sv", ["plain", Variant("s", "")])
    try:
        (collection,) = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "ReadAlias", "s", ["default"])
        if collection == "/":
            raise KeyringUnavailable("no default keyring collection")
        props = {"org.freedesktop.Secret.Item.Label": Variant("s", f"Mei {provider_id} API key"),
                 "org.freedesktop.Secret.Item.Attributes": Variant("a{ss}", attrs)}
        try:
            _item, prompt = await _call(bus, collection, "org.freedesktop.Secret.Collection", "CreateItem",
                                        "a{sv}(oayays)b", [props, [session, b"", value.encode(), "text/plain"], True])
        except KeyringUnavailable as e:
            if "locked" in str(e).lower():
                raise KeyringLocked("the keyring is locked") from None
            raise
        if prompt != "/":
            await _call(bus, prompt, "org.freedesktop.Secret.Prompt", "Dismiss")
            raise KeyringLocked("the keyring is locked")
    finally:
        await _call(bus, session, "org.freedesktop.Secret.Session", "Close")


async def delete_provider_keys(bus: MessageBus) -> tuple[int, int]:
    """Delete every Mei key (uninstall --purge). Returns (deleted, left); locked items are left."""
    attrs = {"xdg:schema": SCHEMA, "extension": EXTENSION_ID}
    unlocked, locked = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "SearchItems", "a{ss}", [attrs])
    deleted, left = 0, len(locked)
    for item in unlocked:
        (prompt,) = await _call(bus, item, "org.freedesktop.Secret.Item", "Delete")
        if prompt == "/":
            deleted += 1
        else:
            await _call(bus, prompt, "org.freedesktop.Secret.Prompt", "Dismiss")
            left += 1
    return deleted, left


async def _default_collection(bus: MessageBus) -> str | None:
    (collection,) = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "ReadAlias", "s", ["default"])
    return None if collection == "/" else collection


async def keyring_state(bus: MessageBus) -> str:
    """"unlocked", "locked", or "missing" (no Secret Service, or no default keyring)."""
    try:
        collection = await _default_collection(bus)
        if collection is None:
            return "missing"
        (locked,) = await _call(bus, collection, "org.freedesktop.DBus.Properties", "Get", "ss",
                                ["org.freedesktop.Secret.Collection", "Locked"])
    except KeyringUnavailable:
        return "missing"
    return "locked" if locked.value else "unlocked"


async def unlock_keyring(bus: MessageBus, timeout: float = 120.0) -> str:
    """Ask the keyring to unlock; the desktop shows its own password prompt. Returns the new state."""
    collection = await _default_collection(bus)
    if collection is None:
        return "missing"
    _unlocked, prompt = await _call(bus, SERVICE_PATH, SERVICE_IFACE, "Unlock", "ao", [[collection]])
    if prompt != "/":
        done = asyncio.get_running_loop().create_future()
        rule = f"type='signal',interface='org.freedesktop.Secret.Prompt',member='Completed',path='{prompt}'"

        def on_message(msg: Message) -> None:
            if msg.member == "Completed" and msg.path == prompt and not done.done():
                done.set_result(None)

        bus.add_message_handler(on_message)
        await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                               interface="org.freedesktop.DBus", member="AddMatch", signature="s", body=[rule]))
        try:
            await _call(bus, prompt, "org.freedesktop.Secret.Prompt", "Prompt", "s", [""])
            async with asyncio.timeout(timeout):
                await done
        except TimeoutError:
            await _call(bus, prompt, "org.freedesktop.Secret.Prompt", "Dismiss")
        finally:
            bus.remove_message_handler(on_message)
            await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                   interface="org.freedesktop.DBus", member="RemoveMatch", signature="s", body=[rule]))
    return await keyring_state(bus)
