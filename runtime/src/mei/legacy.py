"""One-time import of what the extension used to keep (§14.3), and the ADR-10 key migration.

Sources are read, never renamed. Each import records the source's sha256, so it runs once per
version of the source. Plaintext API keys are removed from dconf only after the same key has
been written to the keyring *and read back*.

Safety: this only runs against the user's real data folder. A runtime started with MEI_DATA_DIR
(tests, development) skips it unless MEI_LEGACY_IMPORT=1 is set on a fully private session.
"""

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mei.protocol import Config, ProviderSettings
from mei.providers.profiles import resolve_id
from mei.store import repo
from mei.store.db import Store, now_ms

log = logging.getLogger("mei.legacy")
DCONF_DIR = "/org/gnome/shell/extensions/mei/"
LEGACY_KEY_ID = "legacy"  # keyring slot for the old single `api-key` value, whose provider is unknown


def enabled(data_dir_overridden: bool) -> bool:
    return not data_dir_overridden or os.environ.get("MEI_LEGACY_IMPORT") == "1"


# ── GVariant text for strings (what `dconf read`/`dconf write` speak) ───────

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "a": "\a", "\\": "\\", "'": "'", '"': '"'}


def parse_gvariant_string(text: str) -> str:
    t = text.strip()
    if len(t) < 2 or t[0] not in "'\"" or t[-1] != t[0]:
        raise ValueError("not a GVariant string literal")
    body, out, i = t[1:-1], [], 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = body[i + 1] if i + 1 < len(body) else ""
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 2
        elif nxt in "uU":
            width = 4 if nxt == "u" else 8
            out.append(chr(int(body[i + 2:i + 2 + width], 16)))
            i += 2 + width
        else:
            out.append(nxt)
            i += 2
    return "".join(out)


def gvariant_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\t", "\\t")
    return f"'{escaped}'"


# ── Ports (real implementations below; tests pass fakes) ─────────────────────


class Dconf(Protocol):
    async def read(self, key: str) -> str | None: ...
    async def write(self, key: str, value: str) -> None: ...
    async def reset(self, key: str) -> None: ...


class DconfCli:
    """Uses /usr/bin/dconf by absolute path: the dconf on PATH may be someone else's (Stage 0a)."""

    async def _run(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec("/usr/bin/dconf", *args, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(f"dconf {args[0]} failed: {err.decode().strip()}")
        return out.decode()

    async def read(self, key: str) -> str | None:
        raw = (await self._run("read", DCONF_DIR + key)).strip()
        return parse_gvariant_string(raw) if raw else None

    async def write(self, key: str, value: str) -> None:
        await self._run("write", DCONF_DIR + key, gvariant_string(value))

    async def reset(self, key: str) -> None:
        await self._run("reset", DCONF_DIR + key)


@dataclass
class Keyring:
    store: Callable[[str, str], Awaitable[None]]
    lookup: Callable[[str], Awaitable[str | None]]


@dataclass
class Report:
    settings_imported: bool = False
    providers: list[str] = field(default_factory=list)
    keys_moved: list[str] = field(default_factory=list)
    keys_pending: list[str] = field(default_factory=list)
    conversations: int = 0
    messages: int = 0
    skipped: list[str] = field(default_factory=list)


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def _already(store: Store, source: str, digest: str) -> bool:
    return store.read_one("SELECT 1 FROM imports WHERE source = ? AND sha256 = ?", (source, digest)) is not None


def _record(tx, source: str, digest: str, counts: dict) -> None:
    tx.execute("INSERT INTO imports (source, sha256, imported_at, counts) VALUES (?, ?, ?, ?)",
               (source, digest, now_ms(), json.dumps(counts)))


def _is_placeholder(key: str) -> bool:
    return bool(key) and set(key) == {"*"} and len(key) <= 8


# ── Settings ────────────────────────────────────────────────────────────────


async def import_settings(store: Store, dconf: Dconf, report: Report) -> list[Callable]:
    raw_configs = await dconf.read("provider-configs")
    raw_active = await dconf.read("provider")
    source = json.dumps({"provider-configs": raw_configs, "provider": raw_active})
    digest = _sha(source)
    if raw_configs is None and raw_active is None:
        return []
    revision, config = repo.get_config(store)
    if _already(store, "dconf-settings", digest) or revision > 0 and config.active:
        return []  # same source already imported, or the user configured the runtime since
    try:
        stored = json.loads(raw_configs or "{}")
    except ValueError:
        report.skipped.append("provider-configs is not valid JSON")
        stored = {}
    providers: dict[str, ProviderSettings] = {}
    for pid, item in (stored.items() if isinstance(stored, dict) else []):
        rid = resolve_id(pid)
        if rid is None or not isinstance(item, dict):
            continue
        providers[rid] = ProviderSettings(model=str(item.get("modelName") or ""), url=str(item.get("url") or ""),
                                          mode=str(item.get("mode") or ""), thinking=str(item.get("thinking") or ""),
                                          reasoning_effort=str(item.get("reasoningEffort") or ""))
    active = resolve_id(raw_active or "") or ""
    new = Config(active=active, providers=providers, privacy=config.privacy)
    with store.tx() as tx:
        repo.put_config(tx, revision, new)
        _record(tx, "dconf-settings", digest, {"providers": len(providers)})
    report.settings_imported = True
    report.providers = sorted(providers)
    return tx.events  # type: ignore[return-value]


# ── Keys (ADR-10) ───────────────────────────────────────────────────────────


async def migrate_keys(dconf: Dconf, keyring: Keyring, report: Report) -> None:
    raw = await dconf.read("provider-configs")
    try:
        stored = json.loads(raw) if raw else {}
    except ValueError:
        stored = {}
    changed = False
    for pid, item in (stored.items() if isinstance(stored, dict) else []):
        key = str(item.get("apiKey") or "") if isinstance(item, dict) else ""
        if not key or _is_placeholder(key):
            continue
        if await _move(keyring, pid, key):
            item["apiKey"] = ""
            item["apiKeyStorage"] = "secret"
            changed = True
            report.keys_moved.append(pid)
        else:
            report.keys_pending.append(pid)
    if changed:
        await dconf.write("provider-configs", json.dumps(stored, separators=(",", ":")))
    legacy = await dconf.read("api-key")
    if legacy and not _is_placeholder(legacy):
        if await _move(keyring, LEGACY_KEY_ID, legacy):
            await dconf.reset("api-key")
            report.keys_moved.append("api-key")
        else:
            report.keys_pending.append("api-key")


async def _move(keyring: Keyring, slot: str, key: str) -> bool:
    try:
        existing = await keyring.lookup(slot)
        if existing != key:
            await keyring.store(slot, key)
        return await keyring.lookup(slot) == key  # read back before anything is deleted
    except Exception as e:  # locked or unavailable: leave the plaintext copy and try again next start
        log.warning("could not move the %s key into the keyring yet: %s", slot, type(e).__name__)
        return False


# ── Chats ───────────────────────────────────────────────────────────────────


def import_chats(store: Store, path: Path, report: Report) -> None:
    if not path.is_file():
        return
    data = path.read_bytes()
    digest = _sha(data)
    if _already(store, "chats.json", digest):
        return
    try:
        sessions = json.loads(data)
    except ValueError:
        report.skipped.append("chats.json is not valid JSON")
        return
    added_convs = added_msgs = 0
    with store.tx() as tx:
        for s in sessions if isinstance(sessions, list) else []:
            if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not isinstance(s.get("messages"), list):
                continue
            conv_id = f"legacy-{s['id']}"
            if tx.one("SELECT 1 FROM conversations WHERE id = ?", (conv_id,)):
                continue  # never touch a conversation we already have
            created = int(s.get("createdAt") or now_ms())
            updated = int(s.get("updatedAt") or created)
            title = repo.make_title(str(s.get("title") or "Imported chat")) or "Imported chat"
            tx.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                       (conv_id, title, created, updated))
            ordinal = 0
            for m in s["messages"]:
                if not isinstance(m, dict) or m.get("role") not in ("user", "assistant", "system") \
                        or not isinstance(m.get("content"), str):
                    continue
                ordinal += 1
                tx.execute("INSERT INTO messages (id, conversation_id, task_id, ordinal, role, content, thinking, "
                           "metadata, created_at) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
                           (f"{conv_id}-{ordinal}", conv_id, ordinal, m["role"], m["content"],
                            m.get("thinking") if isinstance(m.get("thinking"), str) else None,
                            json.dumps(_metadata(m.get("metadata"))), created + ordinal))
                added_msgs += 1
            tx.event("conversation.created", {"conversation": {"id": conv_id, "title": title, "created_at": created,
                                                                "updated_at": updated}, "imported": True},
                     conversation_id=conv_id)
            added_convs += 1
        _record(tx, "chats.json", digest, {"conversations": added_convs, "messages": added_msgs})
    report.conversations += added_convs
    report.messages += added_msgs


def _metadata(meta) -> dict:
    if not isinstance(meta, dict):
        return {}
    tokens = meta.get("tokens") if isinstance(meta.get("tokens"), dict) else {}
    out = {"id": meta.get("providerId"), "label": meta.get("providerLabel"), "model": meta.get("model"),
           "duration_ms": meta.get("durationMs")}
    if tokens:
        out["tokens"] = {"input": tokens.get("inputTokens"), "output": tokens.get("outputTokens")}
    return {k: v for k, v in out.items() if v is not None}


async def run(store: Store, data_dir: Path, dconf: Dconf, keyring: Keyring) -> tuple[Report, list]:
    """Everything, in order: settings, then keys (needs the settings source), then chats."""
    report = Report()
    events: list = []
    try:
        events += await import_settings(store, dconf, report)
        await migrate_keys(dconf, keyring, report)
    except Exception:
        log.exception("importing settings from dconf failed; will retry next start")
    try:
        import_chats(store, data_dir / "chats.json", report)
    except Exception:
        log.exception("importing chats.json failed; will retry next start")
    return report, events
