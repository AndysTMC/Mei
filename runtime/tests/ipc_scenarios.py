"""Client scenarios run inside a private session bus (see test_ipc.py). Prints one JSON result.

The runtime is started by D-Bus activation, exactly as the extension will start it.
Usage: python ipc_scenarios.py <scenario> <workdir>
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

NAME, PATH, IFACE = "com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime"
REPLY = "Durable streaming survives restarts and reconnects. " * 8


class Client:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self.events: list[dict] = []
        self.deltas: list[dict] = []
        bus.add_message_handler(self._on)

    def _on(self, msg: Message):
        if msg.message_type == MessageType.SIGNAL and msg.member == "Event" and msg.interface == IFACE:
            env = json.loads(msg.body[0])
            (self.events if env["seq"] is not None else self.deltas).append(env)

    async def call(self, member: str, args: dict | None = None) -> dict:
        reply = await self.bus.call(Message(destination=NAME, path=PATH, interface=IFACE, member=member,
                                            signature="s", body=[json.dumps(args or {})]))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body[0] if reply.body else ''}")
        return json.loads(reply.body[0])

    async def hello(self) -> dict:
        return await self.call("Hello", {"client": {"kind": "test"}, "protocol": [2, 0]})

    async def until(self, pred, timeout=15.0):
        async with asyncio.timeout(timeout):
            while not pred():
                await asyncio.sleep(0.01)

    def finished(self, task_id: str) -> dict | None:
        return next((e for e in self.events if e["type"] == "task.finished" and e["task_id"] == task_id), None)


async def configure(c: Client, workdir: str, **options) -> None:
    cfg = await c.call("GetConfig")
    opts = {"reply": REPLY, "chunk_chars": 4, "delay_ms": 10, "call_log": f"{workdir}/calls.jsonl", **options}
    await c.call("UpdateConfig", {"revision": cfg["revision"],
                                  "config": {"active": "fake", "providers": {"fake": {"options": opts}}}})


def calls(workdir: str) -> int:
    path = f"{workdir}/calls.jsonl"
    return len(open(path).read().splitlines()) if os.path.exists(path) else 0


async def stream(c: Client, workdir: str) -> dict:
    await c.hello()
    await configure(c, workdir)
    att = await c.call("Attach", {"scope": "all", "after_seq": 0})
    r = await c.call("SubmitInput", {"command_id": str(uuid.uuid4()), "text": "hello"})
    await c.until(lambda: c.finished(r["task_id"]))
    seqs = [e["seq"] for e in c.events]
    final = next(e for e in c.events if e["type"] == "message.completed" and e["payload"]["message"]["role"] == "assistant")
    return {"mode": att["mode"], "seq_contiguous": seqs == list(range(seqs[0], seqs[0] + len(seqs))),
            "state": c.finished(r["task_id"])["payload"]["state"],
            "deltas_match": "".join(d["payload"]["text"] for d in c.deltas) == final["payload"]["message"]["content"] == REPLY,
            "chunks_contiguous": [d["payload"]["chunk"] for d in c.deltas] == list(range(1, len(c.deltas) + 1))}


async def reattach(c: Client, workdir: str) -> dict:
    """Detach mid-stream, miss events, re-attach with after_seq: the answer must come out whole."""
    await c.hello()
    await configure(c, workdir, delay_ms=25)
    await c.call("Attach", {"scope": "all", "after_seq": 0})
    r = await c.call("SubmitInput", {"command_id": str(uuid.uuid4()), "text": "hello"})
    await c.until(lambda: len(c.deltas) >= 3)
    await c.call("Detach")
    last_seq = max(e["seq"] for e in c.events)
    seen_text = "".join(d["payload"]["text"] for d in c.deltas)
    other = await c.call("SubmitInput", {"command_id": str(uuid.uuid4()), "text": "a second chat"})
    await asyncio.sleep(0.6)  # deltas and durable events (the second chat's) are missed here
    missed_while_detached = len(c.deltas)
    att = await c.call("Attach", {"scope": "all", "after_seq": last_seq})
    stream_view = next(s for s in att["streams"] if s["task_id"] == r["task_id"])
    text, chunk = stream_view["text"], stream_view["chunk"]  # partial answer available at once
    replayed = att["events"]
    await c.until(lambda: c.finished(r["task_id"]))
    for d in c.deltas[missed_while_detached:]:
        if d["payload"]["chunk"] > chunk:
            assert d["payload"]["chunk"] == chunk + 1, "delta gap after re-attach"
            text += d["payload"]["text"]
            chunk = d["payload"]["chunk"]
    final = next(e for e in c.events if e["type"] == "message.completed" and e["payload"]["message"]["role"] == "assistant")
    await c.until(lambda: c.finished(other["task_id"]))
    replayed_seqs = [e["seq"] for e in replayed]
    return {"mode": att["mode"], "replayed_types": sorted({e["type"] for e in replayed}),
            "replay_starts_after_cursor": bool(replayed_seqs) and replayed_seqs[0] == last_seq + 1,
            "replay_contiguous": replayed_seqs == list(range(last_seq + 1, last_seq + 1 + len(replayed_seqs))),
            "partial_at_attach": len(stream_view["text"]) > len(seen_text),
            "reassembled_matches": text == final["payload"]["message"]["content"] == REPLY,
            "deltas_during_detach": missed_while_detached - 3 if missed_while_detached > 3 else 0}


async def crash(c: Client, workdir: str) -> dict:
    """kill -9 the runtime mid-stream; the next call re-activates it; the task is INTERRUPTED with
    a draft and the provider is not called again until the user resumes."""
    hello = await c.hello()
    await configure(c, workdir, delay_ms=30)
    await c.call("Attach", {"scope": "all", "after_seq": 0})
    r = await c.call("SubmitInput", {"command_id": str(uuid.uuid4()), "text": "hello"})
    await asyncio.sleep(2.6)  # past the 2 s draft checkpoint
    last_seq = max(e["seq"] for e in c.events)
    os.kill(hello["pid"], signal.SIGKILL)
    await asyncio.sleep(0.3)
    hello2 = await c.hello()  # D-Bus activation starts a fresh runtime
    att = await c.call("Attach", {"scope": "all", "after_seq": last_seq})
    finished = next((e for e in att["events"] if e["type"] == "task.finished" and e["task_id"] == r["task_id"]), None)
    calls_before_resume = calls(workdir)
    await c.call("Resume", {"command_id": str(uuid.uuid4()), "task_id": r["task_id"]})
    await c.until(lambda: (f := c.finished(r["task_id"])) and f["payload"]["state"] == "COMPLETED", timeout=30)
    return {"new_pid": hello2["pid"] != hello["pid"], "new_epoch": hello2["epoch"] != hello["epoch"],
            "state_after_restart": finished and finished["payload"]["state"],
            "draft_is_prefix": bool(finished and finished["payload"]["draft"]["text"]
                                    and REPLY.startswith(finished["payload"]["draft"]["text"])),
            "calls_before_resume": calls_before_resume, "calls_after_resume": calls(workdir)}


async def duplicate(c: Client, workdir: str) -> dict:
    await c.hello()
    await configure(c, workdir)
    cmd = str(uuid.uuid4())
    a = await c.call("SubmitInput", {"command_id": cmd, "text": "hello"})
    b = await c.call("SubmitInput", {"command_id": cmd, "text": "hello"})
    try:
        await c.call("SubmitInput", {"command_id": cmd, "text": "different"})
        conflict = None
    except RuntimeError as e:
        conflict = str(e).split(":")[0]
    return {"same_task": a["task_id"] == b["task_id"], "second_duplicate": b["duplicate"], "conflict": conflict}


async def lock(c: Client, workdir: str) -> dict:
    await c.hello()
    t0 = time.monotonic()
    second = subprocess.run([sys.executable, "-m", "mei", "serve"], capture_output=True, text=True, timeout=20)
    return {"exit_code": second.returncode, "seconds": round(time.monotonic() - t0, 2),
            "said_why": "another Mei runtime" in second.stderr}


async def setup(c: Client, workdir: str) -> dict:
    await c.hello()
    before = await c.call("SetupStatus")
    steps = {s["id"]: s for s in before["steps"]}
    await configure(c, workdir, reply="OK, ready.")
    test = await c.call("TestProvider")
    revision = (await c.call("GetConfig"))["revision"]
    await c.call("SetupApply", {"step": "offered"})
    await c.call("SetupApply", {"step": "finish", "choices": {"skipped": ["shortcuts"]}})
    after = await c.call("SetupStatus")
    rerun = [(await c.call("SetupApply", {"step": "offered"}))["changed"],
             (await c.call("SetupApply", {"step": "finish", "choices": {"skipped": ["shortcuts"]}}))["changed"]]
    try:
        await c.call("SetupApply", {"step": "voice"})
        bad = ""
    except RuntimeError as e:
        bad = str(e).split(":")[0]
    return {"before": {"completed": before["completed"], "offered": before["offered"],
                       "keyring": steps["service"]["keyring"], "models": steps["models"]["state"]},
            "test": test, "after": {"completed": after["completed"], "skipped": after["skipped"]},
            "rerun_changed": rerun, "revision_unchanged": (await c.call("GetConfig"))["revision"] == revision,
            "bad_step": bad}


async def approver(c: Client, workdir: str) -> dict:
    """Approvals and answers come only from the Shell; this client is a Python script."""
    await c.call("Hello", {"client": {"kind": "test"}, "protocol": [2, 2], "bridge": "/com/andystmc/Mei1/ShellBridge"})
    errors = {}
    for method, args in (("ResolveApproval", {"command_id": "a", "approval_id": "x", "decision": "allow"}),
                         ("AnswerInput", {"command_id": "b", "request_id": "y", "value": "yes"})):
        try:
            await c.call(method, args)
            errors[method] = None
        except RuntimeError as e:
            errors[method] = str(e).split(":")[0]
    grants = await c.call("ListGrants")
    return {"errors": errors, "grants": grants}


async def agent_events(c: Client, workdir: str) -> dict:
    """A task that plans and finishes (meta tools only): its actions reach clients as events."""
    await c.hello()
    await c.call("Attach", {"scope": "all", "after_seq": 0})
    await configure(c, workdir, delay_ms=0, script=[
        {"tool_calls": [{"name": "plan_update", "arguments": {"criteria": [{"text": "it's done"}]}}]},
        {"tool_calls": [{"name": "task_finish", "arguments": {"summary": "Done.", "criteria": [
            {"index": 0, "status": "met"}]}}]}])
    r = await c.call("SubmitInput", {"command_id": str(uuid.uuid4()), "text": "do the thing"})
    await c.until(lambda: c.finished(r["task_id"]))
    snapshot = await c.call("GetConversation", {"conversation_id": r["conversation_id"]})
    task = next(t for t in snapshot["tasks"] if t["id"] == r["task_id"])
    return {"types": sorted({e["type"] for e in c.events if e["task_id"] == r["task_id"]}),
            "outcome": c.finished(r["task_id"])["payload"]["outcome"]["kind"],
            "snapshot_actions": [(a["capability"], a["execution"]) for a in task["actions"]],
            "shown_roles": [m["role"] for m in snapshot["messages"]]}


async def main() -> None:
    scenario, workdir = sys.argv[1], sys.argv[2]
    from mei.ipc import dbus_patch
    dbus_patch.apply()
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    result = await globals()[scenario](Client(bus), workdir)
    print(json.dumps(result))


asyncio.run(main())
