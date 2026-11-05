"""Running a desktop tool: by absolute path, with a timeout, bounded output, and no shell.

System GLib tools are called by absolute path (/usr/bin/gsettings): a shadowing copy earlier on
PATH (Homebrew's, for one) can use another settings backend and silently drop writes.
"""

import asyncio
import os
from dataclasses import dataclass

MAX_OUTPUT = 4 * 1024 * 1024


def user_manager() -> bool:
    """Is a systemd user manager running for this session (so `systemd-run --user` works)? Its
    private socket is in the runtime dir; a private session or a CI runner can have the dir without
    one, and then commands run in a process group of their own instead."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    return bool(runtime_dir) and os.path.exists(os.path.join(runtime_dir, "systemd", "private"))


class ToolFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Output:
    code: int
    stdout: str
    stderr: str


async def run(argv: list[str], *, env: dict[str, str] | None = None, timeout: float = 15.0,
              max_output: int = MAX_OUTPUT, pass_fds: tuple[int, ...] = ()) -> Output:
    code, stdout, stderr, _over = await _exec(argv, env, timeout, pass_fds, max_output, strict=False)
    return Output(code, stdout.decode("utf-8", "replace"), stderr)


async def checked_bytes(argv: list[str], *, timeout: float = 15.0, max_output: int = MAX_OUTPUT,
                        pass_fds: tuple[int, ...] = ()) -> bytes:
    """Like `checked`, for a tool whose output isn't text (a PNG). Output past `max_output` fails."""
    code, stdout, stderr, over = await _exec(argv, None, timeout, pass_fds, max_output, strict=True)
    if over:
        raise ToolFailed(f"{os.path.basename(argv[0])}: more than {max_output} bytes of output")
    if code != 0:
        raise ToolFailed(f"{os.path.basename(argv[0])}: {_last_line(stderr) or f'exit status {code}'}")
    return stdout


STDERR_KEPT = 64 * 1024


async def _exec(argv: list[str], env: dict[str, str] | None, timeout: float, pass_fds: tuple[int, ...],
                max_output: int, *, strict: bool) -> tuple[int, bytes, str, bool]:
    """Run it, keeping at most `max_output` bytes of its output as they arrive (and the start of its
    errors): the rest is read and dropped, never held. `strict`: more output than that stops the
    tool, and the last value says so."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **(env or {})}, start_new_session=True, pass_fds=pass_fds)
    except OSError as e:
        raise ToolFailed(f"couldn't run {os.path.basename(argv[0])}: {e.strerror}") from None
    over = False

    async def keep(stream: asyncio.StreamReader, limit: int, stops: bool) -> bytes:
        nonlocal over
        kept = bytearray()
        while chunk := await stream.read(65536):  # to the end, so the pipe closes with the tool
            if stops and not over and len(kept) + len(chunk) > limit:
                over = True
                proc.kill()
            if not over:
                kept += chunk[:max(0, limit - len(kept))]
        return bytes(kept)

    async def finish() -> tuple[bytes, bytes]:
        out, err = await asyncio.gather(keep(proc.stdout, max_output, strict), keep(proc.stderr, STDERR_KEPT, False))
        await proc.wait()
        return out, err

    try:
        stdout, stderr = await asyncio.wait_for(finish(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout, stderr.decode("utf-8", "replace"), over


async def checked(argv: list[str], **kw) -> str:
    out = await run(argv, **kw)
    if out.code != 0:
        raise ToolFailed(f"{os.path.basename(argv[0])}: {_last_line(out.stderr) or f'exit status {out.code}'}")
    return out.stdout


def _last_line(text: str) -> str:
    return text.strip().splitlines()[-1] if text.strip() else ""
