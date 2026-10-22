"""Downloading voice models: checked against the pinned size and hash before unpacking, unpacked
safely, appearing in one step, and nothing left behind on failure."""

import hashlib
import io
import tarfile
from dataclasses import replace

import httpx
import pytest

from mei.voice import download
from mei.voice.models import KROKO, SILERO, Model, have
from mei.voice.parts import VoiceError


def archive(entries: dict[str, bytes], *, link: tuple[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo(link[0])
            info.type, info.linkname = tarfile.SYMTYPE, link[1]
            tar.addfile(info)
    return buf.getvalue()


def pinned(model: Model, body: bytes) -> Model:
    return replace(model, sha256=hashlib.sha256(body).hexdigest(), size=len(body))


def client(routes: dict[str, httpx.Response]) -> httpx.AsyncClient:
    def handle(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


async def test_an_archive_is_checked_unpacked_and_appears_whole(tmp_path):
    body = archive({f"{KROKO.folder}/tokens.txt": b"a b c", f"{KROKO.folder}/encoder.onnx": b"x" * 100})
    model = pinned(KROKO, body)
    cdn = "https://objects.example.com/kroko"
    async with client({model.url: httpx.Response(302, headers={"location": cdn}), cdn: httpx.Response(200, content=body)}) as c:
        seen = []
        await download.fetch(c, model, tmp_path, lambda got, total: seen.append((got, total)))
    assert have(model, tmp_path) and (tmp_path / KROKO.folder / "tokens.txt").read_bytes() == b"a b c"
    assert seen[-1] == (len(body), len(body)) and sorted(p.name for p in tmp_path.iterdir()) == [KROKO.folder]


async def test_a_wrong_checksum_installs_nothing(tmp_path):
    body = archive({f"{KROKO.folder}/tokens.txt": b"tampered"})
    model = replace(pinned(KROKO, body), sha256="0" * 64)
    async with client({model.url: httpx.Response(200, content=body)}) as c:
        with pytest.raises(VoiceError, match="checksum"):
            await download.fetch(c, model, tmp_path)
    assert list(tmp_path.iterdir()) == []


async def test_an_archive_reaching_outside_is_refused(tmp_path):
    for body in (archive({f"{KROKO.folder}/ok": b"1", "../escaped": b"2"}),
                 archive({f"{KROKO.folder}/ok": b"1"}, link=(f"{KROKO.folder}/link", "/etc/passwd"))):
        model = pinned(KROKO, body)
        async with client({model.url: httpx.Response(200, content=body)}) as c:
            with pytest.raises(VoiceError, match="couldn't be unpacked"):
                await download.fetch(c, model, tmp_path)
        assert not (tmp_path.parent / "escaped").exists() and not have(model, tmp_path)


async def test_single_files_and_https_only(tmp_path):
    body = b"onnx bytes"
    model = pinned(SILERO, body)
    async with client({model.url: httpx.Response(302, headers={"location": "http://plain.example.com/x"})}) as c:
        with pytest.raises(VoiceError, match="isn't https"):
            await download.fetch(c, model, tmp_path)
    async with client({model.url: httpx.Response(200, content=body)}) as c:
        await download.fetch(c, model, tmp_path)
        await download.fetch(c, model, tmp_path)  # already there: nothing to do
    assert (tmp_path / SILERO.folder).read_bytes() == body
