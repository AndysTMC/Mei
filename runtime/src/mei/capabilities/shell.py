"""Running commands (§9.3, §13.6).

`shell.run` runs in a jail that sees the conversation's workspace and only the folders it names.
A writable folder outside the workspace can lose data (a command can delete anything in it), so it
asks unless the person granted that folder for the task. `shell.run_host` runs in the person's own
session, unsandboxed, and asks every time, showing the exact command. Output keeps its head and
tail; the rest is read with `shell.output`.
"""

import os
from contextlib import ExitStack
from pathlib import Path
from typing import Annotated

import msgspec

from .base import (WORKSPACE, ActionContext, ActionResult, Availability, AVAILABLE, Capability, CapabilityError,
                   Effects, Env, Mount, Resource, RunResult, RunSpec)
from .fs_at import folder, judged_path

MAX_COMMAND = 4000
MAX_TIMEOUT_S = 600


class Folder(msgspec.Struct, kw_only=True):
    path: str
    write: Annotated[bool, msgspec.Meta(description="Let the command change files here")] = False


class RunParams(msgspec.Struct, kw_only=True):
    command: Annotated[str, msgspec.Meta(min_length=1, max_length=MAX_COMMAND,
                                         description="A shell command line, run with /bin/sh -c")]
    folders: Annotated[list[Folder], msgspec.Meta(max_length=8, description=(
        "Folders the command may see, read-only unless write is true. Nothing else of the home folder is "
        "visible; a scratch workspace (also $HOME) always is."))] = msgspec.field(default_factory=list)
    cwd: Annotated[str, msgspec.Meta(description="Where to run: one of the folders, or the workspace (default)")] = ""
    network: Annotated[bool, msgspec.Meta(description="Allow network access (off by default)")] = False
    timeout_s: Annotated[int, msgspec.Meta(ge=1, le=MAX_TIMEOUT_S)] = 120


def _folder(env: Env, value: str) -> Path:
    """A folder a command may see: it must exist, and must not hold one Mei never opens."""
    path = _real(env, value)
    if not path.is_dir():
        raise CapabilityError("not_found", f"{env.show(path)} isn't a folder")
    if env.rules.holds_denied(path):
        raise CapabilityError("invalid", f"{env.show(path)} holds folders Mei never opens (keys, keyrings, browser "
                                         "profiles); name a folder inside it instead")
    return path


def _real(env: Env, value: str) -> Path:
    try:
        return Path(os.path.realpath(env.path(value)))
    except ValueError as e:
        raise CapabilityError("invalid", str(e)) from None


class ShellRun(Capability):
    name = "shell.run"
    summary = ("Run a command in a sandbox: it sees only the folders you list (read-only unless write) and a "
               "scratch workspace, with no network unless you ask. For builds, scripts, converting files.")
    Params = RunParams
    timeout_s = MAX_TIMEOUT_S + 10

    def available(self, env: Env) -> Availability:
        if env.runner is None or not env.runner.available(sandboxed=True):
            return Availability.unavailable("bubblewrap isn't installed")
        return AVAILABLE

    def effects(self, p: RunParams, env: Env) -> Effects:
        disclosure = "off_machine" if p.network else "none"
        if any(f.write for f in p.folders):  # it can delete anything in those folders: no undo
            return Effects(mutates="local", undo="none", loses_data=True, disclosure=disclosure)
        return Effects(mutates="local", undo="none", disclosure=disclosure)  # only the workspace changes

    def resources(self, p: RunParams, env: Env) -> list[Resource]:
        found = [Resource(kind="path", value=str(_folder(env, f.path)), access="write" if f.write else "read",
                          role="folder") for f in p.folders]
        return found + [Resource(kind="path", value=WORKSPACE, access="write", role="workspace")]

    def reads_content(self, p: RunParams, env: Env) -> list[Path]:
        return [_real(env, f.path) for f in p.folders]

    def describe(self, p: RunParams, env: Env) -> str:
        where = ", ".join(env.show(_real(env, f.path)) + (" (can change)" if f.write else "") for f in p.folders)
        return f"Run `{p.command}`" + (f" with {where}" if where else "") + (" and network access" if p.network else "")

    async def run(self, p: RunParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        # Every folder the jail gets is held open from here until the command ends, and bound by its
        # descriptor (decision 0015): the folders judged, whatever their paths lead to by then.
        with ExitStack() as held:
            workspace = judged_path(ctx, "workspace", env.workspace(ctx.conversation_id))
            space = held.enter_context(folder(env, workspace, create=True, mode=0o700))
            mounts, hidden = [], []
            for i, f in enumerate(p.folders):
                path = judged_path(ctx, "folder", _folder(env, f.path), index=i)
                opened = held.enter_context(folder(env, path))
                secrets, _complete = env.rules.secrets_under(path, dir_fd=opened.fd)
                mounts.append(Mount(path, writable=f.write, fd=opened.fd))
                hidden += secrets
            cwd = _real(env, p.cwd) if p.cwd else (mounts[0].path if mounts else workspace)
            if cwd != workspace and not any(cwd == m.path or m.path in cwd.parents for m in mounts):
                raise CapabilityError("invalid", "cwd must be one of the folders, or the workspace")
            spec = RunSpec(command=p.command, cwd=cwd, timeout_s=p.timeout_s, workspace=workspace,
                           workspace_fd=space.fd, mounts=tuple(mounts), hidden=tuple(hidden), network=p.network,
                           spill=_spill(ctx))
            result = await env.runner.run(spec)
        return report(p.command, result, ctx, sources=[str(m.path) for m in mounts])


class HostParams(msgspec.Struct, kw_only=True):
    command: Annotated[str, msgspec.Meta(min_length=1, max_length=MAX_COMMAND)]
    cwd: str = "~"
    timeout_s: Annotated[int, msgspec.Meta(ge=1, le=MAX_TIMEOUT_S)] = 120


class ShellRunHost(Capability):
    """Unsandboxed: for what the jail can't do (system tools, the person's own environment). Mei
    can't tell what it will change, and the person approves each exact command."""

    name = "shell.run_host"
    summary = ("Run a command in the person's own session, outside the sandbox. They approve every command, "
               "so prefer shell_run; use this only when the sandbox can't do it.")
    Params = HostParams
    always_ask = True
    timeout_s = MAX_TIMEOUT_S + 10

    def available(self, env: Env) -> Availability:
        return AVAILABLE if env.runner is not None else Availability.unavailable("commands can't run here")

    def effects(self, p: HostParams, env: Env) -> Effects:
        return Effects(mutates="unknown", undo="none", loses_data=True)

    def resources(self, p: HostParams, env: Env) -> list[Resource]:
        return [Resource(kind="path", value=str(_real(env, p.cwd)), access="write", role="cwd")]

    def reads_content(self, p: HostParams, env: Env) -> list[Path]:
        return [_real(env, p.cwd)]

    def describe(self, p: HostParams, env: Env) -> str:
        return f"Run on your computer, unsandboxed, in {env.show(_real(env, p.cwd))}: {p.command}"

    async def run(self, p: HostParams, ctx: ActionContext) -> ActionResult:
        cwd = judged_path(ctx, "cwd", _real(ctx.env, p.cwd))
        if not cwd.is_dir():
            raise CapabilityError("not_found", f"{ctx.env.show(cwd)} isn't a folder")
        with folder(ctx.env, cwd) as here:  # it runs in the folder approved, held open
            spec = RunSpec(command=p.command, cwd=cwd, cwd_fd=here.fd, timeout_s=p.timeout_s, spill=_spill(ctx),
                           sandboxed=False)
            result = await ctx.env.runner.run(spec)
        return report(p.command, result, ctx, sources=[str(cwd)])


class OutputParams(msgspec.Struct, kw_only=True):
    run: Annotated[str, msgspec.Meta(description="The run id shown with the output (its first 8 characters)")]
    offset: Annotated[int, msgspec.Meta(ge=0)] = 0
    max_chars: Annotated[int, msgspec.Meta(ge=100, le=50_000)] = 20_000


class ShellOutput(Capability):
    name = "shell.output"
    summary = "Read more of a long command output, from a character offset."
    Params = OutputParams
    idempotent = True

    def describe(self, p: OutputParams, env: Env) -> str:
        return f"Read the output of run {p.run}"

    async def run(self, p: OutputParams, ctx: ActionContext) -> ActionResult:
        folder = ctx.env.artifacts(ctx.conversation_id)
        matches = sorted(folder.glob(f"{p.run.strip()[:36]}*.out")) if p.run.strip() and folder.is_dir() else []
        if len(matches) != 1:
            raise CapabilityError("not_found", f"no output for run {p.run} in this conversation")
        text = matches[0].read_bytes().decode("utf-8", "replace")
        part = text[p.offset:p.offset + p.max_chars]
        more = len(text) > p.offset + len(part)
        note = f"\n[… more after character {p.offset + len(part)}]" if more else ""
        return ActionResult(ok=True, observation=(part or "(nothing here)") + note, summary=f"Read run {p.run}'s output",
                            data_class="file_content", trust="untrusted")


def _spill(ctx: ActionContext) -> Path:
    return ctx.env.artifacts(ctx.conversation_id) / f"{ctx.action_id}.out"


def report(command: str, r: RunResult, ctx: ActionContext, *, sources: list[str]) -> ActionResult:
    """What the model sees of a run: the status, then the head and tail of the output."""
    if r.timed_out:
        status = f"stopped after {r.seconds:.0f} s (time limit); everything it started was killed"
    else:
        status = f"exit {r.exit_code} after {r.seconds:.1f} s"
    ok = not r.timed_out and r.exit_code == 0
    notes = "".join(f"\n({n})" for n in r.notes)
    return ActionResult(ok=ok, observation=f"$ {command}\n{status}\n{_body(r, ctx).rstrip()}{notes}",
                        summary=f"Ran `{command[:60]}`: {status.split(';')[0]}",
                        error_class="" if ok else ("timeout" if r.timed_out else "failed"),
                        data_class="file_content", trust="untrusted", sources=sources)


def _body(r: RunResult, ctx: ActionContext) -> str:
    rest = r.total_bytes - len(r.head)  # bytes after the head
    if rest <= len(r.tail):  # head and tail meet: that's all of it
        whole = r.head + (r.tail[len(r.tail) - rest:] if rest > 0 else b"")
        return whole.decode("utf-8", "replace")
    skipped = rest - len(r.tail)
    return (r.head.decode("utf-8", "replace") + f"\n[… {skipped} bytes; read them with "
            f"shell_output(run=\"{ctx.action_id[:8]}\", offset=…)]\n" + r.tail.decode("utf-8", "replace"))
