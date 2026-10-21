"""Running a command for a task (§13.6): in a bubblewrap jail inside a systemd scope, or (for
`shell.run_host`) in a scope alone.

The jail sees /usr and /etc read-only, a private /tmp, the task's workspace, and only the folders
the action names (each read-only unless marked writable). There is no network unless asked for, no
home folder, no session bus, and a cleared environment. The scope caps memory, CPU, and process
count, and stopping it kills everything the command started; the jail's own PID namespace does the
same if Mei dies. Output keeps its head and tail in memory; all of it is written to a spill file.
"""

import asyncio
import os
import time
import uuid
from pathlib import Path

from mei.capabilities.base import RunResult, RunSpec

BWRAP = "/usr/bin/bwrap"
SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
HEAD_BYTES = 12 * 1024
TAIL_BYTES = 12 * 1024
SPILL_MAX = 20 * 1024 * 1024
LIMITS = ("MemoryMax=2G", "CPUQuota=200%", "TasksMax=512")
_SECRETISH = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "APIKEY", "CREDENTIAL", "_KEY")


class Sandbox:
    """The `Env.runner` port. `available()` says whether jailed commands can run here at all."""

    def __init__(self, bwrap: str = BWRAP, systemd_run: str = SYSTEMD_RUN) -> None:
        self._bwrap = bwrap if os.access(bwrap, os.X_OK) else None
        self._scope = systemd_run if os.access(systemd_run, os.X_OK) and os.environ.get("XDG_RUNTIME_DIR") else None

    def available(self, sandboxed: bool = True) -> bool:
        return self._bwrap is not None or not sandboxed

    async def run(self, spec: RunSpec) -> RunResult:
        unit = f"mei-run-{uuid.uuid4().hex[:12]}"
        argv = self._argv(spec, unit)
        spec.spill.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            cwd=str(spec.cwd) if not spec.sandboxed else "/", env=_host_env() if not spec.sandboxed else _minimal_env(),
            start_new_session=True)
        result = RunResult(None, b"", b"", 0, 0.0, spilled=spec.spill)
        try:
            await asyncio.wait_for(self._collect(proc, spec.spill, result), spec.timeout_s)
            result.exit_code = await proc.wait()
        except TimeoutError:
            result.timed_out = True
            await self._stop(proc, unit)
        except asyncio.CancelledError:
            await self._stop(proc, unit)
            raise
        result.seconds = time.monotonic() - started
        return result

    def _argv(self, spec: RunSpec, unit: str) -> list[str]:
        inner = ["/bin/sh", "-c", spec.command]
        if spec.sandboxed:
            if self._bwrap is None:
                raise RuntimeError("bubblewrap isn't installed")
            inner = [self._bwrap, *jail_args(spec), *inner]
        if self._scope is None:
            return inner  # no user manager: a process group stands in for the scope
        return [self._scope, "--user", "--scope", "--quiet", "--collect", f"--unit={unit}",
                *(f"--property={p}" for p in LIMITS), "--", *inner]

    @staticmethod
    async def _collect(proc: asyncio.subprocess.Process, spill: Path, result: RunResult) -> None:
        with open(spill, "wb") as out:
            os.chmod(spill, 0o600)
            while chunk := await proc.stdout.read(65536):
                if result.total_bytes < SPILL_MAX:
                    out.write(chunk[:SPILL_MAX - result.total_bytes])
                if len(result.head) < HEAD_BYTES:
                    result.head += chunk[:HEAD_BYTES - len(result.head)]
                result.tail = (result.tail + chunk)[-TAIL_BYTES:]
                result.total_bytes += len(chunk)
        if result.total_bytes > SPILL_MAX:
            result.notes.append(f"only the first {SPILL_MAX // (1024 * 1024)} MB of output were kept")

    async def _stop(self, proc: asyncio.subprocess.Process, unit: str) -> None:
        """Kill everything the command started: the whole scope, and the process group as well."""
        if self._scope is not None and os.access(SYSTEMCTL, os.X_OK):
            stop = await asyncio.create_subprocess_exec(SYSTEMCTL, "--user", "kill", "--signal=SIGKILL",
                                                        f"{unit}.scope", stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
            await stop.wait()
        try:
            os.killpg(proc.pid, 9)
        except ProcessLookupError:
            pass
        await proc.wait()


def jail_args(spec: RunSpec) -> list[str]:
    args = ["--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8", "--setenv", "TERM",
            "dumb", "--ro-bind", "/usr", "/usr", "--ro-bind", "/etc", "/etc"]
    for link in ("/bin", "/sbin", "/lib", "/lib64", "/lib32"):
        args += ["--ro-bind-try", link, link]  # symlinks into /usr on merged-/usr systems, folders elsewhere
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]
    if spec.network:
        args.append("--share-net")
    for mount in spec.mounts:
        args += ["--bind" if mount.writable else "--ro-bind", str(mount.path), str(mount.path)]
    for secret in spec.hidden:  # an empty folder or an empty file in place of each
        args += ["--tmpfs", str(secret)] if secret.is_dir() else ["--ro-bind", "/dev/null", str(secret)]
    if spec.workspace is not None:
        args += ["--bind", str(spec.workspace), str(spec.workspace), "--setenv", "HOME", str(spec.workspace)]
    return args + ["--chdir", str(spec.cwd)]


def _minimal_env() -> dict[str, str]:
    """What systemd-run needs to reach the user manager; the jail clears even this."""
    return {k: v for k, v in os.environ.items() if k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "PATH")}


def _host_env() -> dict[str, str]:
    """The person's environment for host commands, without anything that looks like a credential."""
    return {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in _SECRETISH)}
