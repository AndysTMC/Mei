"""Record real event streams from the engine into protocol/fixtures/ (shared with the TS tests).

Run after changing the protocol:  uv run python tests/make_fixtures.py
"""

import asyncio
import json
import tempfile
from pathlib import Path

import msgspec

from mei.core.engine import Engine
from mei.ipc.service import RuntimeService
from mei.protocol import Config, ProviderConfig, ProviderSettings, SubmitInputArgs, TaskCommandArgs, UpdateConfigArgs
from mei.providers.fake import FakeProvider
from mei.store.db import Store

OUT = Path(__file__).resolve().parents[2] / "protocol" / "fixtures"
REPLY = "Mei keeps every word, even across restarts."


class Tape:
    """Records durable events and deltas in the order the client would receive them."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def publish(self, events) -> None:
        self.items += [msgspec.to_builtins(e) for e in events]

    def publish_ephemeral(self, event) -> None:
        self.items.append(msgspec.to_builtins(event))


async def factory(cfg: ProviderConfig):
    return FakeProvider(cfg.options)


def engine(path: Path, tape: Tape, **options) -> Engine:
    eng = Engine(Store(path), tape, factory)
    eng.update_config(UpdateConfigArgs(eng.get_config()["revision"], Config(active="fake", providers={"fake": ProviderSettings(
        model="fake-1", options={"reply": REPLY, "chunk_chars": 5, "delay_ms": 12, "thinking": "Let me think.", **options})})))
    tape.items.clear()
    return eng


def attach_reply(eng: Engine, after_seq: int = 0) -> dict:
    service = RuntimeService(bus=None, engine=eng)  # _attach only reads; nothing is sent
    return service._attach(":test", json.dumps({"scope": "all", "after_seq": after_seq}))


async def until(pred, timeout=5.0):
    async with asyncio.timeout(timeout):
        while not pred():
            await asyncio.sleep(0.005)


def finished(tape: Tape, task_id: str) -> bool:
    return any(i["type"] == "task.finished" and i["task_id"] == task_id for i in tape.items)


def deltas(tape: Tape) -> int:
    return sum(1 for i in tape.items if i["type"] == "message.delta")


async def turn_completed(d: Path) -> dict:
    tape = Tape()
    eng = engine(d, tape)
    attach = attach_reply(eng)
    r = eng.submit_input(SubmitInputArgs(command_id="cmd-1", text="Remember this?"))
    await until(lambda: finished(tape, r["task_id"]))
    return {"description": "A new conversation, one streamed reply with thinking, completed.",
            "attach": attach, "events": tape.items, "expect": {"conversation_id": r["conversation_id"],
                                                               "reply": REPLY, "state": "COMPLETED"}}


async def turn_cancelled(d: Path) -> dict:
    tape = Tape()
    eng = engine(d, tape, delay_ms=20)
    attach = attach_reply(eng)
    r = eng.submit_input(SubmitInputArgs(command_id="cmd-1", text="Stop me"))
    await until(lambda: deltas(tape) >= 4)
    eng.cancel(TaskCommandArgs(command_id="cmd-2", task_id=r["task_id"]))
    await until(lambda: finished(tape, r["task_id"]))
    return {"description": "The user stops the reply mid-stream.", "attach": attach, "events": tape.items,
            "expect": {"conversation_id": r["conversation_id"], "state": "CANCELLED"}}


async def interrupted_then_resumed(d: Path) -> dict:
    tape = Tape()
    eng = engine(d, tape, delay_ms=20)
    attach = attach_reply(eng)
    r = eng.submit_input(SubmitInputArgs(command_id="cmd-1", text="Survive a restart"))
    await until(lambda: deltas(tape) >= 4)
    await eng.shutdown()  # the runtime restarts (e.g. an update) mid-reply
    eng.store.close()
    eng2 = Engine(Store(d), tape, factory)
    eng2.recover()
    interrupted_at = len(tape.items)
    eng2.resume(TaskCommandArgs(command_id="cmd-2", task_id=r["task_id"]))
    await until(lambda: sum(1 for i in tape.items if i["type"] == "task.finished") >= 2)
    return {"description": "Mei restarts mid-reply (task INTERRUPTED with a draft), then the user resumes.",
            "attach": attach, "events": tape.items, "interrupted_at": interrupted_at,
            "expect": {"conversation_id": r["conversation_id"], "reply": REPLY, "state": "COMPLETED"}}


async def reattach_mid_stream(d: Path) -> dict:
    tape = Tape()
    long_reply = " ".join([REPLY] * 6)
    eng = engine(d, tape, delay_ms=20, reply=long_reply)
    r = eng.submit_input(SubmitInputArgs(command_id="cmd-1", text="Reconnect while I talk"))
    await until(lambda: deltas(tape) >= 3)
    seen = list(tape.items)
    last_seq = max(i["seq"] for i in seen if i["seq"] is not None)
    await until(lambda: deltas(tape) >= 6)
    missed = len(tape.items)
    reply = attach_reply(eng, after_seq=last_seq)
    await until(lambda: finished(tape, r["task_id"]))
    return {"description": "A client saw the start of a reply, missed some deltas while detached, then "
                           "re-attached with after_seq; the reply includes the partial stream.",
            "before": seen, "attach": reply, "events": tape.items[missed:],
            "expect": {"conversation_id": r["conversation_id"], "reply": long_reply, "state": "COMPLETED"}}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for scenario in (turn_completed, turn_cancelled, interrupted_then_resumed, reattach_mid_stream):
        with tempfile.TemporaryDirectory() as tmp:
            data = await scenario(Path(tmp))
        path = OUT / f"{scenario.__name__}.json"
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(OUT.parents[2])} ({len(data['events'])} events)")


if __name__ == "__main__":
    asyncio.run(main())
