"""While Mei works on a spoken request (decision 0029): a soft tone if the answer takes more than about
a second, so the person knows they were heard, then a few words at 10, 100 and 1,000 seconds, until
Mei answers or asks. Each new spell of thinking (after an approval, say) starts the series again.
"""

import asyncio
from collections.abc import Callable

TONE_AFTER_S = 1.0
CHECK_INS = ((10.0, "Still on it."),
             (100.0, "This is taking a while. I'm still working on it."),
             (1000.0, "Still working on it. This one is long."))


class Waiting:
    def __init__(self, cue: Callable[[str], None], tone_after_s: float = TONE_AFTER_S,
                 check_ins: tuple[tuple[float, str], ...] = CHECK_INS) -> None:
        """`cue(text)` plays the tone ("") or says `text`, outside any reply."""
        self._cue = cue
        self._tone_after_s = tone_after_s
        self._check_ins = check_ins
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        self.stop()
        self._task = asyncio.ensure_future(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        began = loop.time()
        await asyncio.sleep(self._tone_after_s)
        self._cue("")
        for at, text in self._check_ins:
            await asyncio.sleep(max(0.0, began + at - loop.time()))
            self._cue(text)
