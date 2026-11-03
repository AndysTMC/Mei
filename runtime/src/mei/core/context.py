"""Context assembly (§8.3) and the disclosure filter (§13.5).

Earlier tasks in the conversation are collapsed to what was asked and answered, plus a line of
what Mei did; the current task is sent whole, with each batch's results right after the message
that made the calls (providers reject anything between them). Untrusted observations are wrapped
as data. File contents a cloud model may not see, by the person's Privacy setting, are withheld.
"""

import base64
import datetime
import ipaddress
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from mei.capabilities.base import Env
from mei.capabilities.registry import Registry
from mei.obs import redact
from mei.protocol import Privacy, ProviderConfig
from mei.providers.base import ChatTurn, ModelRequest, ProviderError, Replay, ToolCall
from mei.providers.profiles import PROFILES
from mei.store.db import Store

from . import prompt

MAX_OBSERVATION_CHARS = 50_000
# Existing text character caps, tool definitions included (decision 0037). These aren't a model's
# token capacity; per-model limits and image accounting need a separate design.
BUDGET_CHARS = {"cloud": 400_000, "local": 64_000}
KEEP_WHOLE = 3  # the current task's newest tool results, never shortened
SHORTENED_CHARS = 2_000
SHORTENED_NOTE = "\n[… shortened so the request fits the model; run the tool again for the rest]"
MAX_PRIOR_ACTIONS_NOTED = 12
WITHHELD = ("[Withheld: the person's privacy choices keep this result on this computer. "
            "Tell them which information wasn't available.]")


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
    spoken = any(r["id"] == task["input_message_id"] and json.loads(r["metadata"] or "{}").get("source") == "voice"
                 for r in rows)
    tools = inputs.registry.specs(inputs.env, without=inputs.hidden_tools) if inputs.tools else ()
    turns = [ChatTurn("system", prompt.system_prompt(inputs.env, inputs.now, plan, memories=inputs.memories,
                                                     episodes=inputs.episodes, spoken=spoken,
                                                     sees=any(t.name == "desktop_observe" for t in tools)))]
    earlier = _earlier(inputs, [r for r in rows if r["ordinal"] < input_ordinal])
    current = _current(inputs, task["id"], [r for r in rows if r["ordinal"] == input_ordinal or
                                 (r["task_id"] == task["id"] and r["ordinal"] > input_ordinal)], actions)
    budget = BUDGET_CHARS["cloud" if is_cloud(inputs.provider) else "local"]
    # Reserve tool definitions and request wrapper as well, including tool names. This bounds the
    # serialized text/tool fields, not the provider's exact token or image capacity.
    room = budget - (len(json.dumps(asdict(ModelRequest([], tools)), ensure_ascii=False)) - 2)
    return ModelRequest(fit(turns[0], earlier, current, room), tools=tools)


def fit(system: ChatTurn, earlier: list[ChatTurn], current: list[ChatTurn], room: int) -> list[ChatTurn]:
    """Text/tool fields within `room` characters (decision 0037). The system prompt and the person's request stay
    whole. Earlier turns of the conversation go first, oldest first, and the model is told; then the current
    task's older tool results are shortened, the newest KEEP_WHOLE of them never."""
    need = _size(system) + sum(map(_size, current))
    kept = deque(earlier)
    prior_size = sum(map(_size, kept))

    def notice() -> str:
        left_out = len(earlier) - len(kept)
        return (f"<runtime_note>{left_out} earlier messages of this conversation "
                "are left out: the model can't hold them all.</runtime_note>\n") if left_out else ""

    def overflow() -> int:
        # The prefix is part of a JSON string: its escaped newlines also consume the cap.
        return need + prior_size + len(json.dumps(notice(), ensure_ascii=False)) - 2 - room

    while kept and overflow() > 0:
        prior_size -= _size(kept.popleft())
        while kept and kept[0].role != "user":  # whole exchanges: never an answer without its question
            prior_size -= _size(kept.popleft())
    current = list(current)
    tool_at = [i for i, t in enumerate(current) if t.role == "tool"]
    for i in tool_at[:-KEEP_WHOLE] if overflow() > 0 else ():
        turn = current[i]
        if len(turn.content) > SHORTENED_CHARS:
            content = turn.content[:SHORTENED_CHARS] + SHORTENED_NOTE
            current[i] = replace(turn, content=content)
            need -= _size(turn) - _size(current[i])
        if overflow() <= 0:
            break
    if overflow() > 0:
        raise ProviderError("This request exceeds Mei's current context budget. Start a new conversation or ask "
                            "for a smaller part. Your stored history has not been deleted.")
    if notice():
        first = next(i for i, t in enumerate([*kept, *current]) if t.role == "user")
        turns = [*kept, *current]
        turns[first] = replace(turns[first], content=notice() + turns[first].content)
        return [system, *turns]
    return [system, *kept, *current]


def _size(turn: ChatTurn) -> int:
    # Images aren't text tokens: charging their base64 length breaks ordinary screenshots. Keep
    # them intact; accurate image costs need model-specific accounting. Include signatures, replay
    # and JSON escaping. Two extra characters cover the array's brackets/separators per item.
    return len(json.dumps(asdict(replace(turn, images=())), ensure_ascii=False)) + 2


def _earlier(inputs: Inputs, rows: list) -> list[ChatTurn]:
    done = _done_by_task(inputs, {r["task_id"] for r in rows if r["task_id"]})
    last_answer: dict[str, int] = {}
    for i, r in enumerate(rows):
        if r["role"] == "assistant" and not r["tool_calls"] and r["task_id"]:
            last_answer[r["task_id"]] = i
    turns = []
    for i, r in enumerate(rows):
        if r["role"] == "user":
            turns.append(_user_turn(r))
        elif r["role"] == "assistant" and not r["tool_calls"] and r["content"]:
            note = ""
            if r["task_id"] and last_answer.get(r["task_id"]) == i and done.get(r["task_id"]):
                note = "\n\n[What Mei did: " + "; ".join(done[r["task_id"]]) + "]"
            turns.append(ChatTurn("assistant", r["content"] + note))
    return turns


def _done_by_task(inputs: Inputs, task_ids: set[str]) -> dict[str, list[str]]:
    if not task_ids:
        return {}
    marks = ",".join("?" for _ in task_ids)
    rows = inputs.store.read(f"SELECT * FROM actions WHERE task_id IN ({marks}) AND execution = 'SUCCEEDED' "
                      "AND capability NOT IN ('plan.update', 'ask_user', 'task.finish') ORDER BY created_at",
                      tuple(task_ids))
    done: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        result = json.loads(r["result"]) if r["result"] else {}
        summary = result.get("summary")
        if summary and len(done[r["task_id"]]) < MAX_PRIOR_ACTIONS_NOTED:
            # Derived context is subject to the same disclosure rules as the original observation,
            # including already-stored results and memories whose sensitivity changed since the action.
            done[r["task_id"]].append(redact(summary) if _may_send(inputs, r, result) else WITHHELD)
    return done


def _current(inputs: Inputs, task_id: str, rows: list, actions: dict) -> list[ChatTurn]:
    results = {r["action_id"]: r for r in rows if r["role"] == "tool"}
    by_batch: dict[str, list] = defaultdict(list)
    for a in actions.values():
        by_batch[a["batch_id"]].append(a)
    batch_of_message = {r["message_id"]: r["id"] for r in
                        inputs.store.read("SELECT id, message_id FROM batches WHERE task_id = ?", (task_id,))}
    # Only the latest picture goes to the model: one is enough to act on, and each costs many tokens.
    pictured = [a for a in actions.values() if (json.loads(a["result"] or "{}")).get("images")]
    latest_picture = max(pictured, key=lambda a: (a["created_at"], a["position"]))["id"] if pictured else None
    turns: list[ChatTurn] = []
    for r in rows:
        if r["role"] == "tool":
            continue  # placed right after the call that asked for it
        if r["role"] == "system":
            turns.append(ChatTurn("user", f"<runtime_note>{r['content']}</runtime_note>"))
        elif r["role"] == "user":
            turns.append(_user_turn(r))
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
                    turns.append(_tool_turn(inputs, action, message, picture=action["id"] == latest_picture))
    return turns


def attachment_of(message) -> dict | None:
    """What the person attached to this message ("Ask about this", or a drop on Mei), if anything."""
    return json.loads(message["metadata"] or "{}").get("attachment")


def _user_turn(message) -> ChatTurn:
    """The person's words, then what they attached: text marked as content others wrote, dropped
    files by their paths (the person chose them; what they hold is read like any file)."""
    attachment = attachment_of(message)
    if not attachment:
        return ChatTurn("user", message["content"])
    kind = attachment.get("kind", "selection")
    if kind == "files":
        # One JSON string per line, so a name with quotes or a line break still reads back exactly. Not
        # redacted: the model needs the very path to open the file, and the policy judges that path.
        body = "\n".join(json.dumps(p, ensure_ascii=False) for p in attachment.get("paths", []))
        return ChatTurn("user", f'{message["content"]}\n\n<attachment kind="files">\n{_unclosable(body)}\n</attachment>')
    named = (("app", attachment.get("app_id", "").removesuffix(".desktop")), ("window", attachment.get("window_title", "")))
    attrs = "".join(f' {name}="{_attr(value)}"' for name, value in named if value)
    block = f'<attachment kind="{kind}"{attrs} trust="untrusted">\n{_unclosable(attachment.get("text", ""))}\n</attachment>'
    return ChatTurn("user", f"{message['content']}\n\n{redact(block)}")


def _unclosable(body: str) -> str:
    """What others wrote can't close its own wrapper."""
    return body.replace("</attachment>", "</attachment_>")


def _attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _pictures(result: dict) -> tuple[str, ...]:
    """A result's pictures as base64, read back from the conversation's artifacts (gone: none)."""
    out = []
    for path in result.get("images", []):
        try:
            out.append(base64.b64encode(Path(path).read_bytes()).decode())
        except OSError:
            continue
    return tuple(out)


def _tool_turn(inputs: Inputs, action, message, *, picture: bool = False) -> ChatTurn:
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
    images = _pictures(result) if picture and _may_send(inputs, action, result) else ()
    return ChatTurn("tool", redact(content)[:MAX_OBSERVATION_CHARS], tool_call_id=action["call_id"],
                    name=action["tool"], is_error=bool(meta.get("is_error")), images=images)


def _may_send(inputs: Inputs, action, result: dict) -> bool:
    if not is_cloud(inputs.provider):
        return True
    memory_ids = result.get("memory_ids")
    resources = json.loads(action["resources"] or "[]")
    judged_memories = [r["value"] for r in resources if r.get("kind") == "memory"]
    if memory_ids is None:
        # Save/forget results from before provenance was recorded already carry an id. Old searches
        # cannot vouch for which memories they quoted; keep those untracked results off cloud models.
        memory_id = result.get("memory_id") or (result.get("undo") or {}).get("memory_id")
        if memory_id or judged_memories:
            memory_ids = [memory_id] if memory_id else []
        elif result.get("data_class") == "memory":
            return False
    if memory_ids is not None:
        if not isinstance(memory_ids, list) or any(not isinstance(i, str) for i in memory_ids):
            return False
        for memory_id in set(memory_ids + judged_memories):
            row = inputs.store.read_one("SELECT sensitivity FROM memories WHERE id = ?", (memory_id,))
            if row is None or row["sensitivity"] == "local_only":
                return False  # deleted or local-only: an old summary cannot override that choice
    if result.get("data_class") not in ("file_content", "clipboard"):
        return True
    choice = inputs.privacy.cloud_files
    if choice == "always":
        return True
    if choice == "never":
        return False
    if action["approval_id"] or (json.loads(action["effects"] or "{}")).get("disclosure") == "off_machine":
        return True  # the person allowed this read on a card (or by a grant) that said where its contents go
    sources = result.get("sources", [])
    if not sources:  # file content with nothing to say where it came from stays on this computer
        return result.get("data_class") == "clipboard"
    anchored = {Path(r["value"]) for r in json.loads(action["resources"]) if r.get("provenance") == "user"}
    return all(Path(s) in anchored or any(a in Path(s).parents for a in anchored) for s in sources)
