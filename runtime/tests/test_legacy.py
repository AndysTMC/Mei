import json

import pytest

from mei import legacy
from mei.store import repo
from mei.store.db import Store


class FakeDconf:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = dict(values)
        self.writes: list[str] = []

    async def read(self, key):
        return self.values.get(key)

    async def write(self, key, value):
        self.writes.append(key)
        self.values[key] = value

    async def reset(self, key):
        self.writes.append(f"reset:{key}")
        self.values.pop(key, None)


class FakeKeyring:
    def __init__(self, *, fail: bool = False, corrupt: bool = False) -> None:
        self.items: dict[str, str] = {}
        self.fail, self.corrupt = fail, corrupt

    async def store(self, pid, key):
        if self.fail:
            raise RuntimeError("locked")
        self.items[pid] = key[::-1] if self.corrupt else key

    async def lookup(self, pid):
        if self.fail:
            raise RuntimeError("locked")
        return self.items.get(pid)

    def port(self) -> legacy.Keyring:
        return legacy.Keyring(store=self.store, lookup=self.lookup)


CONFIGS = {
    "gemini": {"url": "", "modelName": "gemini-flash-lite-latest", "apiKey": "AIza-real-key", "apiKeyStorage": "secret",
               "mode": "", "thinking": "", "reasoningEffort": ""},
    "openrouter": {"url": "", "modelName": "or/model", "apiKey": "sk-or-1", "apiKeyStorage": "", "mode": "",
                   "thinking": "", "reasoningEffort": ""},
    "ollama": {"url": "", "modelName": "qwen3", "apiKey": "****", "apiKeyStorage": "secret", "mode": "",
               "thinking": "", "reasoningEffort": ""},
    "deepseek": {"url": "", "modelName": "deepseek-v4", "apiKey": "", "apiKeyStorage": "", "mode": "",
                 "thinking": "enabled", "reasoningEffort": "max"},
    "nonsense": {"modelName": "x"},
}


def dconf(**extra) -> FakeDconf:
    return FakeDconf({"provider-configs": json.dumps(CONFIGS), "provider": "gemini", **extra})


@pytest.mark.parametrize("value", ["plain", "it's", 'a "quote"', "back\\slash", "new\nline", "tab\t", "ünï 🌸", "{\"a\":1}"])
def test_gvariant_string_round_trip(value):
    assert legacy.parse_gvariant_string(legacy.gvariant_string(value)) == value


def test_gvariant_parses_dconf_output_forms():
    assert legacy.parse_gvariant_string('"double \\"quoted\\""') == 'double "quoted"'
    assert legacy.parse_gvariant_string("'\\u00e9t\\U0001f338'") == "ét🌸"
    with pytest.raises(ValueError):
        legacy.parse_gvariant_string("@as []")


def test_only_runs_for_the_real_data_folder(monkeypatch):
    monkeypatch.delenv("MEI_LEGACY_IMPORT", raising=False)
    assert legacy.enabled(data_dir_overridden=False)
    assert not legacy.enabled(data_dir_overridden=True)
    monkeypatch.setenv("MEI_LEGACY_IMPORT", "1")
    assert legacy.enabled(data_dir_overridden=True)


async def test_settings_import_maps_providers_and_runs_once(tmp_path):
    store = Store(tmp_path / "db")
    d = dconf()
    report = legacy.Report()
    await legacy.import_settings(store, d, report)
    rev, cfg = repo.get_config(store)
    assert cfg.active == "gemini" and report.providers == ["deepseek", "gemini", "ollama", "openrouter"]
    assert cfg.providers["gemini"].model == "gemini-flash-lite-latest"
    assert cfg.providers["deepseek"].thinking == "enabled" and cfg.providers["deepseek"].reasoning_effort == "max"
    assert "key" not in json.dumps(__import__("msgspec").to_builtins(cfg)).lower()  # no secrets in config
    again = legacy.Report()
    await legacy.import_settings(store, d, again)
    assert not again.settings_imported and repo.get_config(store)[0] == rev


async def test_settings_import_never_overrides_settings_made_in_the_runtime(tmp_path):
    store = Store(tmp_path / "db")
    from mei.protocol import Config, ProviderSettings
    with store.tx() as tx:
        repo.put_config(tx, 0, Config(active="groq", providers={"groq": ProviderSettings(model="m")}))
    report = legacy.Report()
    await legacy.import_settings(store, dconf(), report)
    assert not report.settings_imported and repo.get_config(store)[1].active == "groq"


async def test_keys_move_to_the_keyring_and_plaintext_is_scrubbed():
    d = dconf(**{"api-key": "sk-very-old"})
    kr = FakeKeyring()
    report = legacy.Report()
    await legacy.migrate_keys(d, kr.port(), report)
    assert kr.items == {"gemini": "AIza-real-key", "openrouter": "sk-or-1", "legacy": "sk-very-old"}
    remaining = json.loads(d.values["provider-configs"])
    assert all(v.get("apiKey", "") in ("", "****") for v in remaining.values())
    assert remaining["gemini"]["apiKeyStorage"] == "secret" and remaining["gemini"]["modelName"] == "gemini-flash-lite-latest"
    assert "api-key" not in d.values and "AIza-real-key" not in json.dumps(d.values) and "sk-or-1" not in json.dumps(d.values)
    assert sorted(report.keys_moved) == ["api-key", "gemini", "openrouter"]


async def test_plaintext_stays_when_the_keyring_fails_or_reads_back_wrong():
    for kr in (FakeKeyring(fail=True), FakeKeyring(corrupt=True)):
        d = dconf(**{"api-key": "sk-very-old"})
        report = legacy.Report()
        await legacy.migrate_keys(d, kr.port(), report)
        assert d.writes == [], "nothing may be deleted before a confirmed keyring write"
        assert json.loads(d.values["provider-configs"])["gemini"]["apiKey"] == "AIza-real-key"
        assert sorted(report.keys_pending) == ["api-key", "gemini", "openrouter"]


SESSIONS = [
    {"id": "abc", "title": "First chat", "createdAt": 1000, "updatedAt": 2000, "messages": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "thinking": "hm",
         "metadata": {"providerId": "gemini", "providerLabel": "Gemini", "model": "g", "durationMs": 12,
                      "tokens": {"inputTokens": 3, "outputTokens": 4}}}]},
    {"id": "def", "title": "Second", "createdAt": 3000, "updatedAt": 4000, "messages": [{"role": "user", "content": "x"}]},
    {"id": "bad", "messages": "not a list"},
]


def test_chats_import_preserves_content_and_runs_once(tmp_path):
    store = Store(tmp_path / "db")
    chats = tmp_path / "chats.json"
    chats.write_text(json.dumps(SESSIONS))
    report = legacy.Report()
    legacy.import_chats(store, chats, report)
    assert (report.conversations, report.messages) == (2, 3)
    snap = repo.conversation_snapshot(store, "legacy-abc")
    assert [(m["role"], m["content"]) for m in snap["messages"]] == [("user", "hi"), ("assistant", "hello")]
    meta = snap["messages"][1]["metadata"]
    assert meta == {"id": "gemini", "label": "Gemini", "model": "g", "duration_ms": 12, "tokens": {"input": 3, "output": 4}}
    assert snap["messages"][1]["thinking"] == "hm" and snap["conversation"]["title"] == "First chat"
    legacy.import_chats(store, chats, again := legacy.Report())
    assert again.conversations == 0
    assert chats.read_text() == json.dumps(SESSIONS)  # the source is never modified


def test_a_changed_chats_file_only_adds_new_conversations(tmp_path):
    store = Store(tmp_path / "db")
    chats = tmp_path / "chats.json"
    chats.write_text(json.dumps(SESSIONS))
    legacy.import_chats(store, chats, legacy.Report())
    changed = [dict(SESSIONS[0], title="Edited elsewhere"), SESSIONS[1],
               {"id": "ghi", "title": "New", "createdAt": 5, "updatedAt": 6, "messages": [{"role": "user", "content": "n"}]}]
    chats.write_text(json.dumps(changed))
    report = legacy.Report()
    legacy.import_chats(store, chats, report)
    assert report.conversations == 1
    assert repo.conversation_snapshot(store, "legacy-abc")["conversation"]["title"] == "First chat"


def test_malformed_timestamps_fall_back_instead_of_blocking_the_import(tmp_path):
    store = Store(tmp_path / "db")
    chats = tmp_path / "chats.json"
    chats.write_text(json.dumps([
        {"id": "bad", "createdAt": "yesterday", "updatedAt": None, "messages": [{"role": "user", "content": "x"}]},
        {"id": "neg", "createdAt": -5, "updatedAt": True, "messages": [{"role": "user", "content": "y"}]},
        {"id": "ok", "createdAt": 10, "updatedAt": 20.5, "messages": []},
    ]))
    report = legacy.Report()
    legacy.import_chats(store, chats, report)
    assert report.conversations == 3
    ok = repo.conversation_snapshot(store, "legacy-ok")["conversation"]
    assert (ok["created_at"], ok["updated_at"]) == (10, 20)
    bad = repo.conversation_snapshot(store, "legacy-bad")["conversation"]
    assert bad["created_at"] > 1_000_000_000_000 and bad["updated_at"] == bad["created_at"]


async def test_run_does_everything_and_survives_a_broken_source(tmp_path):
    store = Store(tmp_path / "db")
    (tmp_path / "chats.json").write_text("{not json")
    report = await legacy.run(store, tmp_path, dconf(), FakeKeyring().port())
    assert report.settings_imported and "gemini" in report.keys_moved
    assert report.skipped == ["chats.json is not valid JSON"]
