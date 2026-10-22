"""The voice worker's jail (§5.4, spike 0c): models read-only, no network, no session bus, none of
the person's files, and of the runtime directory only PipeWire's socket. With the GPU in use, the
NVIDIA device nodes too (they reach the GPU, not the network or files).
"""

import os
import sys
from pathlib import Path

import mei

BWRAP = "/usr/bin/bwrap"
NVIDIA_DEVICES = ("/dev/nvidiactl", "/dev/nvidia0", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools")


def available() -> bool:
    return os.access(BWRAP, os.X_OK)


def worker_argv(models: Path, *, gpu: bool = False, readable: tuple[Path, ...] = (), writable: tuple[Path, ...] = ()) -> list[str]:
    """The command that starts the worker in its jail. `readable`/`writable`: extra paths, for
    tests and setup checks that play or capture audio files."""
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    interpreter_root = Path(sys.base_prefix).parent  # uv keeps Pythons side by side here
    code = Path(mei.__file__).resolve().parent.parent  # site-packages, or src/ for a development checkout
    args = [BWRAP, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/nonexistent", "--setenv", "LANG", "C.UTF-8",
            "--setenv", "XDG_RUNTIME_DIR", runtime, "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--setenv", "MEI_PERSON_HOME", str(Path.home()),  # only so diagnose() can say it can't see it
            "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
            "--ro-bind-try", "/etc/pipewire", "/etc/pipewire", "--ro-bind-try", "/etc/alsa", "/etc/alsa",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind", str(interpreter_root), str(interpreter_root), "--ro-bind", sys.prefix, sys.prefix]
    if not code.is_relative_to(sys.prefix):
        args += ["--ro-bind", str(code), str(code)]
    args += ["--ro-bind", str(models), str(models), "--dir", runtime,
             "--bind-try", f"{runtime}/pipewire-0", f"{runtime}/pipewire-0"]
    for path in readable:
        args += ["--ro-bind", str(path), str(path)]
    for path in writable:
        args += ["--bind", str(path), str(path)]
    if gpu:
        for device in NVIDIA_DEVICES:
            if os.path.exists(device):
                args += ["--dev-bind", device, device]
        libs = _cuda_libraries()
        if libs:
            args += ["--setenv", "LD_LIBRARY_PATH", ":".join(libs)]
    return args + [sys.executable, "-m", "mei.voice.worker"]


def _cuda_libraries() -> list[str]:
    """CUDA runtime and cuDNN from NVIDIA's pip packages, when the GPU build installed them (decision
    0017): the system's CUDA runtime can be too old for the engine."""
    root = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "nvidia"
    return [str(root / name / "lib") for name in ("cuda_runtime", "cudnn", "cublas", "cuda_nvrtc")
            if (root / name / "lib").is_dir()]
