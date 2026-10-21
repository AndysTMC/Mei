"""How a run ends when it doesn't end normally (§8.7, §15): stopped by the person, by a shutdown,
or by a failure. Whatever the model streamed so far is kept as the turn's draft."""

import json
from collections.abc import Callable
from dataclasses import dataclass

from mei.core.states import TERMINAL, Disposition, Execution, TaskState
from mei.protocol import Envelope
from mei.store import agent, repo
from mei.store.db import Store, Tx

from . import ledger
from .streaming import Stream

E, S = Execution, TaskState


@dataclass
class InFlight:
    """What a run is in the middle of: a model call's stream, or a started action."""

    stream: Stream | None = None
    action_id: str | None = None


def stopped(store: Store, publish: Callable[[list[Envelope]], None], task_id: str, flight: InFlight) -> None:
    """Cancelled: by the person (CANCEL_REQUESTED is stored first) or by a shutdown."""
    with store.tx() as tx:
        state = S(repo.get_task(tx, task_id)["state"])
        if state in TERMINAL:
            return
        draft = _draft(tx, flight)
        if state == S.CANCEL_REQUESTED:
            running = agent.get_action(tx, flight.action_id) if flight.action_id else None
            if running is not None and E(running["execution"]) == E.STARTED:
                task = repo.task_dict(repo.get_task(tx, task_id))
                mutating = (json.loads(running["effects"] or "{}")).get("mutates", "no") != "no"
                ledger.finish_action(tx, task, running, E.CANCELLED, "Stopped by the person before it finished.",
                                     is_error=True, disposition=Disposition.UNKNOWN if mutating else Disposition.NONE)
            ledger.cancel_now(tx, task_id, draft=draft)
        else:
            # A shutdown. An action in flight stays STARTED; recovery treats it as in doubt (§15).
            final = repo.set_task_state(tx, task_id, S.INTERRUPTED, error="Mei was restarting")
            repo.finished_event(tx, final, draft=draft)
    publish(tx.events)


def failed(store: Store, publish: Callable[[list[Envelope]], None], task_id: str, flight: InFlight,
           to: TaskState, error: str) -> None:
    with store.tx() as tx:
        state = S(repo.get_task(tx, task_id)["state"])
        if state in TERMINAL:
            return
        draft = _draft(tx, flight)
        if state == S.CANCEL_REQUESTED:
            ledger.cancel_now(tx, task_id, draft=draft)  # the person's stop wins over a failure
        else:
            final = repo.set_task_state(tx, task_id, to, error=error)
            repo.finished_event(tx, final, draft=draft)
    publish(tx.events)


def _draft(tx: Tx, flight: InFlight) -> dict | None:
    stream = flight.stream
    if stream is None:
        return None
    tx.execute("UPDATE turns SET draft_text = ?, draft_thinking = ?, draft_chunk = ? WHERE id = ?",
               (stream.text, stream.thinking, stream.chunk, stream.turn_id))
    repo.finish_turn(tx, stream.turn_id, "lost")
    return {"text": stream.text, "thinking": stream.thinking}
