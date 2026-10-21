"""Drives the real engine against a world: submit a request, wait for the task to settle, answer
cards and questions. Shared by the loop tests (with the scripted model) and the evals."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from mei.capabilities.base import Env
from mei.capabilities.catalog import default_registry
from mei.core.engine import Engine
from mei.core.states import TERMINAL, TaskState
from mei.protocol import (AnswerInputArgs, Approvals, Attachment, Config, Privacy, ProviderConfig, ProviderSettings,
                          ResolveApprovalArgs, SubmitInputArgs, UpdateConfigArgs)
from mei.providers.base import Provider
from mei.store import agent, repo
from mei.store.db import Store

S = TaskState
SETTLED = {S.WAITING_APPROVAL, S.WAITING_INPUT, S.INTERRUPTED, *TERMINAL}
ProviderFactory = Callable[[ProviderConfig], Awaitable[Provider]]


class Recorder:
    """A publisher that keeps every event."""

    def __init__(self) -> None:
        self.events = []
        self.deltas = []

    def publish(self, events) -> None:
        self.events.extend(events)

    def publish_ephemeral(self, event) -> None:
        self.deltas.append(event)

    def types(self) -> list[str]:
        return [e.type for e in self.events]


class Driver:
    def __init__(self, data_dir: Path, env: Env, factory: ProviderFactory, provider: ProviderConfig, *,
                 preset: str = "balanced", cloud_files: str = "pointed",
                 boundary: Callable[[str], None] = lambda _n: None) -> None:
        self.env = env
        self.rec = Recorder()
        self.engine = Engine(Store(data_dir), self.rec, factory, registry=default_registry(), env=env,
                             boundary=boundary)
        settings = ProviderSettings(model=provider.model, url=provider.url, options=provider.options)
        revision = self.engine.get_config()["revision"]
        self.engine.update_config(UpdateConfigArgs(revision, Config(
            active=provider.id, providers={provider.id: settings},
            privacy=Privacy(cloud_files=cloud_files), approvals=Approvals(preset=preset))))
        self._n = 0

    @property
    def store(self) -> Store:
        return self.engine.store

    def _id(self) -> str:
        self._n += 1
        return f"cmd-{self._n}"

    def submit(self, text: str, conversation_id: str | None = None, attachment: Attachment | None = None) -> dict:
        return self.engine.submit_input(SubmitInputArgs(command_id=self._id(), text=text,
                                                        conversation_id=conversation_id, attachment=attachment))

    async def until(self, task_id: str, states=SETTLED, timeout: float = 10.0) -> str:
        """Wait until the task is in one of `states` and its runner has finished."""
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


# ── Scripts for the scripted model (providers/fake.py) ──────────────────────


def call(tool: str, /, **arguments) -> dict:
    return {"name": tool, "arguments": arguments}


def turn(*calls: dict, text: str = "") -> dict:
    return {"text": text, "tool_calls": list(calls)}
