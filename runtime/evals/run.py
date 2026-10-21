"""Run the eval tasks and score them by the world they leave behind (§20, §22 Stage 3).

    uv run python -m evals.run                      # the scripted model: proves the harness and checks
    uv run python -m evals.run --provider groq      # a real model, key and model from the repo's .env
    uv run python -m evals.run --provider gemini --model gemini-3-flash --repeat 3 --out baseline.json

Approvals are answered like a careful person reading the card: allowed once, unless something on
it came from a file or web page, which is denied. Questions get their first choice. Keys are never
printed. Reported per run: pass rate, approval prompts per task, and how often a task that wasn't
verified by Mei's own checks was actually wrong ("wrong-reported rate").
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from mei.core.states import TaskState
from mei.obs import redact
from mei.protocol import ProviderConfig
from mei.providers import factory
from mei.providers.fake import FakeProvider
from mei.store import agent, repo

from .driver import Driver
from .tasks import TASKS, Task
from .world import World

S = TaskState
ENV = Path(__file__).resolve().parents[2] / ".env"
TASK_TIMEOUT_S = 240.0
MAX_ROUNDS = 12  # cards and questions answered per task before giving up
# provider id → (key variable, model variable) in .env
LIVE = {"openai": ("OPENAI_API_KEY", "OPENAI_MODEL"), "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
        "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"), "groq": ("GROQ_API_KEY", "GROQ_MODEL"),
        "mistral": ("MISTRAL_API_KEY", "MISTRAL_MODEL"), "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
        "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"), "fireworks": ("FIREWORKS_API_KEY", "FIREWORKS_MODEL"),
        "nvidia": ("NVIDIA_API_KEY", "NVIDIA_MODEL"), "ollama": ("", "OLLAMA_MODEL")}


def load_env() -> dict[str, str]:
    """The process environment, plus the repo's .env for anything it doesn't set."""
    env = dict(os.environ)
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


@dataclass
class Result:
    task: str
    kind: str
    passed: bool
    detail: str
    state: str
    outcome: str | None  # outcome_verified / partially_verified / reported, or None for a plain answer
    prompts: int  # approval cards shown
    denied: int  # cards the careful person denied
    questions: int
    model_calls: int
    seconds: float
    error: str = ""


async def run_task(task: Task, root: Path, provider: ProviderConfig, make) -> Result:
    world = World(root)
    await task.setup(world)
    if task.kind == "file" and world.env.extractor is None and "pdf" in task.prompt.lower():
        return Result(task.name, task.kind, False, "pdftotext isn't installed", "SKIPPED", None, 0, 0, 0, 0, 0.0)
    driver = Driver(root / "mei", world.env, make, provider)
    started = time.monotonic()
    prompts = denied = questions = 0
    submitted = driver.submit(task.prompt)
    task_id = submitted["task_id"]
    state = ""
    try:
        for _round in range(MAX_ROUNDS):
            state = await driver.until(task_id, timeout=TASK_TIMEOUT_S)
            if state == S.WAITING_APPROVAL:
                card = agent.approval_view(driver.approval(task_id))["card"]
                prompts += 1
                careful_no = any(r.get("provenance") == "untrusted" for r in card.get("resources", []))
                denied += careful_no
                driver.approve(task_id, decision="deny" if careful_no else "allow")
            elif state == S.WAITING_INPUT:
                questions += 1
                spec = agent.input_view(agent.pending_input(driver.store, task_id))["spec"]
                driver.answer(task_id, spec["choices"][0] if spec["choices"] else
                              {f["name"]: (f.get("options") or ["yes"])[0] for f in spec["fields"]} if spec["fields"]
                              else "Yes, go ahead.")
            else:
                break
    except TimeoutError:
        state = "TIMEOUT"
    final = driver.task(task_id)
    reply = _last_reply(driver, submitted["conversation_id"])
    passed, detail = await task.check(world, reply)
    if final["state"] in (S.FAILED, S.INTERRUPTED) and _unavailable(final["error"] or ""):
        passed, state = False, "ERROR"  # the provider was unavailable: says nothing about the model or Mei
    outcome = (final["outcome"] or {}).get("kind")
    calls = driver.store.read_one("SELECT model_calls FROM tasks WHERE id = ?", (task_id,))["model_calls"]
    error = redact(final["error"] or "") if final["state"] in (S.FAILED, S.INTERRUPTED, S.BLOCKED) else ""
    driver.store.close()
    return Result(task.name, task.kind, passed, detail, str(state), outcome, prompts, denied, questions, calls,
                  round(time.monotonic() - started, 1), error)


def _unavailable(error: str) -> bool:
    """Rate limits, outages, and timeouts; not a model's bad tool call, which is a real failure."""
    return any(sign in error for sign in ("HTTP 429", "HTTP 5", "timed out", "connection failed", "no complete reply"))


def _last_reply(driver: Driver, conversation_id: str) -> str:
    shown = [m for m in repo.history(driver.store, conversation_id) if m["role"] == "assistant" and m["content"]]
    return shown[-1]["content"] if shown else ""


def summarize(results: list[Result]) -> dict:
    """Pass rate, prompts per task, and how often a not-verified result was wrong. Tasks the provider
    failed (rate limits, outages) are counted apart: they say nothing about the model or Mei."""
    ran = [r for r in results if r.state not in ("SKIPPED", "ERROR")]
    unverified = [r for r in ran if r.outcome in ("reported", "partially_verified")]
    return {
        "tasks": len(ran),
        "provider_errors": sum(1 for r in results if r.state == "ERROR"),
        "passed": sum(r.passed for r in ran),
        "pass_rate": round(sum(r.passed for r in ran) / len(ran), 3) if ran else 0.0,
        "prompts_per_task": round(sum(r.prompts for r in ran) / len(ran), 2) if ran else 0.0,
        "wrong_reported_rate": round(sum(not r.passed for r in unverified) / len(unverified), 3) if unverified else 0.0,
        "verified_but_wrong": sum(1 for r in ran if r.outcome == "outcome_verified" and not r.passed),
        "outcomes": {k: sum(1 for r in ran if r.outcome == k) for k in
                     ("outcome_verified", "partially_verified", "reported", None)},
    }


async def run_all(tasks: list[Task], provider: ProviderConfig, make, repeat: int = 1, pause: float = 0.0) -> list[Result]:
    results = []
    for _ in range(repeat):
        for n, task in enumerate(tasks):
            if pause and (n or results):
                await asyncio.sleep(pause)  # free tiers limit tokens per minute
            with tempfile.TemporaryDirectory(prefix=f"mei-eval-{task.name}-") as tmp:
                options = {**provider.options, "script": task.script} if provider.id == "fake" else provider.options
                results.append(await run_task(task, Path(tmp), ProviderConfig(
                    id=provider.id, model=provider.model, url=provider.url, options=options), make))
    return results


async def _scripted(cfg: ProviderConfig):
    return FakeProvider(cfg.options)


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", default="fake", help="'fake' (scripted), or a provider id with a key in .env")
    p.add_argument("--model", default="", help="model id (default: the .env's <PROVIDER>_MODEL)")
    p.add_argument("--tasks", default="", help="comma-separated task names (default: all)")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--out", default="", help="write the results as JSON here")
    p.add_argument("--pause", type=float, default=0.0, help="seconds between tasks (for rate-limited free tiers)")
    return p.parse_args(argv)


async def main(argv: list[str]) -> int:
    args = _parse(argv)
    tasks = [t for t in TASKS if not args.tasks or t.name in args.tasks.split(",")]
    if args.provider == "fake":
        results = await run_all(tasks, ProviderConfig(id="fake", options={"delay_ms": 0, "chunk_chars": 200}),
                                _scripted, args.repeat)
        return _report(results, "fake (scripted)", args.out)
    env = load_env()
    key_var, model_var = LIVE.get(args.provider, ("", ""))
    model = args.model or env.get(model_var, "")
    key = env.get(key_var, "") if key_var else ""
    if not model or (key_var and not key):
        print(f"no model or key for {args.provider} in .env ({model_var}, {key_var})")
        return 2

    async def key_for(_pid: str) -> str:
        return key

    async with httpx.AsyncClient(follow_redirects=False) as client:
        async def make(cfg: ProviderConfig):
            return await factory.build(cfg, client, key_for)
        results = await run_all(tasks, ProviderConfig(id=args.provider, model=model), make, args.repeat, args.pause)
    return _report(results, f"{args.provider} {model}", args.out)


def _report(results: list[Result], label: str, out: str) -> int:
    summary = summarize(results)
    for r in results:
        mark = "PASS" if r.passed else {"SKIPPED": "SKIP", "ERROR": "ERR "}.get(r.state, "FAIL")
        print(f"{mark}  {r.task:22} {r.outcome or 'answer':19} prompts={r.prompts} calls={r.model_calls:<2} "
              f"{r.seconds:5.1f}s  {r.detail or r.error}"[:200])
    print(f"\n{label}: {summary['passed']}/{summary['tasks']} passed, {summary['prompts_per_task']} prompts per "
          f"task, wrong-reported rate {summary['wrong_reported_rate']}, verified-but-wrong "
          f"{summary['verified_but_wrong']}, provider errors {summary['provider_errors']}")
    if out:
        Path(out).write_text(json.dumps({"provider": label, "summary": summary,
                                         "results": [asdict(r) for r in results]}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
