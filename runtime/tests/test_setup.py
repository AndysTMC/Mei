"""Setup steps: what each reports, and that re-running setup without changes writes nothing."""

import pytest

from mei.protocol import Config, Privacy, ProtocolError, ProviderSettings
from mei.setup import SETUP_VERSION, Probes, Setup
from mei.store import repo
from mei.store.db import Store


class FakeKeyring:
    def __init__(self, state="unlocked", keys=None):
        self.state = state
        self.keys = keys or {}
        self.unlocks = 0

    def probes(self) -> Probes:
        async def keyring():
            return self.state

        async def has_key(pid):
            return None if self.state == "locked" else pid in self.keys

        async def unlock():
            self.unlocks += 1
            self.state = "unlocked"
            return self.state

        return Probes(keyring=keyring, has_key=has_key, unlock=unlock)


def configure(store: Store, config: Config) -> None:
    revision, _ = repo.get_config(store)
    with store.tx() as tx:
        repo.put_config(tx, revision, config)


def steps(status: dict) -> dict:
    return {s["id"]: s for s in status["steps"]}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()


async def test_a_fresh_runtime_reports_setup_not_done(store, tmp_path):
    status = await Setup(store, FakeKeyring().probes(), tmp_path, "9.9").status()
    assert status["version"] == SETUP_VERSION and not status["completed"] and not status["offered"]
    s = steps(status)
    assert list(s) == ["service", "models", "approvals", "memory", "privacy"]
    assert s["service"]["state"] == "done" and s["service"]["runtime_version"] == "9.9"
    assert s["service"]["data_dir"] == str(tmp_path) and s["service"]["data_bytes"] > 0
    assert s["models"]["state"] == "todo" and s["models"]["provider"] == ""
    assert s["privacy"] == {"id": "privacy", "state": "done", "conversation_retention_days": None,
                            "cloud_files": "pointed"}
    assert s["approvals"] == {"id": "approvals", "state": "done", "preset": "balanced"}


async def test_a_locked_keyring_needs_attention_and_can_be_unlocked(store, tmp_path):
    keyring = FakeKeyring(state="locked")
    setup = Setup(store, keyring.probes(), tmp_path, "1")
    assert steps(await setup.status())["service"]["state"] == "attention"
    assert await setup.apply("service", {"unlock_keyring": True}) == {"changed": False, "keyring": "unlocked"}
    assert keyring.unlocks == 1 and steps(await setup.status())["service"]["state"] == "done"


async def test_models_are_done_when_the_active_provider_can_answer(store, tmp_path):
    keyring = FakeKeyring()
    setup = Setup(store, keyring.probes(), tmp_path, "1")
    configure(store, Config(active="gemini", providers={"gemini": ProviderSettings(model="gemini-x")}))
    m = steps(await setup.status())["models"]
    assert (m["state"], m["label"], m["requires_key"], m["has_key"]) == ("todo", "Gemini", True, False)

    keyring.keys["gemini"] = "k"
    assert steps(await setup.status())["models"]["state"] == "done"

    configure(store, Config(active="ollama", providers={"ollama": ProviderSettings(model="llama3")}))
    m = steps(await setup.status())["models"]
    assert m["state"] == "done" and m["requires_key"] is False and m["has_key"] is None

    configure(store, Config(active="opencode", providers={"opencode": ProviderSettings(model="x")}))
    assert steps(await setup.status())["models"]["state"] == "todo"  # retired providers can't be used


async def test_rerunning_setup_without_changes_changes_nothing(store, tmp_path):
    setup = Setup(store, FakeKeyring().probes(), tmp_path, "1")
    assert await setup.apply("offered", {}) == {"changed": True}
    assert await setup.apply("offered", {}) == {"changed": False}
    assert (await setup.status())["offered"]

    revision, _ = repo.get_config(store)
    assert await setup.apply("finish", {"skipped": ["shortcuts", "privacy", "shortcuts"]}) == {"changed": True}
    status = await setup.status()
    assert status["completed"] and status["skipped"] == ["privacy", "shortcuts"]

    # Setup again, same choices: no write to setup state, and the config revision never moved.
    assert await setup.apply("offered", {}) == {"changed": False}
    assert await setup.apply("finish", {"skipped": ["privacy", "shortcuts"]}) == {"changed": False}
    assert repo.get_config(store)[0] == revision

    assert await setup.apply("finish", {"skipped": []}) == {"changed": True}
    assert (await setup.status())["skipped"] == []


async def test_setup_rejects_unknown_steps_and_unskippable_ones(store, tmp_path):
    setup = Setup(store, FakeKeyring().probes(), tmp_path, "1")
    with pytest.raises(ProtocolError):
        await setup.apply("voice", {})
    with pytest.raises(ProtocolError):
        await setup.apply("finish", {"skipped": ["service"]})
    with pytest.raises(ProtocolError):
        await setup.apply("finish", {"skipped": "models"})


async def test_privacy_reports_the_retention_setting(store, tmp_path):
    configure(store, Config(privacy=Privacy(conversation_retention_days=30)))
    s = steps(await Setup(store, FakeKeyring().probes(), tmp_path, "1").status())
    assert s["privacy"]["conversation_retention_days"] == 30

