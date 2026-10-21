"""Setup assistant steps (architecture §18.3).

Each step reports what is already in place; the UI walks them in order and every choice is an
ordinary setting (provider settings and privacy go through UpdateConfig, the shortcut is the
Shell's own GSettings key, which `Main.wm.addKeybinding` requires, so the UI owns that step).
What setup itself keeps is only its progress: whether it was offered and finished, and what the
user skipped. Applying is idempotent, so re-running setup without changes writes nothing.
"""

import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import msgspec

from mei.protocol import ProtocolError
from mei.providers.profiles import PROFILES
from mei.store import repo
from mei.store.db import Store

# Bump when a new step should be shown to everyone who finished an older setup.
SETUP_VERSION = 2  # 2: Approvals, and the cloud-files choice under Privacy (Stage 3)
STEPS = ("service", "models", "approvals", "memory", "privacy", "shortcuts")


class SetupState(msgspec.Struct, kw_only=True):
    completed_version: int = 0
    offered: bool = False
    skipped: list[str] = msgspec.field(default_factory=list)


@dataclass
class Probes:
    keyring: Callable[[], Awaitable[str]]  # "unlocked" | "locked" | "missing"
    has_key: Callable[[str], Awaitable[bool | None]]  # None when the keyring can't say (locked)
    unlock: Callable[[], Awaitable[str]]


def load_state(store: Store) -> SetupState:
    row = store.read_one("SELECT value FROM meta WHERE key = 'setup'")
    return msgspec.json.decode(row["value"], type=SetupState) if row else SetupState()


def _save_state(store: Store, state: SetupState) -> bool:
    if state == load_state(store):
        return False
    with store.tx() as tx:
        tx.execute("INSERT INTO meta (key, value) VALUES ('setup', ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (msgspec.json.encode(state).decode(),))
    return True


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass  # removed while we walked (SQLite's journal files come and go)
    return total


class Setup:
    def __init__(self, store: Store, probes: Probes, data_dir: Path, runtime_version: str) -> None:
        self.store = store
        self.probes = probes
        self.data_dir = data_dir
        self.runtime_version = runtime_version

    async def status(self) -> dict:
        state = load_state(self.store)
        _revision, config = repo.get_config(self.store)
        keyring = await self.probes.keyring()
        service = {"id": "service", "state": "done" if keyring == "unlocked" else "attention",
                   "runtime_version": self.runtime_version, "keyring": keyring, "data_dir": str(self.data_dir),
                   "data_bytes": _dir_bytes(self.data_dir), "free_bytes": shutil.disk_usage(self.data_dir).free}

        profile = PROFILES.get(config.active)
        settings = config.providers.get(config.active)
        model = settings.model if settings else ""
        requires_key = bool(profile and profile.auth != "none")
        has_key = await self.probes.has_key(config.active) if requires_key else None
        usable = bool(profile and profile.selectable and model and (not requires_key or has_key))
        models = {"id": "models", "state": "done" if usable else "todo", "provider": config.active,
                  "label": profile.label if profile else "", "model": model,
                  "requires_key": requires_key, "has_key": has_key}

        # Keeping everything until the user deletes it is the default (§14.4), so privacy is
        # always in a safe state; setup only offers the choice.
        privacy = {"id": "privacy", "state": "done",
                   "conversation_retention_days": config.privacy.conversation_retention_days,
                   "cloud_files": config.privacy.cloud_files}
        # Balanced is a safe default and the floor holds under every preset, so this is always "done" too.
        approvals = {"id": "approvals", "state": "done", "preset": config.approvals.preset}
        # Memory is on with automatic saving by default; anything inferred from what Mei read waits for review.
        memory = {"id": "memory", "state": "done", "enabled": config.memory.enabled,
                  "auto_save": config.memory.auto_save}
        return {"version": SETUP_VERSION, "completed": state.completed_version >= SETUP_VERSION,
                "offered": state.offered, "skipped": state.skipped,
                "steps": [service, models, approvals, memory, privacy]}

    async def apply(self, step: str, choices: dict) -> dict:
        state = load_state(self.store)
        if step == "service":
            if choices.get("unlock_keyring"):
                return {"changed": False, "keyring": await self.probes.unlock()}
            return {"changed": False}
        if step == "offered":
            state.offered = True
            return {"changed": _save_state(self.store, state)}
        if step == "finish":
            skipped = choices.get("skipped", [])
            if not isinstance(skipped, list) or any(s not in STEPS or s == "service" for s in skipped):
                raise ProtocolError("InvalidArgument", f"skipped steps must be among {list(STEPS[1:])}")
            state.offered, state.completed_version, state.skipped = True, SETUP_VERSION, sorted(set(skipped))
            return {"changed": _save_state(self.store, state)}
        raise ProtocolError("InvalidArgument", f"unknown setup step {step!r}")
