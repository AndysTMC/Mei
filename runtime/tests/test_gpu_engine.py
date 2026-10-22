"""The GPU engine download (decision 0019): every pinned wheel checked before anything is unpacked,
unpacked safely, appearing whole in one step, removable; nothing left behind on failure."""

import hashlib
import io
import stat
import zipfile

import httpx
import pytest

from mei.voice import gpu_engine
from mei.voice.gpu_engine import Wheel
from mei.voice.parts import VoiceError


def wheel(entries: dict[str, bytes], *, link: str = "", mode: int = 0o644) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | mode) << 16
            z.writestr(info, data)
        if link:
            info = zipfile.ZipInfo(link)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def serve(monkeypatch, bodies: dict[str, bytes], *, corrupt: str = "") -> httpx.AsyncClient:
    pinned = tuple(Wheel(f"https://example.org/{name}", hashlib.sha256(body).hexdigest(), len(body))
                   for name, body in bodies.items())
    monkeypatch.setattr(gpu_engine, "wheels", lambda: pinned)
    served = {f"https://example.org/{n}": (b"x" * len(b) if n == corrupt else b) for n, b in bodies.items()}

    def handle(request: httpx.Request) -> httpx.Response:
        body = served.get(str(request.url))
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)
    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


BODIES = {
    "sherpa.whl": wheel({"sherpa_onnx/__init__.py": b"GPU = True\n", "sherpa_onnx/lib/libonnxruntime.so": b"elf"}),
    "cudnn.whl": wheel({"nvidia/cudnn/lib/libcudnn.so.9": b"elf"}, mode=0o755),
}


async def test_the_engine_is_checked_unpacked_and_appears_whole(tmp_path, monkeypatch):
    seen: list[tuple[int, int]] = []
    await gpu_engine.fetch(serve(monkeypatch, BODIES), tmp_path, lambda got, total: seen.append((got, total)))
    site = gpu_engine.site(tmp_path)
    assert gpu_engine.installed(tmp_path)
    assert (site / "sherpa_onnx/__init__.py").read_bytes() == b"GPU = True\n"
    assert (site / "nvidia/cudnn/lib/libcudnn.so.9").stat().st_mode & 0o111  # kept executable
    assert str(site / "nvidia/cudnn/lib") in gpu_engine.library_dirs(tmp_path)
    total = sum(len(b) for b in BODIES.values())
    assert seen[-1] == (total, total) and all(t == total for _, t in seen)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["site"]  # no download or staging left
    gpu_engine.remove(tmp_path)
    assert not gpu_engine.installed(tmp_path) and not site.exists()


async def test_one_wrong_checksum_installs_nothing(tmp_path, monkeypatch):
    with pytest.raises(VoiceError, match="checksum"):
        await gpu_engine.fetch(serve(monkeypatch, BODIES, corrupt="cudnn.whl"), tmp_path)
    assert not gpu_engine.installed(tmp_path) and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad", [{"../escape.so": b"x"}, {"/etc/cron.d/x": b"x"}, "link"])
def test_a_wheel_reaching_outside_or_holding_links_is_refused(tmp_path, bad):
    body = wheel({"ok.py": b""}, link="sherpa_onnx/evil") if bad == "link" else wheel(bad)
    (tmp_path / "w.whl").write_bytes(body)
    into = tmp_path / "into"
    into.mkdir()
    with pytest.raises(VoiceError, match="shouldn't"):
        gpu_engine.unpack(tmp_path / "w.whl", into)
    assert not (tmp_path / "escape.so").exists()


def test_pinned_wheels_are_https_and_sized():
    for w in (*gpu_engine.SHERPA_CUDA.values(), *gpu_engine.NVIDIA):
        assert w.url.startswith("https://") and len(w.sha256) == 64 and w.size > 1_000_000
    assert 1_800_000_000 < sum(w.size for w in gpu_engine.wheels("cp312")) < 2_000_000_000
    with pytest.raises(VoiceError, match="no GPU build"):
        gpu_engine.wheels("cp39")
