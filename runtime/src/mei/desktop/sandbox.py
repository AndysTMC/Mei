"""Running a command for a task (§13.6): in a bubblewrap jail inside a systemd scope, or (for
`shell.run_host`) in a scope alone.

The jail sees /usr and /etc read-only, a private /tmp, the task's workspace, and only the folders
the action names (each read-only unless marked writable). `$HOME` is the person's home path, of
which only those folders exist; tools' caches and settings (the XDG folders) go to the workspace. Folders come as descriptors Mei holds
open and are bound with `--bind-fd`, which checks that what it mounted is that very folder, so a
link swapped in after policy's check can't put another folder in the jail (decision 0015). There is no network unless asked for, no
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

from .run import user_manager
from .watch import MAX_FOLDERS as MAX_WATCHED, SecretWatch

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
        self._scope = systemd_run if os.access(systemd_run, os.X_OK) and user_manager() else None

    def available(self, sandboxed: bool = True) -> bool:
        return self._bwrap is not None or not sandboxed

    async def run(self, spec: RunSpec) -> RunResult:
        unit = f"mei-run-{uuid.uuid4().hex[:12]}"
        argv = self._argv(spec, unit)
        spec.spill.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        started = time.monotonic()
        held = tuple(fd for fd in (*(m.fd for m in spec.mounts), spec.workspace_fd, spec.cwd_fd) if fd is not None)
        if spec.sandboxed:
            cwd = "/"
        else:  # the child's copy of the held folder: the folder judged, whatever its path leads to now
            cwd = f"/proc/self/fd/{spec.cwd_fd}" if spec.cwd_fd is not None else str(spec.cwd)
        result = RunResult(None, b"", b"", 0, 0.0, spilled=spec.spill)
        watched = [(m.path, m.fd) for m in spec.mounts if m.fd is not None]
        # Watching starts before the command does (decision 0016), so nothing it writes lands unseen;
        # a secret already there that wasn't masked (it came after the look) stops it before it starts.
        watch = SecretWatch(watched, spec.secret, frozenset(spec.hidden)) \
            if spec.secret is not None and watched else None
        if watch is not None:
            watch.start()
            if not watch.complete:
                result.notes.append(f"Mei could watch only {MAX_WATCHED} folders for secret files appearing")
            if watch.tripped.is_set():
                watch.close()
                result.secret_appeared = watch.found
                return result
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, cwd=cwd, env=_host_env() if not spec.sandboxed else _minimal_env(),
                start_new_session=True, pass_fds=held)
        except BaseException:
            if watch is not None:
                watch.close()
            raise
        collect = asyncio.ensure_future(self._collect(proc, spec.spill, result))
        tripped = asyncio.ensure_future(watch.tripped.wait()) if watch is not None else None
        try:
            done, _ = await asyncio.wait({collect, *([tripped] if tripped else [])}, timeout=spec.timeout_s,
                                         return_when=asyncio.FIRST_COMPLETED)
            if collect in done:
                collect.result()
                result.exit_code = await proc.wait()
                if watch is not None:
                    watch.drain()  # a secret written just before the end counts, though the end was seen first
                    if watch.tripped.is_set():
                        result.secret_appeared = watch.found
            else:
                if tripped is not None and tripped in done:
                    result.secret_appeared = watch.found
                else:
                    result.timed_out = True
                await self._stop(proc, unit)
                await collect  # the output ends with the process
        except asyncio.CancelledError:
            await self._stop(proc, unit)
            raise
        finally:
            for task in (collect, tripped):
                if task is not None and not task.done():
                    task.cancel()
            if watch is not None:
                watch.close()
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
    if spec.home is not None and spec.workspace is not None:
        args += ["--dir", str(spec.home)]  # an empty, throwaway home: only the named folders appear in it
    for mount in spec.mounts:
        args += _bind(mount.path, mount.fd, writable=mount.writable)
    for secret in spec.hidden:  # an empty folder or an empty file in place of each
        args += ["--tmpfs", str(secret)] if secret.is_dir() else ["--ro-bind", "/dev/null", str(secret)]
    if spec.workspace is not None:
        args += _bind(spec.workspace, spec.workspace_fd, writable=True)
        # `~` is the person's home, as they and the model mean it (only named folders are there);
        # tools' caches and settings go to the workspace, which lasts with the conversation.
        args += ["--setenv", "HOME", str(spec.home or spec.workspace)]
        for var, sub in (("XDG_CACHE_HOME", ".cache"), ("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                         ("XDG_STATE_HOME", ".local/state")):
            args += ["--setenv", var, str(spec.workspace / sub)]
    return args + ["--chdir", str(spec.cwd)]


def _bind(path: Path, fd: int | None, *, writable: bool) -> list[str]:
    """Bind a folder at its own path in the jail: the held one by descriptor when there is one."""
    if fd is not None:
        return ["--bind-fd" if writable else "--ro-bind-fd", str(fd), str(path)]
    return ["--bind" if writable else "--ro-bind", str(path), str(path)]


def _minimal_env() -> dict[str, str]:
    """What systemd-run needs to reach the user manager; the jail clears even this."""
    return {k: v for k, v in os.environ.items() if k in ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS", "PATH")}


def _host_env() -> dict[str, str]:
    """The person's environment for host commands, without anything that looks like a credential."""
    return {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in _SECRETISH)}
