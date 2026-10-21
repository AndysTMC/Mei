"""A fake world for agent-loop tests: a temporary home, the real file capabilities, the scripted
model, and the evals' driver."""

import datetime
import json
import os
from pathlib import Path

from mei.capabilities.base import Env
from mei.protocol import ProviderConfig
from mei.providers.fake import FakeProvider

from evals.driver import Driver, Recorder, call, turn  # noqa: F401  (re-exported for the loop and crash tests)


class TextExtractor:
    """Stands in for pdftotext: the test's "PDFs" are text files."""

    async def pdf_text(self, path: Path, max_chars: int) -> str:
        return path.read_text()[:max_chars]


async def fake_factory(cfg: ProviderConfig):
    return FakeProvider(cfg.options)


def make_world(tmp: Path) -> Env:
    home = tmp / "home"
    dirs = {"DOWNLOAD": home / "Downloads", "DOCUMENTS": home / "Documents", "MUSIC": home / "Music",
            "PICTURES": home / "Pictures"}
    for d in dirs.values():
        d.mkdir(parents=True)
    return Env(home=home, data_dir=tmp / "mei", data_home=home / ".local/share", user_dirs=dirs,
               extractor=TextExtractor())


def put(env: Env, path: str, text: str = "x", *, days_old: float = 0) -> Path:
    p = env.path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    if days_old:
        when = datetime.datetime.now().timestamp() - days_old * 86400
        os.utime(p, (when, when))
    return p


class Harness(Driver):
    """The driver with the scripted model; every request it gets is logged to `calls.jsonl`."""

    def __init__(self, tmp: Path, *, script=None, scripts=None, preset="balanced", cloud=False, cloud_files="pointed",
                 env: Env | None = None, boundary=lambda _n: None, **options) -> None:
        self.tmp = tmp
        self.log = tmp / "calls.jsonl"
        self.options = {"delay_ms": 0, "chunk_chars": 50, "call_log": str(self.log), "cloud": cloud,
                        "script": script or [], "scripts": scripts or {}, **options}
        super().__init__(tmp / "mei", env or make_world(tmp), fake_factory,
                         ProviderConfig(id="fake", options=self.options), preset=preset, cloud_files=cloud_files,
                         boundary=boundary)

    def requests(self) -> list[dict]:
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []


def assert_provider_valid(turns: list[dict]) -> None:
    """Every assistant turn with tool calls is followed at once by exactly one result per call."""
    i = 0
    while i < len(turns):
        t = turns[i]
        if t["role"] == "tool":
            raise AssertionError(f"tool result without its call at {i}: {turns}")
        if t["role"] == "assistant" and t.get("tool_calls"):
            n = len(t["tool_calls"])
            results = turns[i + 1:i + 1 + n]
            assert len(results) == n and all(r["role"] == "tool" for r in results), f"unpaired calls at {i}: {turns}"
            i += 1 + n
            continue
        i += 1
