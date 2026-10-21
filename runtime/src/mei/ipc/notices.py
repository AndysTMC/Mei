"""Desktop notifications from the runtime itself, for when no Shell is attached (§18.4).

While the Shell extension is attached it notifies, since it knows whether the popup already shows
the conversation. When it isn't (disabled, or Mei running without GNOME Shell's extension), a task
that finishes or needs the person would otherwise go unseen. Notifications name the conversation,
not its content: they can show on the lock screen.
"""

import asyncio
import logging
from collections.abc import Callable

from mei.capabilities.base import Notifier
from mei.protocol import Envelope

log = logging.getLogger("mei.ipc")
_FINISHED = {"COMPLETED": "Mei finished", "FAILED": "Mei couldn't finish", "BLOCKED": "Mei got stuck"}


class Notices:
    def __init__(self, notifier: Notifier | None, title_of: Callable[[str], str]) -> None:
        self._notifier = notifier
        self._title_of = title_of
        self._pending: set[asyncio.Task] = set()

    def on_events(self, events: list[Envelope], *, shell_attached: bool) -> None:
        if shell_attached or self._notifier is None:
            return
        for event in events:
            heading = None
            if event.type == "task.finished":
                heading = _FINISHED.get(event.payload.get("state", ""))
            elif event.type == "approval.requested":
                heading = "Mei needs your OK"
            elif event.type == "input.requested":
                heading = "Mei has a question"
            if heading and event.conversation_id:
                self._send(heading, self._title_of(event.conversation_id))

    def _send(self, title: str, body: str) -> None:
        async def send() -> None:
            try:
                await self._notifier.notify(title, body)
            except Exception as e:  # the task's state is stored either way; only the nudge is lost
                log.warning("couldn't show the notification %r: %s", title, e)

        task = asyncio.get_running_loop().create_task(send())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
