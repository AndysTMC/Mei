"""Memory as the engine uses it: the port the memory tools reach, recall into a task, the episode
written when a task ends, and the person's own edits (§17)."""

import json
from collections.abc import Callable

from mei.core.context import memory_may_leave, ran_locally
from mei.protocol import Envelope
from mei.store import memory as mem
from mei.store.db import Store

RECALL_LIMIT = 8
EPISODE_LIMIT = 3


class StoreMemory:
    """The memory tools' port (capabilities.base.MemoryPort), over the store."""

    def __init__(self, store: Store, publish: Callable[[list[Envelope]], None]) -> None:
        self._store = store
        self._publish = publish

    def search(self, text: str, limit: int) -> list[dict]:
        return [mem.memory_view(r) for r in mem.search(self._store, text, limit=limit)]

    def history(self, text: str, limit: int) -> list[dict]:
        return [dict(r) for r in mem.search_history(self._store, text, limit=limit)]

    def get(self, memory_id: str) -> dict | None:
        """By id, or by the first 8 characters the tools show."""
        row = mem.get_memory(self._store, memory_id)
        if row is None and len(memory_id) >= 8:
            rows = self._store.read("SELECT * FROM memories WHERE id LIKE ? LIMIT 2", (memory_id + "%",))
            row = rows[0] if len(rows) == 1 else None
        return mem.memory_view(row) if row is not None else None

    def archive(self, memory_id: str) -> dict | None:
        with self._store.tx() as tx:
            view = mem.update_memory(tx, memory_id, status="archived")
        self._publish(tx.events)
        return view


def recall(store: Store, task, *, local_only_ok: bool) -> list[dict]:
    """The memories a task's request brings up, remembered on the task so policy and later steps
    see the same set. `local_only_ok`: false for cloud models, which never see local-only memories."""
    request = " ".join(r["content"] for r in store.read(
        "SELECT content FROM messages WHERE role = 'user' AND (id = ? OR task_id = ?)",
        (task["input_message_id"], task["id"])))
    found = [r for r in mem.recall(store, request, limit=RECALL_LIMIT) if local_only_ok or memory_may_leave(store, r)]
    ids = [r["id"] for r in found]  # what the request brought up: for policy, the person's words (§17.5)
    # Matching words alone find nothing for a question about the person in general (decision 0035: "Do you
    # know what I like?" against "I love Android", "What do you know about me?" against everything). The
    # places words leave are filled with what matters most anyway. Shown, not vouched for: only what the
    # request matched counts as the person's words.
    found += [r for r in mem.best_known(store, exclude=ids, limit=RECALL_LIMIT - len(found))
              if local_only_ok or memory_may_leave(store, r)]
    previous = json.loads(task["recalled"])
    if set(ids) - set(previous):
        with store.tx() as tx:
            tx.execute("UPDATE tasks SET recalled = ? WHERE id = ?", (json.dumps(list(dict.fromkeys(previous + ids))),
                                                                      task["id"]))
            mem.mark_used(tx, [i for i in ids if i not in previous])
    return [mem.memory_view(r) for r in found]


def episodes(store: Store, task, *, cloud: bool = False) -> list[dict]:
    """Earlier tasks like this one. For a cloud model, not those a local model answered (decision 0042)."""
    request = store.read_one("SELECT content FROM messages WHERE id = ?", (task["input_message_id"],))["content"]
    found = [dict(r) for r in mem.episodes(store, request, limit=EPISODE_LIMIT,
                                           exclude_conversation=task["conversation_id"])]
    local = ran_locally(store, [e["task_id"] for e in found]) if cloud else set()
    return [e for e in found if e["task_id"] not in local]


def stated(store: Store, task) -> list[str]:
    """Texts of the user-stated memories this task recalled: for policy, words the person said (§17.5)."""
    ids = json.loads(task["recalled"])
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    return [r["text"] for r in store.read(f"SELECT text FROM memories WHERE id IN ({marks}) AND status = 'active' "
                                          "AND provenance = 'user_stated'", tuple(ids))]
