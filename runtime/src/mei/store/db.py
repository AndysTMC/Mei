"""SQLite store: single writer, WAL, durable transactions that carry their events (§14).

A transaction collects the events it appends; they get their global `seq` inside the same
commit, and callers publish them only after the commit succeeded. Nothing is published for a
transaction that rolled back.
"""

import datetime
import fcntl
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

import msgspec

from mei.protocol import DURABLE_EVENTS, Envelope

from .migrations import MIGRATIONS


class WriterLockHeld(RuntimeError):
    """Another runtime instance owns this data directory."""


def now_ms() -> int:
    return int(datetime.datetime.now(datetime.UTC).timestamp() * 1000)


def iso_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())


class Tx:
    def __init__(self, store: "Store") -> None:
        self._store = store
        self.conn = store.conn
        self.events: list[Envelope] = []

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def event(self, type_: str, payload: dict, *, conversation_id: str | None = None,
              task_id: str | None = None, required: bool = True) -> Envelope:
        if type_ not in DURABLE_EVENTS:
            raise ValueError(f"{type_} is not a durable event")
        env = Envelope(type=type_, event_id=new_id(), epoch=self._store.epoch, at=iso_now(),
                       required=required, conversation_id=conversation_id, task_id=task_id,
                       payload=payload)
        cur = self.conn.execute(
            "INSERT INTO events (event_id, conversation_id, task_id, type, required, at, epoch, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (env.event_id, conversation_id, task_id, type_, int(required), env.at, env.epoch,
             msgspec.json.encode(payload).decode()))
        env.seq = cur.lastrowid
        self.events.append(env)
        return env


class Store:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(data_dir, 0o700)
        self.path = data_dir / "mei.db"
        self._lock_fd = os.open(data_dir / "mei.db.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._lock_fd)
            raise WriterLockHeld(f"another Mei runtime is using {data_dir}") from None
        fresh = not self.path.exists()
        self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        if fresh:
            os.chmod(self.path, 0o600)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()
        self.epoch = new_id()
        with self.tx() as tx:
            tx.execute("INSERT INTO meta (key, value) VALUES ('epoch', ?) "
                       "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (self.epoch,))

    def _migrate(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        version = int(row["value"]) if row else 0
        if version > len(MIGRATIONS):
            raise RuntimeError(f"database schema {version} is newer than this runtime ({len(MIGRATIONS)})")
        for number, sql in enumerate(MIGRATIONS[version:], start=version + 1):
            if version > 0:
                # A backup left by an earlier attempt that failed before committing describes the
                # same pre-migration state; VACUUM INTO refuses to overwrite it, so replace it.
                backup = self.path.with_name(f"{self.path.name}.pre-migration-{number}")
                backup.unlink(missing_ok=True)
                self.conn.execute("VACUUM INTO ?", (str(backup),))
            with self.tx() as tx:
                # executescript() would commit on its own; run statements inside our transaction.
                for statement in _split_sql(sql):
                    tx.execute(statement)
                tx.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(number),))

    @contextmanager
    def tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        tx = Tx(self)
        try:
            yield tx
        except BaseException:
            self.conn.execute("ROLLBACK")
            tx.events.clear()
            raise
        self.conn.execute("COMMIT")

    def read(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def read_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def last_seq(self) -> int:
        row = self.conn.execute("SELECT MAX(seq) AS s FROM events").fetchone()
        return int(row["s"] or 0)

    def close(self) -> None:
        self.conn.close()
        os.close(self._lock_fd)


def _split_sql(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]
