"""Domain operations on the store. Each mutation runs inside a caller's `Tx` and appends its event."""

import hashlib
import json

import msgspec

from mei.core.states import TERMINAL, TaskState, check_transition
from mei.protocol import Config, Envelope, ProtocolError

from . import agent, memory
from .db import Store, Tx, new_id, now_ms

TITLE_CHARS = 60


def make_title(text: str) -> str:
    title = " ".join(text.split())
    return title if len(title) <= TITLE_CHARS else title[: TITLE_CHARS - 1].rstrip() + "…"


def conversation_dict(row) -> dict:
    return {"id": row["id"], "title": row["title"], "created_at": row["created_at"],
            "updated_at": row["updated_at"]}


def message_dict(row) -> dict:
    return {"id": row["id"], "conversation_id": row["conversation_id"], "task_id": row["task_id"],
            "role": row["role"], "content": row["content"], "thinking": row["thinking"],
            "metadata": json.loads(row["metadata"]), "created_at": row["created_at"]}


def task_dict(row) -> dict:
    return {"id": row["id"], "conversation_id": row["conversation_id"], "state": row["state"],
            "input_message_id": row["input_message_id"], "error": row["error"],
            "created_at": row["created_at"], "updated_at": row["updated_at"], "mode": row["mode"],
            "plan": json.loads(row["plan"]), "outcome": json.loads(row["outcome"]) if row["outcome"] else None}


def shown(message: dict) -> bool:
    """Messages people see: not tool results, not the runtime's notes to the model."""
    return message["role"] in ("user", "assistant")


# ── Conversations and messages ──────────────────────────────────────────────


def get_conversation(tx_or_store, conversation_id: str):
    return tx_or_store.one("SELECT * FROM conversations WHERE id = ?", (conversation_id,)) \
        if isinstance(tx_or_store, Tx) else \
        tx_or_store.read_one("SELECT * FROM conversations WHERE id = ?", (conversation_id,))


def create_conversation(tx: Tx, title: str) -> dict:
    ts = now_ms()
    conv = {"id": new_id(), "title": make_title(title) or "New chat", "created_at": ts, "updated_at": ts}
    tx.execute("INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
               (conv["id"], conv["title"], ts, ts))
    tx.event("conversation.created", {"conversation": conv}, conversation_id=conv["id"])
    return conv


def add_message(tx: Tx, conversation_id: str, role: str, content: str, *, task_id: str | None = None,
                thinking: str | None = None, metadata: dict | None = None,
                message_id: str | None = None, tool_calls: list[dict] | None = None,
                replay: dict | None = None, action_id: str | None = None) -> dict:
    """Append a message. Only messages people see are announced; tool results and runtime notes
    are the model's transcript, and the UI learns about actions from their own events."""
    ts = now_ms()
    ordinal = tx.one("SELECT COALESCE(MAX(ordinal), 0) + 1 AS n FROM messages WHERE conversation_id = ?",
                     (conversation_id,))["n"]
    msg_id = message_id or new_id()
    tx.execute("INSERT INTO messages (id, conversation_id, task_id, ordinal, role, content, thinking, "
               "metadata, tool_calls, replay, action_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (msg_id, conversation_id, task_id, ordinal, role, content, thinking, json.dumps(metadata or {}),
                json.dumps(tool_calls) if tool_calls else None, json.dumps(replay) if replay else None,
                action_id, ts))
    message = message_dict(tx.one("SELECT * FROM messages WHERE id = ?", (msg_id,)))
    if shown(message):
        tx.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, conversation_id))
        tx.event("message.completed", {"message": message}, conversation_id=conversation_id, task_id=task_id)
    return message


def history(store: Store, conversation_id: str, *, up_to_ordinal: int | None = None) -> list[dict]:
    sql = "SELECT * FROM messages WHERE conversation_id = ?"
    params: tuple = (conversation_id,)
    if up_to_ordinal is not None:
        sql += " AND ordinal <= ?"
        params += (up_to_ordinal,)
    return [message_dict(r) for r in store.read(sql + " ORDER BY ordinal", params)]


def message_ordinal(store: Store, message_id: str) -> int:
    return store.read_one("SELECT ordinal FROM messages WHERE id = ?", (message_id,))["ordinal"]


def delete_conversation(tx: Tx, conversation_id: str) -> None:
    if not tx.one("SELECT id FROM conversations WHERE id = ?", (conversation_id,)):
        raise ProtocolError("NotFound", "no such conversation")
    tx.execute("DELETE FROM events WHERE conversation_id = ?", (conversation_id,))
    tx.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    tx.event("conversation.deleted", {"conversation_id": conversation_id}, conversation_id=conversation_id)


# ── Tasks and turns ─────────────────────────────────────────────────────────


def create_task(tx: Tx, conversation_id: str, input_message_id: str, provider: dict) -> dict:
    ts = now_ms()
    task_id = new_id()
    tx.execute("INSERT INTO tasks (id, conversation_id, input_message_id, state, provider, created_at, "
               "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (task_id, conversation_id, input_message_id, TaskState.ACCEPTED, json.dumps(provider), ts, ts))
    task = task_dict(tx.one("SELECT * FROM tasks WHERE id = ?", (task_id,)))
    tx.event("task.accepted", {"task": task}, conversation_id=conversation_id, task_id=task_id)
    return task


def get_task(tx_or_store, task_id: str):
    sql, params = "SELECT * FROM tasks WHERE id = ?", (task_id,)
    return tx_or_store.one(sql, params) if isinstance(tx_or_store, Tx) else tx_or_store.read_one(sql, params)


def set_task_state(tx: Tx, task_id: str, to: TaskState, *, error: str | None = None) -> dict:
    row = tx.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if row is None:
        raise ProtocolError("NotFound", "no such task")
    frm = TaskState(row["state"])
    check_transition(frm, to)
    tx.execute("UPDATE tasks SET state = ?, error = ?, updated_at = ? WHERE id = ?",
               (to, error, now_ms(), task_id))
    tx.event("task.state_changed", {"task_id": task_id, "from": frm, "to": to, "error": error},
             conversation_id=row["conversation_id"], task_id=task_id)
    return task_dict(tx.one("SELECT * FROM tasks WHERE id = ?", (task_id,)))


def blocking_task(tx: Tx, conversation_id: str):
    """The task that stops new input in this conversation, if any (INTERRUPTED doesn't block)."""
    placeholders = ",".join("?" for _ in TERMINAL)
    return tx.one(f"SELECT * FROM tasks WHERE conversation_id = ? AND state NOT IN ({placeholders}) "
                  "AND state != ? ORDER BY created_at DESC LIMIT 1",
                  (conversation_id, *TERMINAL, TaskState.INTERRUPTED))


def interrupted_tasks(tx: Tx, conversation_id: str) -> list:
    return tx.execute("SELECT * FROM tasks WHERE conversation_id = ? AND state = ?",
                      (conversation_id, TaskState.INTERRUPTED)).fetchall()


def begin_turn(tx: Tx, task_id: str, epoch: str, provider_label: dict) -> dict:
    task = tx.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    attempt = tx.one("SELECT COALESCE(MAX(attempt), 0) + 1 AS n FROM turns WHERE task_id = ?", (task_id,))["n"]
    turn = {"id": new_id(), "task_id": task_id, "attempt": attempt, "message_id": new_id()}
    tx.execute("INSERT INTO turns (id, task_id, attempt, epoch, message_id, state, started_at) "
               "VALUES (?, ?, ?, ?, ?, 'running', ?)",
               (turn["id"], task_id, attempt, epoch, turn["message_id"], now_ms()))
    tx.event("model.started", {"task_id": task_id, "turn_id": turn["id"], "attempt": attempt,
                               "message_id": turn["message_id"], "provider": provider_label},
             conversation_id=task["conversation_id"], task_id=task_id)
    return turn


def save_draft(store: Store, turn_id: str, text: str, thinking: str, chunk: int) -> None:
    with store.tx() as tx:
        tx.execute("UPDATE turns SET draft_text = ?, draft_thinking = ?, draft_chunk = ? WHERE id = ?",
                   (text, thinking, chunk, turn_id))


def finish_turn(tx: Tx, turn_id: str, state: str) -> None:
    tx.execute("UPDATE turns SET state = ?, finished_at = ? WHERE id = ?", (state, now_ms(), turn_id))


def latest_turn(tx_or_store, task_id: str):
    sql = "SELECT * FROM turns WHERE task_id = ? ORDER BY attempt DESC LIMIT 1"
    return tx_or_store.one(sql, (task_id,)) if isinstance(tx_or_store, Tx) else tx_or_store.read_one(sql, (task_id,))


# How a task ended, as Mei's reply when the model didn't give one (§18.2: every request gets a reply).
ENDED = {
    TaskState.COMPLETED: "I finished, but didn't say anything about it.",
    TaskState.BLOCKED: "I stopped before finishing.",
    TaskState.FAILED: "I couldn't finish this.",
    TaskState.CANCELLED: "Stopped.",
}


def finished_event(tx: Tx, task: dict, *, draft: dict | None = None, outcome: dict | None = None) -> None:
    if task["state"] in ENDED and _needs_reply(tx, task, outcome):
        # A reply that was streaming when it ended is that message, finished with how it ended.
        said = ((draft or {}).get("text") or "").strip()
        turn = latest_turn(tx, task["id"]) if said else None
        streaming = turn["message_id"] if turn and tx.one("SELECT 1 FROM messages WHERE id = ?",
                                                           (turn["message_id"],)) is None else None
        add_message(tx, task["conversation_id"], "assistant", _ending(task, said if streaming else ""),
                    task_id=task["id"], metadata={"ended": task["state"]}, message_id=streaming)
    if task["state"] in (TaskState.COMPLETED, TaskState.BLOCKED):
        memory.write_episode(tx, task)
    payload = {"task_id": task["id"], "state": task["state"], "error": task["error"]}
    if draft is not None:
        payload["draft"] = draft
    if outcome is not None:
        payload["outcome"] = outcome
    tx.event("task.finished", payload, conversation_id=task["conversation_id"], task_id=task["id"])


def _needs_reply(tx: Tx, task: dict, outcome: dict | None) -> bool:
    """The runtime ended it (stopped, failed, or blocked without the model's outcome): the person is told,
    whatever Mei said on the way. The model ended it (an answer, or an outcome): its words are the reply,
    unless it said nothing since the person last spoke."""
    if outcome is None and task["state"] != TaskState.COMPLETED:
        return True
    last = tx.one("SELECT role FROM messages WHERE (id = ? OR task_id = ?) AND role IN ('user', 'assistant') "
                  "AND trim(content) != '' ORDER BY ordinal DESC LIMIT 1", (task["input_message_id"], task["id"]))
    return last is None or last["role"] == "user"


def _ending(task: dict, said: str) -> str:
    """What was streamed before the end, if anything, then how it ended and why."""
    why = (task["error"] or "").strip()
    ended = ENDED[task["state"]] + (" " + why[:1].upper() + why[1:] + ("" if why[-1] in ".!?)" else ".") if why else "")
    return f"{said}\n\n*{ended}*" if said else ended


# ── Idempotent commands ─────────────────────────────────────────────────────


def request_hash(method: str, args) -> str:
    return hashlib.sha256(method.encode() + b"\0" + msgspec.json.encode(args)).hexdigest()


def find_command(tx: Tx, command_id: str, method: str, digest: str) -> dict | None:
    row = tx.one("SELECT * FROM commands WHERE command_id = ?", (command_id,))
    if row is None:
        return None
    if row["method"] != method or row["request_hash"] != digest:
        raise ProtocolError("Conflict", "command_id was already used for a different request")
    return json.loads(row["result"])


def record_command(tx: Tx, command_id: str, method: str, digest: str, result: dict) -> None:
    tx.execute("INSERT INTO commands (command_id, method, request_hash, result, created_at) VALUES (?, ?, ?, ?, ?)",
               (command_id, method, digest, json.dumps(result), now_ms()))


# ── Config ──────────────────────────────────────────────────────────────────


def get_config(store: Store) -> tuple[int, Config]:
    row = store.read_one("SELECT revision, document FROM config WHERE id = 1")
    return int(row["revision"]), msgspec.json.decode(row["document"], type=Config)


def put_config(tx: Tx, expected_revision: int, config: Config) -> int:
    row = tx.one("SELECT revision FROM config WHERE id = 1")
    if int(row["revision"]) != expected_revision:
        raise ProtocolError("Conflict", f"config revision is {row['revision']}, not {expected_revision}")
    revision = expected_revision + 1
    tx.execute("UPDATE config SET revision = ?, document = ? WHERE id = 1",
               (revision, msgspec.json.encode(config).decode()))
    tx.event("config.changed", {"revision": revision})
    return revision


# ── Reads for attach ────────────────────────────────────────────────────────


def list_conversations(store: Store) -> list[dict]:
    """Newest first, each with the state of its task in progress, if any (the popup's task list)."""
    placeholders = ",".join("?" for _ in TERMINAL)
    active = {r["conversation_id"]: r["state"] for r in store.read(
        f"SELECT conversation_id, state FROM tasks WHERE state NOT IN ({placeholders}) ORDER BY created_at",
        tuple(TERMINAL))}
    return [{**conversation_dict(r), "active": active.get(r["id"])}
            for r in store.read("SELECT * FROM conversations ORDER BY updated_at DESC")]


def conversation_snapshot(store: Store, conversation_id: str) -> dict:
    conv = store.read_one("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
    if conv is None:
        raise ProtocolError("NotFound", "no such conversation")
    tasks = store.read("SELECT * FROM tasks WHERE conversation_id = ? ORDER BY created_at", (conversation_id,))
    snapshot_tasks = []
    for t in tasks:
        item = {**task_dict(t), **agent.task_extras(store, t["id"])}
        if t["state"] == TaskState.INTERRUPTED:
            turn = latest_turn(store, t["id"])
            if turn is not None:
                item["draft"] = {"text": turn["draft_text"], "thinking": turn["draft_thinking"]}
        snapshot_tasks.append(item)
    remembered = [memory.memory_view(r) for r in store.read(
        "SELECT * FROM memories WHERE source_conversation_id = ? ORDER BY created_at", (conversation_id,))]
    return {"conversation": conversation_dict(conv),
            "messages": [m for m in history(store, conversation_id) if shown(m)], "tasks": snapshot_tasks,
            "memories": remembered}


def events_after(store: Store, after_seq: int, scope: str) -> list[Envelope]:
    if scope == "all":
        rows = store.read("SELECT * FROM events WHERE seq > ? ORDER BY seq", (after_seq,))
    else:
        rows = store.read("SELECT * FROM events WHERE seq > ? AND (conversation_id = ? OR conversation_id IS NULL) "
                          "ORDER BY seq", (after_seq, scope))
    return [Envelope(type=r["type"], event_id=r["event_id"], epoch=r["epoch"], at=r["at"],
                     required=bool(r["required"]), seq=r["seq"], conversation_id=r["conversation_id"],
                     task_id=r["task_id"], payload=json.loads(r["payload"])) for r in rows]
