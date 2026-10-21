"""Context assembly (§8.3) and the disclosure filter (§13.5).

Earlier tasks in the conversation are collapsed to what was asked and answered, plus a line of
what Mei did; the current task is sent whole, with each batch's results right after the message
that made the calls (providers reject anything between them). Untrusted observations are wrapped
as data. File contents a cloud model may not see, by the person's Privacy setting, are withheld.
"""

import datetime
import ipaddress
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from mei.capabilities.base import Env
from mei.capabilities.registry import Registry
from mei.obs import redact
from mei.protocol import Privacy, ProviderConfig
from mei.providers.base import ChatTurn, ModelRequest, Replay, ToolCall
from mei.providers.profiles import PROFILES
from mei.store.db import Store

from . import prompt

MAX_OBSERVATION_CHARS = 50_000
MAX_PRIOR_ACTIONS_NOTED = 12
WITHHELD = ("[Withheld: the person's Privacy settings don't send this file's contents to cloud models. "
            "Tell them what you couldn't read; they can change it in Mei's Settings → Privacy.]")


def is_cloud(cfg: ProviderConfig) -> bool:
    """Does this provider take data off the machine? Local and custom endpoints count as local only
    when their URL really points at this machine."""
    if cfg.id == "fake":
        return bool(cfg.options.get("cloud"))
    profile = PROFILES.get(cfg.id)
    if profile is None or profile.type == "cloud":
        return True
    return not is_loopback_url(cfg.url.strip() or profile.chat_url)


def is_loopback_url(url: str) -> bool:
    """http(s) to localhost or a loopback address, with no user part. Anything unclear is remote:
    `https://localhost.example.com` and `https://localhost@example.com` both go elsewhere."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or "@" in parts.netloc:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Inputs:
    store: Store
    env: Env
    registry: Registry
    privacy: Privacy
    provider: ProviderConfig
    now: datetime.datetime
    tools: bool = True
    memories: tuple[dict, ...] = ()  # recalled for this task (core/memories.py)
    episodes: tuple[dict, ...] = ()
    hidden_tools: frozenset[str] = frozenset()  # capability names not offered (memory turned off)


def build(inputs: Inputs, task) -> ModelRequest:
    store = inputs.store
    plan = json.loads(task["plan"])
    rows = store.read("SELECT * FROM messages WHERE conversation_id = ? ORDER BY ordinal", (task["conversation_id"],))
    input_ordinal = next(r["ordinal"] for r in rows if r["id"] == task["input_message_id"])
    actions = {a["id"]: a for a in store.read("SELECT * FROM actions WHERE task_id = ?", (task["id"],))}
    turns = [ChatTurn("system", prompt.system_prompt(inputs.env, inputs.now, plan, memories=inputs.memories,
                                                     episodes=inputs.episodes))]
    turns += _earlier(store, [r for r in rows if r["ordinal"] < input_ordinal])
    turns += _current(inputs, task["id"], [r for r in rows if r["ordinal"] == input_ordinal or
                               (r["task_id"] == task["id"] and r["ordinal"] > input_ordinal)], actions)
    tools = inputs.registry.specs(inputs.env, without=inputs.hidden_tools) if inputs.tools else ()
    return ModelRequest(turns, tools=tools)


def _earlier(store: Store, rows: list) -> list[ChatTurn]:
    done = _done_by_task(store, {r["task_id"] for r in rows if r["task_id"]})
    last_answer: dict[str, int] = {}
    for i, r in enumerate(rows):
        if r["role"] == "assistant" and not r["tool_calls"] and r["task_id"]:
            last_answer[r["task_id"]] = i
    turns = []
    for i, r in enumerate(rows):
        if r["role"] == "user":
            turns.append(ChatTurn("user", r["content"]))
        elif r["role"] == "assistant" and not r["tool_calls"] and r["content"]:
            note = ""
            if r["task_id"] and last_answer.get(r["task_id"]) == i and done.get(r["task_id"]):
                note = "\n\n[What Mei did: " + "; ".join(done[r["task_id"]]) + "]"
            turns.append(ChatTurn("assistant", r["content"] + note))
    return turns


def _done_by_task(store: Store, task_ids: set[str]) -> dict[str, list[str]]:
    if not task_ids:
        return {}
    marks = ",".join("?" for _ in task_ids)
    rows = store.read(f"SELECT task_id, result FROM actions WHERE task_id IN ({marks}) AND execution = 'SUCCEEDED' "
                      "AND capability NOT IN ('plan.update', 'ask_user', 'task.finish') ORDER BY created_at",
                      tuple(task_ids))
    done: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        summary = (json.loads(r["result"]) if r["result"] else {}).get("summary")
        if summary and len(done[r["task_id"]]) < MAX_PRIOR_ACTIONS_NOTED:
            done[r["task_id"]].append(summary)
    return done


def _current(inputs: Inputs, task_id: str, rows: list, actions: dict) -> list[ChatTurn]:
    results = {r["action_id"]: r for r in rows if r["role"] == "tool"}
    by_batch: dict[str, list] = defaultdict(list)
    for a in actions.values():
        by_batch[a["batch_id"]].append(a)
    batch_of_message = {r["message_id"]: r["id"] for r in
                        inputs.store.read("SELECT id, message_id FROM batches WHERE task_id = ?", (task_id,))}
    turns: list[ChatTurn] = []
    for r in rows:
        if r["role"] == "tool":
            continue  # placed right after the call that asked for it
        if r["role"] == "system":
            turns.append(ChatTurn("user", f"<runtime_note>{r['content']}</runtime_note>"))
        elif r["role"] == "user":
            turns.append(ChatTurn("user", r["content"]))
        elif r["role"] == "assistant":
            calls = [ToolCall(c["id"], c["name"], c["arguments"], c.get("signature", "")) for c in
                     json.loads(r["tool_calls"] or "[]")]
            replay = json.loads(r["replay"]) if r["replay"] else None
            turns.append(ChatTurn("assistant", r["content"], tool_calls=tuple(calls),
                                  replay=Replay(replay["format"], replay["data"]) if replay else None))
            batch_id = batch_of_message.get(r["id"])
            for action in sorted(by_batch.get(batch_id, []), key=lambda a: a["position"]):
                message = results.get(action["id"])
                if message is not None:
                    turns.append(_tool_turn(inputs, action, message))
    return turns


def _tool_turn(inputs: Inputs, action, message) -> ChatTurn:
    result = json.loads(action["result"]) if action["result"] else {}
    meta = json.loads(message["metadata"])
    content = message["content"]
    if not _may_send(inputs, action, result):
        content = WITHHELD
    elif result.get("trust") == "untrusted":
        source = " ".join([action["capability"] or action["tool"],
                           *[inputs.env.show(s) for s in result.get("sources", [])]])
        body = content.replace("</observation>", "</observation_>")  # content can't close its own wrapper
        content = f'<observation source="{source}" trust="untrusted">\n{body}\n</observation>'
    return ChatTurn("tool", redact(content)[:MAX_OBSERVATION_CHARS], tool_call_id=action["call_id"],
                    name=action["tool"], is_error=bool(meta.get("is_error")))


def _may_send(inputs: Inputs, action, result: dict) -> bool:
    if result.get("data_class") != "file_content" or not is_cloud(inputs.provider):
        return True
    choice = inputs.privacy.cloud_files
    if choice == "always":
        return True
    if choice == "never":
        return False
    if action["approval_id"] or (json.loads(action["effects"] or "{}")).get("disclosure") == "off_machine":
        return True  # the person allowed this read on a card (or by a grant) that said where its contents go
    anchored = {Path(r["value"]) for r in json.loads(action["resources"]) if r.get("provenance") == "user"}
    return all(Path(s) in anchored or any(a in Path(s).parents for a in anchored) for s in result.get("sources", []))
