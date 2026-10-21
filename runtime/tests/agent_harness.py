"""A fake world for agent-loop tests: a temporary home, the real file capabilities, a scripted
model, and an engine that records every event. Shared by the loop tests and the evals."""

import asyncio
import datetime
import json
import os
from pathlib import Path

from mei.capabilities.base import Env
from mei.capabilities.catalog import default_registry
from mei.core.engine import Engine
from mei.core.states import TERMINAL, TaskState
from mei.protocol import (AnswerInputArgs, Config, Privacy, ProviderConfig, ProviderSettings, ResolveApprovalArgs,
                          SubmitInputArgs, UpdateConfigArgs, Approvals)
from mei.providers.fake import FakeProvider
from mei.store import agent, repo
from mei.store.db import Store

S = TaskState
WAITING = {S.WAITING_APPROVAL, S.WAITING_INPUT, S.INTERRUPTED, *TERMINAL}


class Recorder:
    def __init__(self) -> None:
        self.events = []
        self.deltas = []

    def publish(self, events) -> None:
        self.events.extend(events)

    def publish_ephemeral(self, event) -> None:
        self.deltas.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


class TextExtractor:
    """Stands in for pdftotext: the test's "PDFs" are text files."""

    async def pdf_text(self, path: Path, max_chars: int) -> str:
        return path.read_text()[:max_chars]


async def fake_factory(cfg: ProviderConfig):
    return FakeProvider(cfg.options)


def make_world(tmp: Path) -> Env:
    home = tmp / "home"
    dirs = {"DOWNLOAD": home / "Downloads", "DOCUMENTS": home / "Documents", "MUSIC": home / "Music",
            "PICTURES": home / "Pictures"}
    for d in dirs.values():
        d.mkdir(parents=True)
    return Env(home=home, data_dir=tmp / "mei", data_home=home / ".local/share", user_dirs=dirs,
               extractor=TextExtractor())


def put(env: Env, path: str, text: str = "x", *, days_old: float = 0) -> Path:
    p = env.path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if days_old:
        when = datetime.datetime.now().timestamp() - days_old * 86400
        os.utime(p, (when, when))
    return p


class Harness:
    def __init__(self, tmp: Path, *, script=None, scripts=None, preset="balanced", cloud=False, cloud_files="pointed",
                 env: Env | None = None, boundary=lambda _n: None, **options) -> None:
        self.tmp = tmp
        self.env = env or make_world(tmp)
        self.log = tmp / "calls.jsonl"
        self.rec = Recorder()
        self.options = {"delay_ms": 0, "chunk_chars": 50, "call_log": str(self.log), "cloud": cloud,
                        "script": script or [], "scripts": scripts or {}, **options}
        self.engine = Engine(Store(tmp / "mei"), self.rec, fake_factory, registry=default_registry(), env=self.env,
                             boundary=boundary)
        revision = self.engine.get_config()["revision"]
        self.engine.update_config(UpdateConfigArgs(revision, Config(
            active="fake", providers={"fake": ProviderSettings(options=self.options)},
            privacy=Privacy(cloud_files=cloud_files), approvals=Approvals(preset=preset))))
        self._n = 0

    @property
    def store(self) -> Store:
        return self.engine.store

    def _id(self) -> str:
        self._n += 1
        return f"cmd-{self._n}"

    def submit(self, text: str, conversation_id: str | None = None) -> dict:
        return self.engine.submit_input(SubmitInputArgs(command_id=self._id(), text=text,
                                                        conversation_id=conversation_id))

    async def until(self, task_id: str, states=WAITING, timeout: float = 10.0) -> str:
        async with asyncio.timeout(timeout):
            while True:
                state = repo.get_task(self.store, task_id)["state"]
                if state in states and task_id not in self.engine._runners:
                    return state
                await asyncio.sleep(0.01)

    def approval(self, task_id: str):
        return agent.pending_approval(self.store, task_id)

    def approve(self, task_id: str, scope: str = "once", decision: str = "allow") -> dict:
        approval = self.approval(task_id)
        return self.engine.resolve_approval(ResolveApprovalArgs(command_id=self._id(), approval_id=approval["id"],
                                                                decision=decision, scope=scope), decided_by=":1.1")

    def answer(self, task_id: str, value) -> dict:
        request = agent.pending_input(self.store, task_id)
        return self.engine.answer_input(AnswerInputArgs(command_id=self._id(), request_id=request["id"], value=value))

    def task(self, task_id: str) -> dict:
        return repo.task_dict(repo.get_task(self.store, task_id))

    def actions(self, task_id: str) -> list:
        return agent.task_actions(self.store, task_id)

    def requests(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


def call(tool: str, /, **arguments) -> dict:
    return {"name": tool, "arguments": arguments}


def turn(*calls: dict, text: str = "") -> dict:
    return {"text": text, "tool_calls": list(calls)}


def assert_provider_valid(turns: list[dict]) -> None:
    """Every assistant turn with tool calls is followed at once by exactly one result per call."""
    i = 0
    while i < len(turns):
        t = turns[i]
        if t["role"] == "tool":
            raise AssertionError(f"tool result without its call at {i}: {turns}")
        if t["role"] == "assistant" and t.get("tool_calls"):
            n = len(t["tool_calls"])
            results = turns[i + 1:i + 1 + n]
            assert len(results) == n and all(r["role"] == "tool" for r in results), f"unpaired calls at {i}: {turns}"
            i += 1 + n
            continue
        i += 1
