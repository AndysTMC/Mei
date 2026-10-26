"""Running a desktop tool: by absolute path, with a timeout, bounded output, and no shell.

System GLib tools are called by absolute path (/usr/bin/gsettings): a shadowing copy earlier on
PATH (Homebrew's, for one) can use another settings backend and silently drop writes.
"""

import asyncio
import os
from dataclasses import dataclass

MAX_OUTPUT = 4 * 1024 * 1024


class ToolFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Output:
    code: int
    stdout: str
    stderr: str


async def run(argv: list[str], *, env: dict[str, str] | None = None, timeout: float = 15.0,
              max_output: int = MAX_OUTPUT, pass_fds: tuple[int, ...] = ()) -> Output:
    code, stdout, stderr = await _exec(argv, env, timeout, pass_fds)
    return Output(code, stdout[:max_output].decode("utf-8", "replace"), stderr)


async def checked_bytes(argv: list[str], *, timeout: float = 15.0, max_output: int = MAX_OUTPUT,
                        pass_fds: tuple[int, ...] = ()) -> bytes:
    """Like `checked`, for a tool whose output isn't text (a PNG). Output past `max_output` fails."""
    code, stdout, stderr = await _exec(argv, None, timeout, pass_fds)
    if code != 0:
        raise ToolFailed(f"{os.path.basename(argv[0])}: {_last_line(stderr) or f'exit status {code}'}")
    if len(stdout) > max_output:
        raise ToolFailed(f"{os.path.basename(argv[0])}: more than {max_output} bytes of output")
    return stdout


async def _exec(argv: list[str], env: dict[str, str] | None, timeout: float,
                pass_fds: tuple[int, ...]) -> tuple[int, bytes, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **(env or {})}, start_new_session=True, pass_fds=pass_fds)
    except OSError as e:
        raise ToolFailed(f"couldn't run {os.path.basename(argv[0])}: {e.strerror}") from None
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout, stderr[:64 * 1024].decode("utf-8", "replace")


async def checked(argv: list[str], **kw) -> str:
    out = await run(argv, **kw)
    if out.code != 0:
        raise ToolFailed(f"{os.path.basename(argv[0])}: {_last_line(out.stderr) or f'exit status {out.code}'}")
    return out.stdout


def _last_line(text: str) -> str:
    return text.strip().splitlines()[-1] if text.strip() else ""
