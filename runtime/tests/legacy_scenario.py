"""Runs inside a private session (see test_legacy_process.py): real dconf on a private database, a
throwaway gnome-keyring, and the runtime started by D-Bus activation. Prints one JSON result."""

import asyncio
import json
import os
import subprocess
import sys

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

from mei.legacy import gvariant_string
from mei.secrets import lookup_provider_key

NAME, PATH, IFACE = "com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime"
DIR = "/org/gnome/shell/extensions/mei/"
CONFIGS = {"gemini": {"url": "", "modelName": "gemini-x", "apiKey": "AIza-test-secret", "apiKeyStorage": "secret",
                      "mode": "", "thinking": "", "reasoningEffort": ""},
           "openrouter": {"url": "", "modelName": "or/m", "apiKey": "sk-or-test-secret", "apiKeyStorage": "",
                          "mode": "", "thinking": "", "reasoningEffort": ""}}


def dconf(*args: str) -> str:
    return subprocess.run(["/usr/bin/dconf", *args], capture_output=True, text=True, check=True).stdout.strip()


async def call(bus, member, args=None):
    reply = await bus.call(Message(destination=NAME, path=PATH, interface=IFACE, member=member, signature="s",
                                   body=[json.dumps(args or {})]))
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"{reply.error_name}: {reply.body}")
    return json.loads(reply.body[0])


async def main() -> None:
    data_dir = os.environ["MEI_DATA_DIR"]
    dconf("write", DIR + "provider-configs", gvariant_string(json.dumps(CONFIGS)))
    dconf("write", DIR + "provider", "'gemini'")
    dconf("write", DIR + "api-key", "'sk-ancient-secret'")
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, "chats.json"), "w") as f:
        json.dump([{"id": "c1", "title": "Old chat", "createdAt": 1, "updatedAt": 2,
                    "messages": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]}], f)

    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    hello = await call(bus, "Hello", {"client": {"kind": "test"}, "protocol": [2, 0]})
    cfg = (await call(bus, "GetConfig"))["config"]
    conv = await call(bus, "GetConversation", {"conversation_id": "legacy-c1"})
    after = dconf("read", DIR + "provider-configs")
    keys = {pid: await lookup_provider_key(bus, pid) for pid in ("gemini", "openrouter", "legacy")}
    os.kill(hello["pid"], 15)  # restart: a second run must change nothing
    await asyncio.sleep(0.5)
    await call(bus, "Hello", {"client": {"kind": "test"}, "protocol": [2, 0]})
    cfg2 = await call(bus, "GetConfig")
    conversations = await call(bus, "Attach", {"scope": "all", "after_seq": 0})
    print(json.dumps({
        "active": cfg["active"], "providers": sorted(cfg["providers"]), "model": cfg["providers"]["gemini"]["model"],
        "keys_in_keyring": {k: v for k, v in keys.items()},
        "plaintext_left_in_dconf": any(s in after for s in ("AIza-test-secret", "sk-or-test-secret")),
        "legacy_api_key_left": dconf("read", DIR + "api-key") != "",
        "non_secret_fields_kept": "gemini-x" in after,
        "imported_messages": [m["content"] for m in conv["messages"]],
        "second_run_revision_same": cfg2["revision"] == (await call(bus, "GetConfig"))["revision"],
        "conversation_count_after_restart": len(conversations["snapshot"]["conversations"]),
    }))


asyncio.run(main())
sys.exit(0)
