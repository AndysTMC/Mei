"""Memory records and history search (§17, memory v0: full-text only, no vectors yet).

Memories are canonical rows; `memories_fts`, `episodes_fts`, and `messages_fts` are derived indexes
kept in step by triggers (migration 4). Search queries are built from words only, never passed
through as FTS syntax.
"""

import re

from .db import Store, Tx, new_id, now_ms

MAX_QUERY_WORDS = 12
DAY_MS = 86_400_000
_WORD = re.compile(r"\w{3,}", re.UNICODE)
# Words too common to say anything about what a memory is about.
STOPWORDS = frozenset("""the and for that this with you your are was were have has had not but all any can
could would should will just from into onto about what when where which who whom why how than then them
they their there these those its it's also very more most some such only own same too our out off over
under again once here both each few other mei please thanks thank like want need make sure""".split())


def words(text: str) -> list[str]:
    """Content words, lower-cased, in order, without repeats."""
    return list(dict.fromkeys(w for w in (m.lower() for m in _WORD.findall(text)) if w not in STOPWORDS))


def fts_query(text: str) -> str:
    """An FTS5 query that matches any of the text's content words (as prefixes). Empty if none."""
    return " OR ".join(f'"{w}"*' for w in words(text)[:MAX_QUERY_WORDS])


def memory_view(row) -> dict:
    return {"id": row["id"], "kind": row["kind"], "text": row["text"], "provenance": row["provenance"],
            "status": row["status"], "sensitivity": row["sensitivity"], "pinned": bool(row["pinned"]),
            "source_task_id": row["source_task_id"], "source_conversation_id": row["source_conversation_id"],
            "use_count": row["use_count"], "created_at": row["created_at"], "updated_at": row["updated_at"],
            "last_used_at": row["last_used_at"]}


def _one(src, sql: str, params: tuple = ()):
    return src.one(sql, params) if isinstance(src, Tx) else src.read_one(sql, params)


def _all(src, sql: str, params: tuple = ()) -> list:
    return src.execute(sql, params).fetchall() if isinstance(src, Tx) else src.read(sql, params)


def get_memory(src, memory_id: str):
    return _one(src, "SELECT * FROM memories WHERE id = ?", (memory_id,))


def add_memory(tx: Tx, text: str, *, provenance: str, status: str, task_id: str | None,
               conversation_id: str | None) -> dict:
    ts = now_ms()
    memory_id = new_id()
    tx.execute("INSERT INTO memories (id, kind, text, provenance, status, source_task_id, source_conversation_id, "
               "created_at, updated_at) VALUES (?, 'profile', ?, ?, ?, ?, ?, ?, ?)",
               (memory_id, text, provenance, status, task_id, conversation_id, ts, ts))
    view = memory_view(get_memory(tx, memory_id))
    kind = "memory.saved" if status == "active" else "memory.pending_review"
    tx.event(kind, {"memory": view}, conversation_id=conversation_id, task_id=task_id)
    return view


def update_memory(tx: Tx, memory_id: str, **fields) -> dict:
    allowed = {"text", "status", "pinned", "sensitivity", "provenance", "use_count", "last_used_at", "superseded_by"}
    if not fields or set(fields) - allowed:
        raise ValueError(f"can't change {sorted(set(fields) - allowed)}")
    fields["updated_at"] = now_ms()
    tx.execute(f"UPDATE memories SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
               (*fields.values(), memory_id))
    view = memory_view(get_memory(tx, memory_id))
    tx.event("memory.updated", {"memory": view}, conversation_id=view["source_conversation_id"])
    return view


def delete_memory(tx: Tx, memory_id: str) -> bool:
    row = get_memory(tx, memory_id)
    if row is None:
        return False
    tx.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    tx.event("memory.deleted", {"memory_id": memory_id}, conversation_id=row["source_conversation_id"])
    return True


def find_same(src, text: str):
    """An active or pending memory that says the same thing (same content words), if any."""
    wanted = set(words(text))
    if not wanted:
        return None
    for row in search(src, text, statuses=("active", "pending_review"), limit=5):
        mine = set(words(row["text"]))
        if mine and len(wanted & mine) / len(wanted | mine) >= 0.8:
            return row
    return None


def search(src, text: str, *, statuses: tuple[str, ...] = ("active",), limit: int = 10) -> list:
    query = fts_query(text)
    if not query:
        return []
    marks = ",".join("?" for _ in statuses)
    return _all(src, f"SELECT m.* FROM memories_fts f JOIN memories m ON m.rowid = f.rowid "
                     f"WHERE memories_fts MATCH ? AND m.status IN ({marks}) ORDER BY bm25(memories_fts) LIMIT ?",
                (query, *statuses, limit))


def listed(src, *, status: str | None = None, text: str = "", limit: int = 200) -> list:
    if text:
        return search(src, text, statuses=(status,) if status else ("active", "pending_review", "archived"),
                      limit=limit)
    if status:
        return _all(src, "SELECT * FROM memories WHERE status = ? ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                    (status, limit))
    return _all(src, "SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC LIMIT ?", (limit,))


def recall(store: Store, text: str, *, limit: int = 8, now: int | None = None) -> list:
    """Active memories for a request: every pinned one, then the best matches, nudged up by recent
    and frequent use (§17.5)."""
    now = now if now is not None else now_ms()
    pinned = store.read("SELECT * FROM memories WHERE status = 'active' AND pinned = 1 ORDER BY updated_at DESC")
    matched = search(store, text, limit=limit * 3)

    def score(rank: int, row) -> float:
        age_days = (now - (row["last_used_at"] or row["updated_at"])) / DAY_MS
        return 1.0 / (rank + 1) + 0.1 * min(row["use_count"], 10) / 10 + 0.1 / (1 + age_days / 30)

    ranked = [row for _rank, row in sorted(((r, row) for r, row in enumerate(matched)),
                                           key=lambda item: score(*item), reverse=True)]
    chosen = list({row["id"]: row for row in [*pinned, *ranked]}.values())
    return chosen[:max(limit, len(pinned))]


def mark_used(tx: Tx, memory_ids: list[str]) -> None:
    for memory_id in memory_ids:
        tx.execute("UPDATE memories SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
                   (now_ms(), memory_id))


# ── Episodes and history ────────────────────────────────────────────────────


def add_episode(tx: Tx, task_id: str, conversation_id: str, summary: str) -> None:
    tx.execute("INSERT INTO episodes (task_id, conversation_id, summary, created_at) VALUES (?, ?, ?, ?) "
               "ON CONFLICT(task_id) DO UPDATE SET summary = excluded.summary", (task_id, conversation_id, summary,
                                                                                  now_ms()))


def write_episode(tx: Tx, task: dict) -> None:
    """Every task that ends with an answer or a result leaves a one-line summary (§17.4)."""
    request = tx.one("SELECT content FROM messages WHERE id = ?", (task["input_message_id"],))
    if request is None:
        return
    reply = tx.one("SELECT content FROM messages WHERE task_id = ? AND role = 'assistant' AND content != '' "
                   "ORDER BY ordinal DESC LIMIT 1", (task["id"],))
    asked = " ".join(request["content"].split())[:160]
    answered = " ".join(reply["content"].split())[:240] if reply else task["state"].lower()
    add_episode(tx, task["id"], task["conversation_id"], f"{asked} → {answered}")


def episodes(store: Store, text: str, *, limit: int = 3, exclude_conversation: str = "") -> list:
    query = fts_query(text)
    if not query:
        return []
    return store.read("SELECT e.* FROM episodes_fts f JOIN episodes e ON e.rowid = f.rowid "
                      "WHERE episodes_fts MATCH ? AND e.conversation_id != ? ORDER BY bm25(episodes_fts) LIMIT ?",
                      (query, exclude_conversation, limit))


def search_history(store: Store, text: str, *, limit: int = 10) -> list:
    """Messages people saw (requests and replies, never tool output), best matches first."""
    query = fts_query(text)
    if not query:
        return []
    return store.read("SELECT m.content, m.role, m.created_at, c.title, c.id AS conversation_id "
                      "FROM messages_fts f JOIN messages m ON m.rowid = f.rowid "
                      "JOIN conversations c ON c.id = m.conversation_id "
                      "WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts) LIMIT ?", (query, limit))


_INDEXES = (  # (index, its column, source table, which rows of it are indexed)
    ("memories_fts", "text", "memories", "1"),
    ("episodes_fts", "summary", "episodes", "1"),
    ("messages_fts", "content", "messages", "role IN ('user', 'assistant')"),
)


def reindex(store: Store) -> bool:
    """Rebuild the full-text indexes if their row counts disagree with the tables. True if rebuilt."""
    rebuilt = False
    for index, column, table, where in _INDEXES:
        indexed = store.read_one(f"SELECT count(*) AS n FROM {index}")["n"]
        if indexed == store.read_one(f"SELECT count(*) AS n FROM {table} WHERE {where}")["n"]:
            continue
        with store.tx() as tx:
            tx.execute(f"DELETE FROM {index}")
            tx.execute(f"INSERT INTO {index} (rowid, {column}) SELECT rowid, {column} FROM {table} WHERE {where}")
        rebuilt = True
    return rebuilt
