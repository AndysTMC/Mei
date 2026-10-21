import os
import sqlite3
import stat

import pytest

from mei.protocol import Config, ProtocolError, ProviderSettings
from mei.store import repo
from mei.store.db import Store, WriterLockHeld
from mei.store.migrations import MIGRATIONS


def test_single_writer_lock(tmp_path):
    first = Store(tmp_path)
    with pytest.raises(WriterLockHeld):
        Store(tmp_path)
    first.close()
    Store(tmp_path).close()  # released when the holder goes away


def test_private_permissions(tmp_path):
    store = Store(tmp_path / "data")
    assert stat.S_IMODE(os.stat(tmp_path / "data").st_mode) == 0o700
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    store.close()


def test_migrations_apply_once_and_reopen(tmp_path):
    Store(tmp_path).close()
    store = Store(tmp_path)
    assert store.read_one("SELECT value FROM meta WHERE key = 'schema_version'")["value"] == str(len(MIGRATIONS))
    store.close()


def test_a_stale_backup_from_a_failed_migration_does_not_block_startup(tmp_path, monkeypatch):
    from mei.store import db as db_mod
    data = tmp_path / "it's here"  # a quote in the path must not break the backup statement
    last = len(MIGRATIONS)
    monkeypatch.setattr(db_mod, "MIGRATIONS", MIGRATIONS[:-1])  # as if the last migration had failed
    Store(data).close()
    monkeypatch.undo()
    stale = data / f"mei.db.pre-migration-{last}"
    stale.write_bytes(b"left over from an attempt that crashed")
    store = Store(data)
    assert store.read_one("SELECT value FROM meta WHERE key = 'schema_version'")["value"] == str(last)
    store.close()
    backup = sqlite3.connect(stale)
    assert backup.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0] == str(last - 1)
    backup.close()


def test_the_agent_migration_keeps_existing_chats(tmp_path, monkeypatch):
    from mei.store import db as db_mod
    monkeypatch.setattr(db_mod, "MIGRATIONS", MIGRATIONS[:2])
    old = Store(tmp_path)
    with old.tx() as tx:  # written the way the schema-2 runtime wrote them
        conv = repo.create_conversation(tx, "hi")
        for n, (role, content, thinking, meta) in enumerate([("user", "hello", None, "{}"),
                                                            ("assistant", "hi there", "t", '{"model": "m"}')], 1):
            tx.execute("INSERT INTO messages (id, conversation_id, task_id, ordinal, role, content, thinking, metadata, "
                       "created_at) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, 0)", (f"m{n}", conv["id"], n, role, content,
                                                                            thinking, meta))
    old.close()
    monkeypatch.undo()
    store = Store(tmp_path)
    messages = repo.history(store, conv["id"])
    assert [(m["role"], m["content"], m["thinking"]) for m in messages] == [("user", "hello", None),
                                                                           ("assistant", "hi there", "t")]
    assert messages[1]["metadata"] == {"model": "m"}
    with store.tx() as tx:
        repo.add_message(tx, conv["id"], "tool", "result", action_id="a1")  # the new role is accepted
    store.close()


def test_new_epoch_each_open(tmp_path):
    a = Store(tmp_path)
    epoch_a = a.epoch
    a.close()
    b = Store(tmp_path)
    assert b.epoch != epoch_a
    b.close()


def test_events_get_one_global_increasing_seq(tmp_path):
    store = Store(tmp_path)
    with store.tx() as tx:
        c1 = repo.create_conversation(tx, "first")
        c2 = repo.create_conversation(tx, "second")
        repo.add_message(tx, c1["id"], "user", "hi")
        repo.add_message(tx, c2["id"], "user", "hello")
    seqs = [e.seq for e in tx.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) == 4
    assert [e.seq for e in repo.events_after(store, seqs[0], c1["id"])] == [seqs[2]]
    assert store.last_seq() == seqs[-1]
    store.close()


def test_rollback_publishes_and_keeps_nothing(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(RuntimeError):
        with store.tx() as tx:
            repo.create_conversation(tx, "doomed")
            raise RuntimeError("boom")
    assert tx.events == []
    assert store.last_seq() == 0
    assert repo.list_conversations(store) == []
    store.close()


def test_config_compare_and_set(tmp_path):
    store = Store(tmp_path)
    cfg = Config(active="fake", providers={"fake": ProviderSettings()})
    with store.tx() as tx:
        assert repo.put_config(tx, 0, cfg) == 1
    with pytest.raises(ProtocolError) as err, store.tx() as tx:
        repo.put_config(tx, 0, cfg)
    assert err.value.name == "Conflict"
    assert repo.get_config(store) == (1, cfg)
    store.close()


def test_titles_are_short_and_single_line():
    assert repo.make_title("  hello\n  world ") == "hello world"
    long = repo.make_title("x" * 200)
    assert len(long) == repo.TITLE_CHARS and long.endswith("…")
