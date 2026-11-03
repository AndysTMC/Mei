"""Counterexamples from the pre-push review, with related boundary and persisted-data cases."""

import json
import sqlite3
from dataclasses import asdict

import httpx
import pytest

from agent_harness import Harness, Recorder, assert_provider_valid, call, fake_factory, turn
from evals.run import Result, _report, main
from mei.capabilities.catalog import default_registry
from mei.core import context
from mei.core.engine import Engine
from mei.core.loop import Crash
from mei.protocol import MemoryPatch, ProviderConfig, TaskCommandArgs, UpdateConfigArgs, UpdateMemoryArgs
from mei.providers.base import ChatTurn, ProviderError, Replay, ToolCall
from mei.providers.models import endpoint, list_models
from mei.providers.profiles import PROFILES
from mei.store import agent, memory as mem, repo
from mei.store.db import Store
from mei.voice.cleanup import Chain, Rules


async def finish(h, submitted):
    state = await h.until(submitted["task_id"])
    if state == "WAITING_APPROVAL":
        h.approve(submitted["task_id"])
        state = await h.until(submitted["task_id"])
    assert state == "COMPLETED"


@pytest.mark.parametrize("record,deleted,cloud", [("tracked", False, True), ("legacy", False, True),
    ("legacy", True, True), ("legacy", False, False), ("resource", False, True), ("resource", True, True)])
async def test_memory_disclosure_applies_to_replayed_action_summaries(tmp_path, record, deleted, cloud):
    h = Harness(tmp_path, cloud=cloud)
    private = "Orchid invoices contain a private medical detail"
    with h.store.tx() as tx:
        saved = mem.add_memory(tx, private, provenance="user_stated", status="active",
                               task_id=None, conversation_id=None)
        mem.update_memory(tx, saved["id"], sensitivity="local_only")
    revision, config = repo.get_config(h.store)
    config.providers["fake"].options["script"] = [turn(call("memory_forget", memory_id=saved["id"])), {"text": "done"}]
    h.engine.update_config(UpdateConfigArgs(revision, config))
    first = h.submit("Forget the saved memory with id " + saved["id"])
    await finish(h, first)
    [action] = h.actions(first["task_id"])
    stored = json.loads(action["result"])
    assert private in stored["summary"]  # the person's local history remains intact
    if record != "tracked":
        stored.pop("memory_ids", None)  # the old result's existing undo id must still protect it
        if record == "resource":  # recovery may have kept only the action description as its summary
            stored.pop("undo", None)
            stored["data_class"] = "metadata"
        with h.store.tx() as tx:
            tx.execute("UPDATE actions SET result = ? WHERE id = ?", (json.dumps(stored), action["id"]))
    if deleted:
        with h.store.tx() as tx:
            mem.delete_memory(tx, saved["id"])
    before = len(h.requests())
    nxt = h.submit("What happened?", conversation_id=first["conversation_id"])
    await finish(h, nxt)
    assert (private in json.dumps(h.requests()[before:])) is (not cloud)
    await h.engine.shutdown()
    h.store.close()


@pytest.mark.parametrize("legacy", [False, True])
async def test_memory_search_replay_respects_a_new_local_only_mark(tmp_path, legacy):
    h = Harness(tmp_path, cloud=True, script=[turn(call("memory_search", query="Orchid")), {"text": "done"}])
    private = "Orchid is the project for the confidential acquisition"
    with h.store.tx() as tx:
        saved = mem.add_memory(tx, private, provenance="user_stated", status="active", task_id=None, conversation_id=None)
    first = h.submit("Search memories for Orchid")
    await finish(h, first)
    [action] = h.actions(first["task_id"])
    result = json.loads(action["result"])
    if legacy:
        result.pop("memory_ids", None)
        with h.store.tx() as tx:
            tx.execute("UPDATE actions SET result = ? WHERE id = ?", (json.dumps(result), action["id"]))
    h.engine.update_memory(UpdateMemoryArgs("private", saved["id"], MemoryPatch(sensitivity="local_only")), from_shell=True)
    task = repo.get_task(h.store, first["task_id"])
    revision, config = repo.get_config(h.store)
    inputs = context.Inputs(h.store, h.env, h.engine.loop.d.registry, config.privacy,
                            ProviderConfig(id="fake", options={"cloud": True}), h.engine.loop.d.now())
    request = context.build(inputs, task)
    assert private not in "".join(t.content for t in request.messages if t.role == "tool")
    assert any(private in m["content"] for m in repo.history(h.store, first["conversation_id"]) if m["role"] == "tool")
    await h.engine.shutdown()
    h.store.close()


class CrashBeforeAction:
    def __call__(self, name):
        if name == "action_started":
            raise Crash(name)


async def crash_runner(h, task_id):
    # Keep the task reference so the deliberately injected BaseException is retrieved.
    runner = h.engine._runners[task_id]
    with pytest.raises(Crash):
        await runner
    h.store.close()
    h.env.memory = None  # a real restart constructs a fresh store-backed port
    h.rec = Recorder()
    h.engine = Engine(Store(h.tmp / "mei"), h.rec, fake_factory, registry=default_registry(), env=h.env)
    h.engine.recover()


@pytest.mark.parametrize("disabled", [False, True])
async def test_recovered_idempotent_actions_recheck_feature_availability(tmp_path, disabled):
    h = Harness(tmp_path, script=[turn(call("memory_search", query="Orchid")), {"text": "done"}],
                boundary=CrashBeforeAction())
    submitted = h.submit("Search my saved memories")
    await crash_runner(h, submitted["task_id"])
    if disabled:
        revision, config = repo.get_config(h.store)
        config.memory.enabled = False
        h.engine.update_config(UpdateConfigArgs(revision, config))
    h.engine.resume(TaskCommandArgs("resume", submitted["task_id"]))
    await finish(h, submitted)
    assert h.actions(submitted["task_id"])[0]["execution"] == ("POLICY_DENIED" if disabled else "SUCCEEDED")
    for request in h.requests():
        assert_provider_valid(request["turns"])
    await h.engine.shutdown()
    h.store.close()


@pytest.mark.parametrize("scope,revoked", [("once", False), ("task", False), ("task", True),
                                         ("always", False), ("always", True)])
async def test_recovery_checks_approval_lifetime_and_revocation(tmp_path, scope, revoked):
    h = Harness(tmp_path, preset="cautious", script=[turn(call("fs_make_dir", path="~/Documents/New")),
                                                     {"text": "done"}], boundary=CrashBeforeAction())
    submitted = h.submit("Create Documents/New")
    assert await h.until(submitted["task_id"]) == "WAITING_APPROVAL"
    old_approval = h.approval(submitted["task_id"])["id"]
    h.approve(submitted["task_id"], scope=scope)
    await crash_runner(h, submitted["task_id"])
    if revoked:
        with h.store.tx() as tx:
            for grant in agent.active_grants(h.store, submitted["task_id"]):
                agent.revoke_grant(tx, grant["id"])
    h.engine.resume(TaskCommandArgs("resume", submitted["task_id"]))
    state = await h.until(submitted["task_id"])
    if scope == "once" or revoked:
        assert state == "WAITING_APPROVAL"
        assert h.approval(submitted["task_id"])["id"] != old_approval
        assert not h.env.path("~/Documents/New").exists()
        assert h.actions(submitted["task_id"])[0]["disposition"] == "unknown"
        h.approve(submitted["task_id"], scope="once")
        assert await h.until(submitted["task_id"]) == "COMPLETED"
        assert h.env.path("~/Documents/New").is_dir()
    else:
        assert state == "COMPLETED" and h.env.path("~/Documents/New").is_dir()
    await h.engine.shutdown()
    h.store.close()


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_commit_failure_discards_events_and_cleans_or_retires_connection(tmp_path, rollback_fails):
    store = Store(tmp_path)
    def deny_transaction(op, first, second, database, trigger):
        denied = ("COMMIT", "ROLLBACK") if rollback_fails else ("COMMIT",)
        return sqlite3.SQLITE_DENY if op == sqlite3.SQLITE_TRANSACTION and first in denied else sqlite3.SQLITE_OK
    store.conn.set_authorizer(deny_transaction)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        with store.tx() as tx:
            repo.create_conversation(tx, "must not survive")
    assert tx.events == []
    if rollback_fails:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            store.conn.execute("SELECT 1")
    else:
        store.conn.set_authorizer(None)
        assert not store.conn.in_transaction
        assert repo.list_conversations(store) == []
        with store.tx() as tx:
            repo.create_conversation(tx, "next transaction")
        assert len(repo.list_conversations(store)) == 1 and len(tx.events) == 1
    store.close()


@pytest.mark.parametrize("raw,expected", [
    ("I will like both designs", "I will like both designs."),
    ("I can like jazz and classical music", "I can like jazz and classical music."),
    ("I just like the original version", "I just like the original version."),
    ("You might like this", "You might like this."),
    ("We should like more posts", "We should like more posts."),
    ("I like um both designs", "I like both designs."),
    ("I just like uh the original version", "I just like the original version."),
])
def test_dictation_does_not_guess_whether_like_is_a_verb(raw, expected):
    cleaned = Chain([Rules()])(raw)
    assert cleaned.text == expected and cleaned.raw == raw


@pytest.mark.parametrize("states,passed,expected", [(["COMPLETED"], [True], 0), (["FAILED"], [False], 1),
    (["COMPLETED", "BLOCKED"], [True, False], 1), (["ERROR"], [False], 2), (["SKIPPED"], [False], 2),
    (["COMPLETED", "SKIPPED"], [True, False], 2), ([], [], 2), (["BLOCKED"], [True], 0)])
def test_eval_exit_status_distinguishes_success_failure_and_incomplete_runs(tmp_path, states, passed, expected):
    results = [Result("probe", "file", "easy", ok, "", state, None, 0, 0, 0, 1, 0.1)
               for state, ok in zip(states, passed)]
    output = tmp_path / "result.json"
    assert _report(results, "scripted", str(output)) == expected
    assert len(json.loads(output.read_text())["results"]) == len(results)


async def test_an_empty_cli_task_selection_is_not_success():
    assert await main(["--tasks", "nonexistent-task"]) != 0


@pytest.mark.parametrize("url,expected", [
    ("https://api.anthropic.com/v1/messages", "https://api.anthropic.com/v1/models"),
    ("https://proxy.test/tenant/v1/messages/?ignored=1", "https://proxy.test/tenant/v1/models"),
    ("https://proxy.test/tenant/v1", "https://proxy.test/tenant/v1/models"),
    ("https://proxy.test/tenant", "https://proxy.test/tenant/v1/models"),
])
async def test_anthropic_catalog_overrides_follow_the_messages_transport(url, expected):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await list_models(client, "anthropic", url=url, api_key="synthetic-key")
    assert str(seen[0].url) == expected
    assert seen[0].headers["x-api-key"] == "synthetic-key" and result.models == ["test-model"]


@pytest.mark.parametrize("pid", [p for p in PROFILES if p not in ("custom", "githubcopilot", "opencode")])
def test_explicit_chat_endpoints_derive_the_same_catalog_path_as_defaults(pid):
    from urllib.parse import urlsplit
    assert urlsplit(endpoint(pid, url=PROFILES[pid].chat_url).url).path == urlsplit(endpoint(pid).url).path


def tool_history(size=50_000):
    turns = [ChatTurn("user", "Read the files")]
    for i in range(3):
        turns += [ChatTurn("assistant", "", tool_calls=(ToolCall(f"c{i}", "fs_read_text", "{}"),)),
                  ChatTurn("tool", "x" * size, tool_call_id=f"c{i}")]
    return turns


def test_protected_results_that_cannot_fit_fail_before_an_oversized_request_is_returned():
    turns = tool_history()
    before = list(turns)
    with pytest.raises(ProviderError, match="context budget"):
        context.fit(ChatTurn("system", "You are Mei."), [], turns, 64_000)
    assert turns == before  # never mutate the transcript to make it fit


@pytest.mark.parametrize("extra", ["replay", "signature", "escaping"])
def test_budget_counts_the_data_besides_visible_text(extra):
    user = ChatTurn("user", "hello")
    if extra == "replay":
        user = ChatTurn("assistant", "hello", replay=Replay("anthropic", {"signature": "s" * 5000}))
    elif extra == "signature":
        user = ChatTurn("assistant", "hello", tool_calls=(ToolCall("id", "tool", "{}", "s" * 5000),))
    else:
        user = ChatTurn("user", '"\\\n' * 1000)
    with pytest.raises(ProviderError, match="context budget"):
        context.fit(ChatTurn("system", "Mei"), [], [user], 2000)


@pytest.mark.parametrize("room", [2_000, 64_000])
def test_image_encoding_is_not_mistaken_for_text_capacity(room):
    picture = ChatTurn("tool", "snapshot abc", tool_call_id="c1", name="desktop_observe",
                       images=("a" * 100_000,))
    current = [ChatTurn("user", "Look at my screen"),
               ChatTurn("assistant", "", tool_calls=(ToolCall("c1", "desktop_observe", "{}"),)), picture]
    system = ChatTurn("system", "Mei")
    assert context.fit(system, [], current, room) == [system, *current]


def test_fitting_reserves_space_for_its_own_left_out_notice():
    earlier = [ChatTurn("user", "question" * 50), ChatTurn("assistant", "answer" * 50)] * 3
    system, current = ChatTurn("system", "Mei"), [ChatTurn("user", "now")]
    for room in (600, 1000, 1400, 1800):
        sent = context.fit(system, earlier, current, room)
        assert len(json.dumps([asdict(t) for t in sent], ensure_ascii=False)) <= room
        assert sent[0] == system and sent[-1].content.endswith("now")


async def test_request_budget_reserves_tool_definitions_and_request_wrapper(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    h.engine._schedule = lambda _task_id: None
    submitted = h.submit("Hello")
    task = repo.get_task(h.store, submitted["task_id"])
    _, config = repo.get_config(h.store)
    inputs = context.Inputs(h.store, h.env, h.engine.loop.d.registry, config.privacy,
                            ProviderConfig(id="fake"), h.engine.loop.d.now())
    request = context.build(inputs, task)
    assert request.tools
    # The request has no expendable history: reducing the total cap by one must fail, not omit
    # the tools or return the same oversized request after counting only their descriptions.
    monkeypatch.setitem(context.BUDGET_CHARS, "local", len(json.dumps(asdict(request), ensure_ascii=False)) - 1)
    with pytest.raises(ProviderError, match="context budget"):
        context.build(inputs, task)
    await h.engine.shutdown()
    h.store.close()


async def test_context_overflow_ends_clearly_without_sending_or_deleting_history(tmp_path, monkeypatch):
    monkeypatch.setitem(context.BUDGET_CHARS, "local", 60_000)
    h = Harness(tmp_path, script=[turn(*(call("fs_read_text", path=f"~/Documents/{i}.txt", max_chars=40_000)
                                      for i in range(3)))])
    for i in range(3):
        h.env.path(f"~/Documents/{i}.txt").write_text("x" * 30_000)
    submitted = h.submit("Read the three files in Documents")
    assert await h.until(submitted["task_id"]) == "FAILED"
    assert len(h.requests()) == 1  # only the initial, small request reached the provider
    history = repo.history(h.store, submitted["conversation_id"])
    assert len([m for m in history if m["role"] == "tool" and len(m["content"]) >= 30_000]) == 3
    assert "context budget" in history[-1]["content"]
    await h.engine.shutdown()
    h.store.close()
