"""Fetching the local voice models (decision 0017). The core downloads; the voice worker never has
the network. Each download is checked against its pinned size and sha256 before anything is
unpacked, archives are unpacked with tarfile's "data" filter (no absolute paths, no links out, no
devices), and the result appears under its final name in one rename, so a half-finished model is
never mistaken for a whole one.
"""

import hashlib
import logging
import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .models import Model, have
from .parts import VoiceError

log = logging.getLogger("mei.voice")
MAX_REDIRECTS = 5
Progress = Callable[[int, int], None]  # (bytes so far, total)


class Pinned(Protocol):
    """A file at a fixed https URL, with its exact size and sha256."""

    part: str  # what it is, as people read it
    url: str
    sha256: str
    size: int


async def fetch(client: httpx.AsyncClient, model: Model, root: Path, progress: Progress | None = None) -> None:
    if have(model, root):
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    part = root / f".{model.folder}.download"
    try:
        await download_checked(client, model, part, progress)
        if model.archive:
            _unpack(model, part, root)
        else:
            part.replace(root / model.folder)
    finally:
        part.unlink(missing_ok=True)
        shutil.rmtree(root / f".{model.folder}.unpack", ignore_errors=True)
    log.info("downloaded %s (%s)", model.part, model.folder)


async def download_checked(client: httpx.AsyncClient, model: Pinned, part: Path, progress: Progress | None) -> None:
    """Download to `part`, refusing anything but https, and raise unless size and sha256 match."""
    url = model.url
    for _ in range(MAX_REDIRECTS + 1):
        if urlsplit(url).scheme != "https":
            raise VoiceError(model.part, f"refused a download that isn't https ({urlsplit(url).netloc})")
        async with client.stream("GET", url, follow_redirects=False, timeout=httpx.Timeout(30, read=60)) as r:
            if r.is_redirect:
                url = str(r.url.join(r.headers["location"]))
                continue
            if r.status_code != 200:
                raise VoiceError(model.part, f"the download failed (HTTP {r.status_code})")
            digest, got = hashlib.sha256(), 0
            with open(part, "wb") as out:
                async for chunk in r.aiter_bytes(1 << 20):
                    got += len(chunk)
                    if got > model.size:
                        raise VoiceError(model.part, "the download is bigger than it should be")
                    digest.update(chunk)
                    out.write(chunk)
                    if progress is not None:
                        progress(got, model.size)
            if got != model.size or digest.hexdigest() != model.sha256:
                raise VoiceError(model.part, "the download doesn't match its checksum; nothing was installed")
            return
    raise VoiceError(model.part, "too many redirects")


def _unpack(model: Model, archive: Path, root: Path) -> None:
    staging = root / f".{model.folder}.unpack"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    try:
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(staging, filter="data")
    except (tarfile.TarError, OSError) as e:
        raise VoiceError(model.part, f"the archive couldn't be unpacked: {e}") from None
    unpacked = staging / model.folder
    if not unpacked.is_dir():
        raise VoiceError(model.part, f"the archive doesn't hold {model.folder}")
    unpacked.replace(root / model.folder)
