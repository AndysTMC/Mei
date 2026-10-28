"""Capabilities against a fake world (§9.1 definition of done): effects, resources, results,
postconditions, recovery probes, and the schemas the model sees."""

import asyncio
import json
import os
from pathlib import Path

import msgspec
import pytest

from mei.capabilities import settings_values
from mei.capabilities.base import ActionContext, CapabilityError, Window
from mei.capabilities.catalog import default_registry
from mei.capabilities.checks import run_check
from mei.capabilities.fs_read import FsList, FsReadText, FsSearch, ListParams, ReadParams, SearchParams
from mei.capabilities.fs_write import (FsEdit, FsMakeDir, FsMove, FsTrash, FsWriteText, EditParams, MakeDirParams,
                                       MoveParams, TrashParams, WriteParams, find_trashed)
from mei.capabilities.meta import CheckSpec
from mei.capabilities.registry import InvalidArguments, Registry, portable_schema
from mei.core.states import Disposition

from agent_harness import make_world, put


@pytest.fixture
def env(tmp_path):
    return make_world(tmp_path)


def ctx(env, action_id="a1") -> ActionContext:
    return ActionContext(env, action_id)


# ── Reading ─────────────────────────────────────────────────────────────────


async def test_list_hides_dotfiles_and_marks_untrusted(env):
    put(env, "~/Downloads/b.pdf", "12345")
    put(env, "~/Downloads/.secret", "x")
    (env.home / "Downloads" / "sub").mkdir()
    r = await FsList().run(ListParams(path="~/Downloads"), ctx(env))
    assert r.trust == "untrusted" and "b.pdf (5 B" in r.observation and "sub/ (folder" in r.observation
    assert ".secret" not in r.observation
    with pytest.raises(CapabilityError) as err:
        await FsList().run(ListParams(path="~/nope"), ctx(env))
    assert err.value.error_class == "not_found"


async def test_search_by_name_date_and_text_skips_secrets(env):
    put(env, "~/Downloads/inv-new.pdf", days_old=3)
    put(env, "~/Downloads/inv-old.pdf", days_old=40)
    put(env, "~/Documents/notes/todo.txt", "buy MILK today")
    put(env, "~/project/.env", "milk=1")
    put(env, "~/.ssh/known_milk", "milk")
    import datetime
    since = str(datetime.date.today() - datetime.timedelta(days=7))
    r = await FsSearch().run(SearchParams(path="~/Downloads", name="inv-*.pdf", modified_after=since), ctx(env))
    assert "inv-new.pdf" in r.observation and "inv-old.pdf" not in r.observation
    r = await FsSearch().run(SearchParams(path="~", text="milk", include_hidden=True), ctx(env))
    assert "todo.txt" in r.observation and ".env" not in r.observation and ".ssh" not in r.observation
    with pytest.raises(CapabilityError):
        await FsSearch().run(SearchParams(path="~", modified_after="last tuesday"), ctx(env))


async def test_read_text_in_parts_and_pdfs(env):
    put(env, "~/Documents/long.txt", "a" * 300 + "b" * 300)
    r = await FsReadText().run(ReadParams(path="~/Documents/long.txt", max_chars=300), ctx(env))
    assert r.observation.startswith("a" * 300) and "offset=300" in r.observation
    assert r.data_class == "file_content" and r.sources == [str(env.path("~/Documents/long.txt"))]
    put(env, "~/Downloads/x.pdf", "pdf text")
    assert (await FsReadText().run(ReadParams(path="~/Downloads/x.pdf"), ctx(env))).observation == "pdf text"
    env.extractor = None
    with pytest.raises(CapabilityError) as err:
        await FsReadText().run(ReadParams(path="~/Downloads/x.pdf"), ctx(env))
    assert err.value.error_class == "unavailable"
    (env.home / "Documents" / "bin.dat").write_bytes(b"\0\1\2")
    with pytest.raises(CapabilityError):
        await FsReadText().run(ReadParams(path="~/Documents/bin.dat"), ctx(env))
    os.mkfifo(env.home / "Documents" / "pipe")  # nobody writes to it: opening it must not wait for someone
    with pytest.raises(CapabilityError, match="not a regular file"):
        await asyncio.wait_for(FsReadText().run(ReadParams(path="~/Documents/pipe"), ctx(env)), 5)


# ── Changing ────────────────────────────────────────────────────────────────


async def test_write_never_overwrites_without_asking_and_keeps_a_backup(env):
    cap, p = FsWriteText(), WriteParams(path="~/Documents/new/a.txt", text="one")
    r = await cap.run(p, ctx(env))
    assert r.undo["created_dirs"] == [str(env.home / "Documents/new")]
    assert (await cap.verify(p, r, ctx(env))).status == "passed"
    with pytest.raises(CapabilityError) as err:
        await cap.run(WriteParams(path="~/Documents/new/a.txt", text="two"), ctx(env, "a2"))
    assert err.value.error_class == "exists"
    r = await cap.run(WriteParams(path="~/Documents/new/a.txt", text="two", overwrite=True), ctx(env, "a3"))
    assert Path(r.undo["backup"]).read_text() == "one" and env.path("~/Documents/new/a.txt").read_text() == "two"
    assert cap.effects(p, env).undo == "recorded" and not cap.effects(p, env).loses_data


async def test_write_probe(env):
    cap, p = FsWriteText(), WriteParams(path="~/Documents/a.txt", text="hello")
    assert await cap.probe(p, ctx(env)) == Disposition.NONE
    put(env, "~/Documents/a.txt", "hello")
    assert await cap.probe(p, ctx(env)) == Disposition.CONFIRMED


async def test_edit_requires_the_exact_count(env):
    put(env, "~/Documents/a.txt", "cat cat dog")
    cap = FsEdit()
    with pytest.raises(CapabilityError):
        await cap.run(EditParams(path="~/Documents/a.txt", old="cat", new="cow"), ctx(env))
    p = EditParams(path="~/Documents/a.txt", old="cat", new="cow", count=2)
    r = await cap.run(p, ctx(env))
    assert env.path("~/Documents/a.txt").read_text() == "cow cow dog"
    assert (await cap.verify(p, r, ctx(env))).status == "passed"
    assert await cap.probe(p, ctx(env)) == Disposition.CONFIRMED


async def test_move_into_folders_never_replaces_and_probes(env):
    put(env, "~/Downloads/a.pdf", "A")
    put(env, "~/Documents/Inv/b.pdf", "B")
    cap = FsMove()
    p = MoveParams(source="~/Downloads/a.pdf", destination="~/Documents/Inv/2026/")
    assert [r.value for r in cap.resources(p, env)] == [str(env.home / "Downloads/a.pdf"),
                                                       str(env.home / "Documents/Inv/2026/a.pdf")]
    assert await cap.probe(p, ctx(env)) == Disposition.NONE
    r = await cap.run(p, ctx(env))
    assert env.path("~/Documents/Inv/2026/a.pdf").read_text() == "A"
    assert (await cap.verify(p, r, ctx(env))).status == "passed"
    assert await cap.probe(p, ctx(env)) == Disposition.CONFIRMED
    put(env, "~/Downloads/b.pdf", "other B")
    with pytest.raises(CapabilityError) as err:
        await cap.run(MoveParams(source="~/Downloads/b.pdf", destination="~/Documents/Inv"), ctx(env, "a2"))
    assert err.value.error_class == "exists" and env.path("~/Documents/Inv/b.pdf").read_text() == "B"
    with pytest.raises(CapabilityError):
        await cap.run(MoveParams(source="~/Documents", destination="~/Documents/Inv/x"), ctx(env, "a3"))


async def test_make_dir_is_idempotent(env):
    cap, p = FsMakeDir(), MakeDirParams(path="~/Documents/a/b")
    r = await cap.run(p, ctx(env))
    assert r.undo["created"] == [str(env.home / "Documents/a"), str(env.home / "Documents/a/b")]
    again = await cap.run(p, ctx(env, "a2"))
    assert again.ok and again.undo["created"] == []


async def test_trash_follows_the_freedesktop_spec(env):
    put(env, "~/Documents/report.txt", "1")
    cap, p = FsTrash(), TrashParams(path="~/Documents/report.txt")
    r = await cap.run(p, ctx(env))
    trashed = Path(r.undo["trashed"])
    info = Path(r.undo["info"]).read_text()
    assert trashed.read_text() == "1" and not env.path("~/Documents/report.txt").exists()
    assert info.startswith("[Trash Info]\nPath=") and "DeletionDate=" in info
    assert find_trashed(env, env.path("~/Documents/report.txt")) == trashed
    assert await cap.probe(p, ctx(env)) == Disposition.CONFIRMED
    put(env, "~/Documents/report.txt", "2")  # a second file of the same name gets a numbered name
    r2 = await cap.run(p, ctx(env, "a2"))
    assert Path(r2.undo["trashed"]).name == "report.2.txt"
    assert stat_mode(env.trash_dir / "files") == 0o700


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777


# ── Criterion checks ────────────────────────────────────────────────────────


class FakeSettings:
    def __init__(self, values: dict) -> None:
        self.values = values

    async def get(self, schema: str, key: str) -> str:
        return self.values[(schema, key)]

    async def set(self, schema: str, key: str, value: str) -> None:
        self.values[(schema, key)] = value

    async def range(self, schema: str, key: str) -> str:
        return "type s"


class FakeBridge:
    async def list_windows(self) -> list[Window]:
        return [Window(app_id="org.gnome.Nautilus", title="Downloads")]


async def test_checks_look_at_the_world(env):
    put(env, "~/Documents/Inv/a.pdf", "12345")
    put(env, "~/Documents/Inv/b.pdf")
    check = lambda **kw: run_check(CheckSpec(**kw), env)  # noqa: E731
    assert (await check(type="file_exists", path="~/Documents/Inv/a.pdf", min_size=5)).status == "passed"
    assert (await check(type="file_exists", path="~/Documents/Inv/a.pdf", min_size=6)).status == "failed"
    assert (await check(type="file_absent", path="~/Documents/Inv/zzz")).status == "passed"
    assert (await check(type="dir_contains", path="~/Documents/Inv", glob="*.PDF", count=2)).status == "passed"
    assert (await check(type="dir_contains", path="~/Documents/Inv", glob="*.txt")).status == "failed"
    assert (await check(type="setting_equals", schema="s", key="k", value="x")).status == "unverifiable"
    env.gsettings = FakeSettings({("org.gnome.desktop.interface", "color-scheme"): "'prefer-dark'"})
    assert (await check(type="setting_equals", schema="org.gnome.desktop.interface", key="color-scheme",
                        value="prefer-dark")).status == "passed"
    assert (await check(type="window_present", app_id="org.gnome.Nautilus")).status == "unverifiable"
    env.bridge = lambda: FakeBridge()
    assert (await check(type="window_present", app_id="org.gnome.Nautilus.desktop", title="downloads")).status == "passed"
    assert (await check(type="window_present", title="Pictures")).status == "failed"


def test_gvariant_scalars():
    assert settings_values.parse("'prefer-dark'") == "prefer-dark"
    assert settings_values.parse("uint32 4000") == 4000 and settings_values.parse("true") is True
    assert settings_values.parse("'it\\'s'") == "it's" and settings_values.parse("['a']") is None
    assert settings_values.same_value("uint32 4000", "4000") and settings_values.same_value("1.0", "1")
    assert not settings_values.same_value("true", "1")
    assert settings_values.to_text("it's") == "'it\\'s'" and settings_values.to_text(False) == "false"


# ── What the model sees ─────────────────────────────────────────────────────


def _walk(node):
    """Every schema node (not the name → schema maps under `properties`)."""
    yield node
    for prop in node.get("properties", {}).values():
        yield from _walk(prop)
    if isinstance(node.get("items"), dict):
        yield from _walk(node["items"])
    for option in node.get("anyOf", []):
        yield from _walk(option)


def test_every_schema_is_in_the_portable_subset(env):
    specs = default_registry().specs(env)
    names = [s.name for s in specs]
    assert "fs_move" in names and "task_finish" in names and all("." not in n for n in names)
    for spec in specs:
        assert spec.parameters["type"] == "object", spec.name
        for node in _walk(spec.parameters):
            assert not {"$ref", "$defs", "title", "additionalProperties"} & set(node), (spec.name, node)
            if "enum" in node:
                assert node["type"] in ("string", "integer", "number"), (spec.name, node)
                assert "" not in node["enum"], (spec.name, node)  # Gemini rejects empty enum values
            assert node.get("default", 0) is not None, (spec.name, node)
            if "anyOf" in node:
                assert all(o.get("type") != "null" for o in node["anyOf"]), (spec.name, node)
    finish = next(s for s in specs if s.name == "plan_update").parameters
    check = finish["properties"]["criteria"]["items"]["properties"]["check"]
    assert check["type"] == "object" and "file_exists" in check["properties"]["type"]["enum"]


def test_arguments_are_decoded_strictly_but_forgivingly():
    registry = default_registry()
    cap = registry.by_wire("fs_list")
    assert registry.decode(cap, '{"path": "~", "limit": "5"}').limit == 5  # a number sent as text is fine
    with pytest.raises(InvalidArguments):
        registry.decode(cap, '{"limit": 5}')  # but a missing path is not
    with pytest.raises(InvalidArguments):
        registry.decode(cap, "not json")
    a = registry.canonical(cap, registry.decode(cap, '{"path": "~", "limit": 5}'))
    b = registry.canonical(cap, registry.decode(cap, '{"limit": 5, "path": "~"}'))
    assert a == b  # the approval hash doesn't depend on key order


def test_a_name_registered_twice_is_an_error():
    with pytest.raises(ValueError):
        Registry([FsList(), FsList()])


def test_portable_schema_flattens_optional_fields():
    class P(msgspec.Struct):
        a: str
        b: int | None = None
    schema = portable_schema(P)
    assert schema["properties"]["b"] == {"type": "integer"} and schema["required"] == ["a"]
    json.dumps(schema)


def test_a_question_card_is_bounded_so_it_cannot_swamp_the_shell():
    """Each option becomes a widget in the compositor: a model asking with thousands is refused."""
    from mei.capabilities.meta import AskParams
    many = {"question": "Pick", "fields": [{"name": "x", "label": "X", "kind": "select",
                                            "options": [str(i) for i in range(10_000)]}]}
    for bad in (many, {"question": "Q" * 5000}, {"question": "Pick", "choices": ["x" * 500]}):
        with pytest.raises(msgspec.ValidationError):
            msgspec.convert(bad, AskParams)
    assert msgspec.convert({"question": "Pick", "choices": ["Downloads", "Desktop"]}, AskParams).choices
