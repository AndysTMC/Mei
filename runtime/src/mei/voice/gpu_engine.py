"""The GPU part of the voice engine (decision 0019): sherpa-onnx's CUDA 12 build, from its author's
wheel repository, and NVIDIA's CUDA runtime, cuBLAS, cuDNN and NVRTC from PyPI. It is an optional
download (~1.9 GB, ~2.9 GB unpacked), offered only where there is an NVIDIA GPU, and removable.

Every wheel is pinned by URL, size and sha256 and checked before anything is unpacked. Wheels are
zip files: they are unpacked member by member, refusing absolute paths, `..`, and links, into a
staging folder that becomes `site/` in one rename. Only the GPU speaker process puts `site/` on
its import path; the rest of Mei never imports from it.
"""

import os
import shutil
import stat
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from mei.paths import data_dir

from .download import download_checked
from .parts import VoiceError

VERSION = "1.13.8+cuda12.cudnn9.onnxruntime1.28.2"
MAX_UNPACKED = 4 << 30  # the pinned wheels unpack to ~2.9 GB; anything far beyond is refused
PART = "graphics card engine"
_HF = "https://huggingface.co/csukuangfj2/sherpa-onnx-wheels/resolve/main/cuda/1.13.8/"
_PYPI = "https://files.pythonhosted.org/packages/"
NVIDIA_LIBS = ("cuda_runtime", "cudnn", "cublas", "cuda_nvrtc")


@dataclass(frozen=True)
class Wheel:
    url: str
    sha256: str
    size: int
    part: str = PART


SHERPA_CUDA = {
    f"cp3{minor}": Wheel(f"{_HF}sherpa_onnx-{VERSION}-cp3{minor}-cp3{minor}-linux_x86_64.whl", sha256, size)
    for minor, sha256, size in (
        (12, "5dc95055b512babadd9798a5efcdd0a29e3d17d6a41e668198c02667a541779c", 443_046_368),
        (13, "34e74ece11e2fcf6b801e2350cfc9175bd303b121e9cba24dcb0b9e03e1cd750", 443_045_729),
        (14, "40685af5c19bd016d9a72d27c1f041015905eeffd22b1f1beaf7402d07fbf0ff", 443_048_018))}
NVIDIA = (
    Wheel(_PYPI + "65/e4/c5a205d48ff00ed8b27882bb45d338d8138e976c76385f328a326bbfaeda/"
          "nvidia_cudnn_cu12-9.27.0.42-py3-none-manylinux_2_27_x86_64.whl",
          "0a4aa3a7d2264256506c6857fc41fc0c499982f78d70195b1cfcc9055c1957cd", 766_178_381),
    Wheel(_PYPI + "cb/c0/0a517bfe63ccd3b92eb254d264e28fca3c7cab75d07daea315250fb1bf73/"
          "nvidia_cublas_cu12-12.9.2.10-py3-none-manylinux_2_27_x86_64.whl",
          "e4f53a8ca8c5d6e8c492d0d0a3d565ecb59a751b19cfdaa4f6da0ab2104c1702", 581_240_110),
    Wheel(_PYPI + "bc/46/a92db19b8309581092a3add7e6fceb4c301a3fd233969856a8cbf042cd3c/"
          "nvidia_cuda_runtime_cu12-12.9.79-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
          "25bba2dfb01d48a9b59ca474a1ac43c6ebf7011f1b0b8cc44f54eb6ac48a96c3", 3_493_179),
    Wheel(_PYPI + "b8/85/e4af82cc9202023862090bfca4ea827d533329e925c758f0cde964cb54b7/"
          "nvidia_cuda_nvrtc_cu12-12.9.86-py3-none-manylinux2010_x86_64.manylinux_2_12_x86_64.whl",
          "210cf05005a447e29214e9ce50851e83fc5f4358df8b453155d5e1918094dcb4", 89_568_129),
)


def gpu_present() -> bool:
    return os.path.exists("/dev/nvidiactl")


def wheels(python: str = f"cp{sys.version_info.major}{sys.version_info.minor}") -> tuple[Wheel, ...]:
    sherpa = SHERPA_CUDA.get(python)
    if sherpa is None or os.uname().machine != "x86_64":
        raise VoiceError(PART, f"there's no GPU build for this computer ({python}, {os.uname().machine})")
    return (sherpa, *NVIDIA)


def size() -> int:
    try:
        return sum(w.size for w in wheels())
    except VoiceError:
        return 0


def engine_dir() -> Path:
    """MEI_GPU_ENGINE overrides it (tests and development)."""
    override = os.environ.get("MEI_GPU_ENGINE", "")
    return Path(override) if os.path.isabs(override) else data_dir() / "voice" / "gpu-engine"


def site(root: Path) -> Path:
    return root / "site"


def installed(root: Path) -> bool:
    stamp = site(root) / ".mei-gpu-engine"
    return stamp.is_file() and stamp.read_text().strip() == VERSION


def library_dirs(root: Path) -> list[str]:
    return [str(site(root) / "nvidia" / name / "lib") for name in NVIDIA_LIBS]


async def fetch(client: httpx.AsyncClient, root: Path, progress: Callable[[int, int], None] | None = None) -> None:
    if installed(root):
        return
    pinned = wheels()
    total, done = sum(w.size for w in pinned), 0
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging, part = root / ".site.unpack", root / ".wheel.download"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    try:
        for wheel in pinned:
            await download_checked(client, wheel, part,
                                   None if progress is None else lambda got, _t, base=done: progress(base + got, total))
            unpack(part, staging)
            done += wheel.size
        (staging / ".mei-gpu-engine").write_text(VERSION + "\n")
        remove(root)
        staging.replace(site(root))
    finally:
        part.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)


def remove(root: Path) -> None:
    shutil.rmtree(site(root), ignore_errors=True)


def unpack(wheel: Path, into: Path) -> None:
    """Regular files only, each inside `into`; the whole set no bigger than MAX_UNPACKED."""
    try:
        with zipfile.ZipFile(wheel) as z:
            members = z.infolist()
            if sum(m.file_size for m in members) > MAX_UNPACKED:
                raise VoiceError(PART, "a wheel unpacks to more than it should")
            for m in members:
                if m.is_dir():
                    continue
                kind = stat.S_IFMT(m.external_attr >> 16)
                target = (into / m.filename).resolve()
                if (kind and kind != stat.S_IFREG) or Path(m.filename).is_absolute() or ".." in Path(m.filename).parts \
                        or not target.is_relative_to(into.resolve()):
                    raise VoiceError(PART, f"a wheel holds something it shouldn't ({m.filename!r})")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                if (m.external_attr >> 16) & 0o111:
                    target.chmod(0o755)
    except (zipfile.BadZipFile, OSError) as e:
        raise VoiceError(PART, f"a wheel couldn't be unpacked: {e}") from None
