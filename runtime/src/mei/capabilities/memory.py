"""Memory tools (§17.5): save, search, and forget memories, and search past conversations.

Saving is carried out by the loop, which knows where the words came from (core/remember.py).
Forgetting archives the memory, so it can be restored in Settings; deleting for good is the
person's own action there.
"""

import datetime
from typing import Annotated

import msgspec

from .base import (LOCAL_UNDOABLE, ActionContext, ActionResult, Availability, AVAILABLE, Capability, CapabilityError,
                   Effects, Env, Resource)

_SOURCES = {"user_stated": "you said this", "inferred": "Mei inferred this", "untrusted": "from something Mei read"}


def _needs_memory(env: Env) -> Availability:
    return AVAILABLE if env.memory is not None else Availability.unavailable("memory isn't available")


def _day(ms: int) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


class SaveParams(msgspec.Struct, kw_only=True):
    text: Annotated[str, msgspec.Meta(description="One lasting fact or preference, in a short sentence, e.g. "
                                                  "\"Invoices go in Documents/Invoices/<year>\"")]


class MemorySave(Capability):
    name = "memory.save"
    summary = ("Remember a lasting fact or preference about the person for future conversations: when they ask "
               "you to remember something, or tell you something about themselves worth keeping.")
    Params = SaveParams
    meta = True

    def available(self, env: Env) -> Availability:
        return _needs_memory(env)

    def describe(self, p: SaveParams, env: Env) -> str:
        return f"Remember: {p.text}"


class SearchParams(msgspec.Struct, kw_only=True):
    query: Annotated[str, msgspec.Meta(description="Words to look for")]
    limit: Annotated[int, msgspec.Meta(ge=1, le=30)] = 10


class MemorySearch(Capability):
    name = "memory.search"
    summary = "Look up what Mei remembers about the person (relevant memories are already in your context)."
    Params = SearchParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_memory(env)

    def describe(self, p: SearchParams, env: Env) -> str:
        return f"Search memories for “{p.query}”"

    async def run(self, p: SearchParams, ctx: ActionContext) -> ActionResult:
        found = ctx.env.memory.search(p.query, p.limit)
        # A local-only memory's text never goes in a tool result, which may reach a cloud model now or
        # later in the conversation. On this computer it reaches the model through recall instead.
        shared = [m for m in found if m.get("sensitivity") != "local_only"]
        lines = [f"- [{m['id'][:8]}] {m['text']} ({_SOURCES.get(m['provenance'], m['provenance'])})" for m in shared]
        if kept := len(found) - len(shared):
            lines.append(f"({kept} more marked local only: not shown here)")
        return ActionResult(ok=True, observation="\n".join(lines) or "Nothing remembered about that.",
                            summary=f"Searched memories ({len(found)} found)", data_class="memory",
                            memory_ids=[m["id"] for m in shared])


class HistoryParams(msgspec.Struct, kw_only=True):
    query: Annotated[str, msgspec.Meta(description="Words to look for in earlier conversations")]
    limit: Annotated[int, msgspec.Meta(ge=1, le=30)] = 10


class HistorySearch(Capability):
    name = "history.search"
    summary = "Search earlier conversations with the person (their messages and your replies)."
    Params = HistoryParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_memory(env)

    def describe(self, p: HistoryParams, env: Env) -> str:
        return f"Search earlier conversations for “{p.query}”"

    async def run(self, p: HistoryParams, ctx: ActionContext) -> ActionResult:
        found = ctx.env.memory.history(p.query, p.limit)
        lines = [f"- {_day(h['created_at'])}, “{h['title']}”, {'they said' if h['role'] == 'user' else 'Mei said'}: "
                 f"{' '.join(h['content'].split())[:300]}" for h in found]
        # Replies in old conversations may quote documents: data, not instructions.
        return ActionResult(ok=True, observation="\n".join(lines) or "No earlier conversation mentions that.",
                            summary=f"Searched earlier conversations ({len(found)} found)", trust="untrusted",
                            from_tasks=[h["task_id"] for h in found if h["role"] == "assistant" and h.get("task_id")])


class ForgetParams(msgspec.Struct, kw_only=True):
    memory_id: Annotated[str, msgspec.Meta(description="The memory's id (its first 8 characters will do)")]


class MemoryForget(Capability):
    name = "memory.forget"
    summary = "Stop using a memory (it can be restored from Mei's Settings)."
    Params = ForgetParams

    def available(self, env: Env) -> Availability:
        return _needs_memory(env)

    def effects(self, p: ForgetParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: ForgetParams, env: Env) -> list[Resource]:
        memory = self._find(p, env)
        return [Resource(kind="memory", value=memory["id"], access="write", role="memory", aliases=(memory["text"],))]

    def describe(self, p: ForgetParams, env: Env) -> str:
        try:
            return f"Forget: {self._find(p, env)['text']}"
        except CapabilityError:
            return f"Forget memory {p.memory_id}"

    async def run(self, p: ForgetParams, ctx: ActionContext) -> ActionResult:
        memory = ctx.env.memory.archive(self._find(p, ctx.env)["id"])
        said = f"memory {memory['id'][:8]} (local only)" if memory.get("sensitivity") == "local_only" else memory["text"]
        return ActionResult(ok=True, observation=f"Forgot: {said}", summary=f"Forgot: {memory['text']}",
                            undo={"kind": "memory", "memory_id": memory["id"]}, data_class="memory",
                            memory_ids=[memory["id"]])

    @staticmethod
    def _find(p: ForgetParams, env: Env) -> dict:
        memory = env.memory.get(p.memory_id.strip()) if env.memory else None
        if memory is None or memory["status"] == "archived":
            raise CapabilityError("not_found", f"no memory {p.memory_id}")
        return memory

