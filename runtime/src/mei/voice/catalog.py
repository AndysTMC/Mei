"""The voice models on this computer (setup and Settings): which there are, which these settings need,
fetching them in the background with progress, and deleting them. With an NVIDIA GPU, the GPU engine
too: never needed, offered when the natural voice may use the GPU.
"""

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from mei.protocol import ProtocolError, VoiceSettings

from . import download, engines, gpu_engine
from .models import CATALOG, have
from .parts import VoiceError

log = logging.getLogger("mei.voice")
GPU_ENGINE = "gpu-engine"  # the GPU engine's id among the models (it is downloaded the same way)


class ModelStore:
    def __init__(self, root: Path, client: httpx.AsyncClient | None, changed: Callable[[], Awaitable[None]]) -> None:
        """`changed()` runs after models arrive or go, so voice starts (or carries on) with them."""
        self._root = root
        self._client = client
        self._changed = changed
        self._downloads: dict[str, dict] = {}  # model id → progress, while (and after) fetching
        self._fetching: asyncio.Task | None = None

    def listing(self, s: VoiceSettings) -> dict:
        needed = {m.folder for m in engines.needed(s)}
        gpu = gpu_engine.gpu_present()
        rows = [{"id": key, "part": m.part, "size": m.size, "have": have(m, self._root), "needed": m.folder in needed,
                 "offered": False, **self._downloads.get(key, {})} for key, m in CATALOG.items()]
        if gpu:
            rows.append({"id": GPU_ENGINE, "part": gpu_engine.PART, "size": gpu_engine.size(),
                         "have": gpu_engine.installed(gpu_engine.engine_dir()), "needed": False,
                         "offered": s.tts == "kokoro" and s.device != "cpu", **self._downloads.get(GPU_ENGINE, {})})
        return {"models": rows, "gpu": gpu, "downloading": self.busy()}

    def busy(self) -> bool:
        return self._fetching is not None and not self._fetching.done()

    def check(self, ids: list[str]) -> None:
        unknown = [i for i in ids if i not in CATALOG and i != GPU_ENGINE]
        if unknown:
            raise ProtocolError("InvalidArgument", f"no voice model {unknown[0]!r}")
        if self.busy():
            raise ProtocolError("Busy", "a download is running")

    def download(self, ids: list[str]) -> None:
        self.check(ids)
        if self._client is None:
            raise ProtocolError("Unavailable", "downloads aren't available here")
        self._fetching = asyncio.ensure_future(self._fetch(ids))

    async def remove(self, ids: list[str]) -> None:
        self.check(ids)
        for key in ids:
            self._downloads.pop(key, None)
            if key == GPU_ENGINE:
                gpu_engine.remove(gpu_engine.engine_dir())
                continue
            path = self._root / CATALOG[key].folder
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        await self._changed()

    async def _fetch(self, ids: list[str]) -> None:
        for key in ids:
            total = gpu_engine.size() if key == GPU_ENGINE else CATALOG[key].size
            progress = self._downloads[key] = {"got": 0, "total": total, "error": ""}

            def report(got: int, total: int, progress: dict = progress) -> None:
                progress.update(got=got, total=total)
            try:
                if key == GPU_ENGINE:
                    await gpu_engine.fetch(self._client, gpu_engine.engine_dir(), report)
                else:
                    await download.fetch(self._client, CATALOG[key], self._root, report)
            except VoiceError as e:  # this one failed: say so, and go on with the rest
                progress["error"] = e.message
            except Exception as e:  # noqa: BLE001  a disk or network failure: say it, don't crash the runtime
                log.exception("downloading %s failed", key)
                progress["error"] = str(e)[:200]
        await self._changed()  # voice starts with what arrived, or says what's still missing
