"""Sandboxed commands (§13.6, Stage 4): escape attempts against the real bubblewrap jail, cancel and
timeout through the engine, output spill, and policy for folders and host commands."""

import asyncio
import json
import subprocess
import time

import pytest

from mei.core.states import Execution, TaskState
from mei.desktop.sandbox import Sandbox
from mei.protocol import TaskCommandArgs

from agent_harness import Harness, call, put, turn

S, E = TaskState, Execution
pytestmark = pytest.mark.skipif(not Sandbox().available(), reason="needs bubblewrap")


def run_script(command: str, **extra) -> list[dict]:
    return [turn(call("shell_run", command=command, **extra)), {"text": "Done."}]


def output(h: Harness) -> str:
    return next(t["content"] for t in reversed(h.requests()[-1]["turns"]) if t["role"] == "tool")


# ── Escape attempts ─────────────────────────────────────────────────────────


async def test_the_jail_sees_no_home_no_network_and_nothing_writable_but_the_workspace(tmp_path):
    attempt = ("echo hi > out.txt; cat out.txt; echo kept > ~/kept.txt; "
               f"touch {tmp_path}/home/escaped 2>&1; touch /usr/escaped 2>&1; ls {tmp_path}/home/Documents 2>&1; "
               "getent hosts example.com >/dev/null && echo NET || echo nonet; "
               "cat /proc/1/cmdline | tr '\\0' ' '; echo; ls /run/user 2>&1 | head -1")
    h = Harness(tmp_path, script=run_script(attempt))
    put(h.env, "~/Documents/private.txt", "PRIVATE")
    r = h.submit("run a quick check")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "hi" in seen and "nonet" in seen and "NET\n" not in seen and "PRIVATE" not in seen
    assert not (h.env.home / "escaped").exists() and "Read-only file system" in seen
    assert (h.env.workspace(r["conversation_id"]) / "out.txt").read_text() == "hi\n"
    assert not (h.env.home / "kept.txt").exists()  # ~ is their home's path, but nothing written there gets out
    assert "approval.requested" not in h.rec.types()  # only Mei's own workspace: no card


async def test_tilde_is_the_persons_home_so_named_folders_are_where_they_expect(tmp_path):
    """A model writes ~/Desktop/notes.md as the person would; with ~/Desktop named, that's their file.
    Tools' caches still go to the workspace."""
    h = Harness(tmp_path, script=run_script("cp ~/Desktop/notes.md ~/Downloads/ && echo copied; echo $XDG_CACHE_HOME",
                                            folders=[{"path": "~/Desktop"}, {"path": "~/Downloads", "write": True}]))
    put(h.env, "~/Desktop/notes.md", "NOTES")
    (h.env.home / "Downloads").mkdir(exist_ok=True)
    r = h.submit("copy notes.md from my Desktop to Downloads")
    if await h.until(r["task_id"]) == S.WAITING_APPROVAL:  # writing into Downloads may ask, by the preset
        h.approve(r["task_id"])
        await h.until(r["task_id"])
    seen = output(h)
    assert "copied" in seen and h.env.path("~/Downloads/notes.md").read_text() == "NOTES"
    assert str(h.env.workspace(r["conversation_id"])) in seen  # caches: the workspace


async def test_network_needs_a_card(tmp_path):
    h = Harness(tmp_path, script=run_script("echo ok", network=True))
    r = h.submit("check the network")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL


async def test_a_named_folder_is_visible_read_only_and_its_secrets_are_masked(tmp_path):
    h = Harness(tmp_path, script=run_script("cat notes.txt; cat .env; ls -a; echo x > new.txt 2>&1",
                                            folders=[{"path": "~/Projects/site"}], cwd="~/Projects/site"))
    put(h.env, "~/Projects/site/notes.txt", "NOTES")
    put(h.env, "~/Projects/site/.env", "API_TOKEN=supersecret")
    r = h.submit("show me what's in ~/Projects/site")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "NOTES" in seen and "supersecret" not in seen and "Read-only file system" in seen
    assert not h.env.path("~/Projects/site/new.txt").exists()


async def test_a_writable_folder_asks_once_per_task(tmp_path):
    script = [turn(call("shell_run", command="echo 1 > a.txt", folders=[{"path": "~/Projects/site", "write": True}],
                        cwd="~/Projects/site")),
              turn(call("shell_run", command="echo 2 > src/b.txt", folders=[{"path": "~/Projects/site", "write": True}],
                        cwd="~/Projects/site")),
              {"text": "Built it."}]
    h = Harness(tmp_path, script=script)
    (h.env.home / "Projects" / "site" / "src").mkdir(parents=True)
    r = h.submit("build ~/Projects/site")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    card = h.approval(r["task_id"])
    assert '"loses_data"' in card["card"] and '"always"' not in card["card"]
    h.approve(r["task_id"], scope="task")
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert h.env.path("~/Projects/site/src/b.txt").read_text() == "2\n"
    assert h.rec.types().count("approval.requested") == 1


async def test_folders_holding_keys_are_refused(tmp_path):
    h = Harness(tmp_path, script=run_script("ls", folders=[{"path": "~"}]))
    r = h.submit("list my home folder with a command")
    assert await h.until(r["task_id"]) == S.COMPLETED
    [action] = h.actions(r["task_id"])
    assert action["execution"] == E.REJECTED and "holds folders Mei never opens" in action["error"]


async def test_a_folder_too_big_to_check_for_secrets_is_not_given_to_the_command(tmp_path, monkeypatch):
    """The check for secret files stops at a limit; past it, a nested .env would go unmasked."""
    from mei.policy.paths import PathRules
    monkeypatch.setattr(PathRules.secrets_under, "__defaults__", (5,))
    h = Harness(tmp_path, script=run_script("cat nested/.env", folders=[{"path": "~/Projects/big"}],
                                            cwd="~/Projects/big"))
    for n in range(10):
        put(h.env, f"~/Projects/big/{n}.txt", "x")
    put(h.env, "~/Projects/big/nested/.env", "API_TOKEN=supersecret")
    r = h.submit("look in ~/Projects/big")
    assert await h.until(r["task_id"]) == S.COMPLETED
    [action] = h.actions(r["task_id"])
    assert action["execution"] == E.FAILED and "too much in it" in action["error"]
    assert "supersecret" not in json.dumps([t["content"] for q in h.requests() for t in q["turns"]])


# ── Stopping ────────────────────────────────────────────────────────────────


async def test_stop_kills_a_long_command_and_everything_it_started_within_2s(tmp_path):
    marker = f"mei-test-{time.monotonic_ns()}"
    h = Harness(tmp_path, script=run_script(f"sleep 600 & sleep 600; echo {marker}", timeout_s=600))
    r = h.submit("wait a long time")
    async with asyncio.timeout(10):
        while not h.actions(r["task_id"]) or h.actions(r["task_id"])[0]["execution"] != E.STARTED:
            await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)
    started = time.monotonic()
    h.engine.cancel(TaskCommandArgs(command_id="stop", task_id=r["task_id"]))
    assert await h.until(r["task_id"], timeout=5) == S.CANCELLED
    assert time.monotonic() - started < 2.0
    left = subprocess.run(["pgrep", "-f", "^sleep 600$"], capture_output=True, text=True).stdout.split()
    assert not [pid for pid in left if _is_ours(pid, h)], "a sleep survived the stop"
    assert h.actions(r["task_id"])[0]["execution"] == E.CANCELLED


def _is_ours(pid: str, h: Harness) -> bool:
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            return str(h.env.home).encode() in f.read()
    except OSError:
        return False


async def test_a_command_over_its_time_limit_is_stopped(tmp_path):
    h = Harness(tmp_path, script=run_script("echo start; sleep 30", timeout_s=1))
    r = h.submit("try it")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "time limit" in seen and "start" in seen


# ── Output ──────────────────────────────────────────────────────────────────


async def test_long_output_keeps_head_and_tail_and_the_rest_can_be_read(tmp_path):
    h = Harness(tmp_path, script=[
        turn(call("shell_run", command="seq 1 20000")),
        turn(call("shell_output", run="PLACEHOLDER", offset=30000, max_chars=200)),
        {"text": "ok"}])
    r = h.submit("count")
    assert await h.until(r["task_id"]) == S.COMPLETED
    first = h.requests()[1]["turns"][-1]["content"]
    assert first.startswith('<observation source="shell.run" trust="untrusted">\n$ seq 1 20000\nexit 0') and "\n1\n2\n" in first and "20000" in first
    assert "bytes; read them with shell_output" in first
    run_id = first.split('shell_output(run="')[1][:8]
    spill = h.env.artifacts(r["conversation_id"])
    assert len(list(spill.glob(f"{run_id}*.out"))) == 1


# ── Host commands ───────────────────────────────────────────────────────────


async def test_host_commands_ask_every_time_and_show_the_command(tmp_path):
    h = Harness(tmp_path, preset="hands_off", script=[
        turn(call("shell_run_host", command="echo hello-from-host", cwd="~")),
        turn(call("shell_run_host", command="echo again", cwd="~")),
        {"text": "ok"}])
    r = h.submit("run echo on my computer")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    card = h.approval(r["task_id"])
    assert "echo hello-from-host" in card["card"] and '"scopes": ["once"]' in card["card"]
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL  # the second one asks again
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert "hello-from-host" in h.requests()[1]["turns"][-1]["content"]


async def test_command_output_is_deleted_with_the_conversation(tmp_path):
    from mei.protocol import ConversationCommandArgs
    h = Harness(tmp_path, script=run_script("echo hi > made.txt; echo done"))
    r = h.submit("make a file")
    await h.until(r["task_id"])
    spill, workspace = h.env.artifacts(r["conversation_id"]), h.env.workspace(r["conversation_id"])
    assert spill.exists() and workspace.exists()
    h.engine.delete_conversation(ConversationCommandArgs(command_id="d", conversation_id=r["conversation_id"]))
    assert not spill.exists() and not workspace.exists()


async def test_shell_output_reads_a_runs_spill_from_an_offset(tmp_path):
    from mei.capabilities.base import ActionContext, CapabilityError
    from mei.capabilities.shell import OutputParams, ShellOutput
    from agent_harness import make_world
    env = make_world(tmp_path)
    spill = env.artifacts("conv") / "abcdef12-0000.out"
    spill.parent.mkdir(parents=True)
    spill.write_text("0123456789" * 50)
    ctx = ActionContext(env, "other-action", "conv")
    r = await ShellOutput().run(OutputParams(run="abcdef12", offset=495, max_chars=100), ctx)
    assert r.observation == "56789"
    r = await ShellOutput().run(OutputParams(run="abcdef12", offset=0, max_chars=100), ctx)
    assert r.observation.startswith("0123456789") and "more after character 100" in r.observation
    with pytest.raises(CapabilityError):
        await ShellOutput().run(OutputParams(run="abcdef12"), ActionContext(env, "x", "another-conversation"))
    # A run id is matched against this conversation's own spills, never used as a path or a pattern.
    other = env.artifacts("other-conv") / "12345678-0000.out"
    other.parent.mkdir(parents=True)
    other.write_text("ANOTHER CONVERSATION'S OUTPUT")
    for sneaky in ("../other-conv/12345678", "*", "abc?ef12", "[a]bcdef12", "abcdef12/../../other-conv/1234"):
        with pytest.raises(CapabilityError):
            await ShellOutput().run(OutputParams(run=sneaky), ctx)
    # Where it came from goes along, as the run recorded it; with no record it has no sources (kept from clouds).
    assert r.sources == []
    spill.with_suffix(".sources").write_text('["/home/someone/project"]')
    r = await ShellOutput().run(OutputParams(run="abcdef12", max_chars=100), ctx)
    assert r.sources == ["/home/someone/project"]


# ── Folders bound by descriptor (decision 0015) ─────────────────────────────


def _swap_to_outside(h: Harness, tmp_path, folder: str):
    put(h.env, f"{folder}/notes.txt", "NOTES-INSIDE")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "notes.txt").write_text("OUTSIDE-SECRET")
    path = h.env.path(folder)

    def swap() -> None:
        path.rename(path.with_name(path.name + "-real"))
        path.symlink_to(outside)
    return swap


async def test_a_link_swapped_in_before_the_jail_starts_binds_the_folder_judged(tmp_path):
    h = Harness(tmp_path, script=run_script("cat notes.txt; touch made-here", folders=[{"path": "~/Projects/site", "write": True}],
                                            cwd="~/Projects/site"))
    swap = _swap_to_outside(h, tmp_path, "~/Projects/site")
    run = h.env.runner.run

    async def swap_then_run(spec):
        swap()  # after the folder is held open, before bubblewrap mounts it
        return await run(spec)
    h.env.runner.run = swap_then_run
    r = h.submit("build ~/Projects/site")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL  # a writable folder asks
    h.approve(r["task_id"], scope="task")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "NOTES-INSIDE" in seen and "OUTSIDE" not in seen
    assert h.env.path("~/Projects/site-real/made-here").exists() and not (tmp_path / "outside" / "made-here").exists()


async def test_a_link_swapped_in_after_the_recheck_never_reaches_the_jail(tmp_path, monkeypatch):
    from mei.core.loop import TaskLoop
    h = Harness(tmp_path, script=run_script("cat notes.txt", folders=[{"path": "~/Projects/site"}], cwd="~/Projects/site"))
    swap = _swap_to_outside(h, tmp_path, "~/Projects/site")
    recheck = TaskLoop._recheck

    async def recheck_then_swap(self, task, action):
        ok = await recheck(self, task, action)
        swap()
        return ok
    monkeypatch.setattr(TaskLoop, "_recheck", recheck_then_swap)
    r = h.submit("show me what's in ~/Projects/site")
    assert await h.until(r["task_id"]) == S.COMPLETED
    [action] = h.actions(r["task_id"])
    assert json.loads(action["result"])["error_class"] == "changed"
    assert "OUTSIDE" not in "\n".join(t["content"] for req in h.requests() for t in req["turns"])


async def test_a_host_command_runs_in_the_folder_approved(tmp_path):
    h = Harness(tmp_path, script=[turn(call("shell_run_host", command="cat notes.txt", cwd="~/Work")), {"text": "ok"}])
    swap = _swap_to_outside(h, tmp_path, "~/Work")
    run = h.env.runner.run

    async def swap_then_run(spec):
        swap()
        return await run(spec)
    h.env.runner.run = swap_then_run
    r = h.submit("run cat on my computer")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "NOTES-INSIDE" in seen and "OUTSIDE" not in seen


# ── Secrets appearing while a command runs (decision 0016) ──────────────────


@pytest.mark.parametrize("where", ["site/.env", "site/new/id_rsa"])
async def test_a_secret_file_appearing_during_a_command_stops_it_and_withholds_its_output(tmp_path, where):
    h = Harness(tmp_path, script=run_script("echo 'sta''rted'; sleep 3; cat .env new/id_rsa 2>&1; echo 'LEA''KED'",
                                            folders=[{"path": "~/Projects/site"}], cwd="~/Projects/site", timeout_s=20))
    put(h.env, "~/Projects/site/notes.txt", "notes")
    r = h.submit("show me what's in ~/Projects/site")
    async with asyncio.timeout(10):
        while not h.actions(r["task_id"]) or h.actions(r["task_id"])[0]["execution"] != E.STARTED:
            await asyncio.sleep(0.05)
    await asyncio.sleep(0.5)
    started = time.monotonic()
    put(h.env, f"~/Projects/{where}", "API_TOKEN=supersecret")  # the person's editor saves a secret meanwhile
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert time.monotonic() - started < 2.5  # stopped, not left to finish its sleep
    seen = "\n".join(t["content"] for req in h.requests() for t in req["turns"] if t["role"] == "tool")
    assert "supersecret" not in seen and "LEAKED" not in seen and "started" not in seen  # none of the output
    assert "may hold secrets, so Mei stopped the command" in seen
    assert not list(h.env.artifacts(r["conversation_id"]).glob("*.out"))  # the spill is gone too


async def test_secrets_already_there_are_masked_and_ordinary_new_files_dont_stop_anything(tmp_path):
    h = Harness(tmp_path, script=run_script("sleep 1; cat .env 2>&1; ls", folders=[{"path": "~/Projects/site", "write": True}],
                                            cwd="~/Projects/site"))
    put(h.env, "~/Projects/site/.env", "API_TOKEN=supersecret")
    r = h.submit("build ~/Projects/site")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"], scope="task")
    async with asyncio.timeout(10):
        while h.actions(r["task_id"])[0]["execution"] != E.STARTED:
            await asyncio.sleep(0.05)
    put(h.env, "~/Projects/site/README.md", "hello")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = output(h)
    assert "supersecret" not in seen and "README.md" in seen and "exit 0" in seen


async def test_a_secret_that_lands_after_the_look_stops_the_command_before_it_starts(tmp_path, monkeypatch):
    """Between looking for secrets to mask and the jail starting, a .env saved meanwhile isn't masked."""
    from mei.policy.paths import PathRules
    h = Harness(tmp_path, script=run_script("cat .env", folders=[{"path": "~/Projects/site"}], cwd="~/Projects/site"))
    put(h.env, "~/Projects/site/notes.txt", "notes")
    look = PathRules.secrets_under

    def look_then_save(self, folder, *args, **kw):
        found = look(self, folder, *args, **kw)
        put(h.env, "~/Projects/site/.env", "API_TOKEN=supersecret")  # saved just after the look
        return found
    monkeypatch.setattr(PathRules, "secrets_under", look_then_save)
    r = h.submit("show me what's in ~/Projects/site")
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = "\n".join(t["content"] for req in h.requests() for t in req["turns"] if t["role"] == "tool")
    assert "supersecret" not in seen and "may hold secrets" in seen


async def test_a_secret_written_as_the_command_ends_still_withholds_its_output(tmp_path, monkeypatch):
    """The command finishes before Mei reads the watch: its end and the secret are seen together."""
    from mei.desktop import sandbox
    real = asyncio.create_subprocess_exec

    async def run_to_the_end(*argv, **kw):
        proc = await real(*argv, **kw)
        await proc.wait()  # everything happens before the runner looks
        return proc
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", run_to_the_end)
    h = Harness(tmp_path, script=run_script("printf 'API_TOKEN=super''secret' > .env; cat .env",
                                            folders=[{"path": "~/Projects/site", "write": True}], cwd="~/Projects/site"))
    put(h.env, "~/Projects/site/notes.txt", "notes")
    r = h.submit("build ~/Projects/site")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.COMPLETED
    seen = "\n".join(t["content"] for req in h.requests() for t in req["turns"] if t["role"] == "tool")
    assert "supersecret" not in seen and "may hold secrets" in seen
