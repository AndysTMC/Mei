"""Stage 0a spike: Secret Service over dbus-fast with a plain session.

Must run against a throwaway gnome-keyring (see run_secret.sh); never against the real keyring.
"""

import asyncio
import json

from dbus_fast import BusType, Message, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.errors import DBusError

SS = "org.freedesktop.secrets"
SVC_PATH = "/org/freedesktop/secrets"
SVC = "org.freedesktop.Secret.Service"
ATTRS = {"xdg:schema": "com.andystmc.mei.provider-api-key", "extension": "mei@andystmc.com", "provider": "spike"}
VALUE = b"sk-spike-not-a-real-key"
results: dict = {}


async def main() -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()

    async def call(path, iface, member, sig="", body=()):
        reply = await bus.call(Message(destination=SS, path=path, interface=iface, member=member,
                                       signature=sig, body=list(body)))
        if reply.message_type.name == "ERROR":
            raise DBusError(reply.error_name, str(reply.body))
        return reply.body

    _out, session = await call(SVC_PATH, SVC, "OpenSession", "sv", ["plain", Variant("s", "")])
    results["open_session_plain"] = "ok"
    (default,) = await call(SVC_PATH, SVC, "ReadAlias", "s", ["default"])
    results["default_collection"] = default

    props = {"org.freedesktop.Secret.Item.Label": Variant("s", "Mei spike key"),
             "org.freedesktop.Secret.Item.Attributes": Variant("a{ss}", ATTRS)}
    item, prompt = await call(default, "org.freedesktop.Secret.Collection", "CreateItem", "a{sv}(oayays)b",
                              [props, [session, b"", VALUE, "text/plain"], True])
    results["create_item_prompt"] = prompt

    unlocked, locked = await call(SVC_PATH, SVC, "SearchItems", "a{ss}", [ATTRS])
    (secrets,) = await call(SVC_PATH, SVC, "GetSecrets", "aoo", [unlocked, session])
    results["read_back_matches"] = secrets[item][2] == VALUE

    await call(SVC_PATH, SVC, "Lock", "ao", [[default]])
    unlocked, locked = await call(SVC_PATH, SVC, "SearchItems", "a{ss}", [ATTRS])
    results["after_lock"] = {"unlocked": len(unlocked), "locked": len(locked)}
    try:
        (secrets,) = await call(SVC_PATH, SVC, "GetSecrets", "aoo", [locked, session])
        results["get_secret_while_locked"] = f"returned {len(secrets)} secrets"
    except DBusError as e:
        results["get_secret_while_locked"] = f"error {e.type}"
    done, prompt = await call(SVC_PATH, SVC, "Unlock", "ao", [[default]])
    results["unlock_returns"] = {"unlocked_now": done, "prompt": prompt}
    if prompt != "/":
        # Real runtime: call Prompt.Prompt(window_id) and await the Completed signal; that
        # shows GNOME's unlock dialog. The spike dismisses it so no dialog appears.
        await call(prompt, "org.freedesktop.Secret.Prompt", "Dismiss")
        results["prompt_dismissed"] = True

    try:
        await call(item, "org.freedesktop.Secret.Item", "Delete")
        results["delete_while_locked"] = "allowed"
    except DBusError as e:
        results["delete_while_locked"] = f"refused: {e.text}"  # the throwaway keyring is discarded anyway
    print(json.dumps(results, indent=1))


asyncio.run(main())
