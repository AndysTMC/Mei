"""The eval suite with the scripted model: every task's reference script must pass its own world
check, so a live failure is the model's, not the harness's (§20)."""

import pytest

from evals.run import Result, run_all, summarize, _scripted
from evals.tasks import TASKS
from mei.protocol import ProviderConfig

SCRIPTED = ProviderConfig(id="fake", options={"delay_ms": 0, "chunk_chars": 200})


async def test_every_reference_script_passes_its_check():
    results = await run_all(TASKS, SCRIPTED, _scripted)
    failed = [(r.task, r.detail, r.error) for r in results if not r.passed]
    assert not failed
    by_task = {r.task: r for r in results}
    assert by_task["invoices_last_week"].outcome == "outcome_verified" and by_task["invoices_last_week"].prompts == 0
    assert by_task["dark_mode_and_files"].outcome == "outcome_verified"
    injection = by_task["readme_injection"]
    assert (injection.prompts, injection.denied) == (1, 1)  # the hijacked call reached a card, and was refused
    assert 10 <= len(TASKS) <= 15


@pytest.mark.parametrize("name", ["shopping_list", "invoices_last_week", "dark_mode_and_files", "volume_30"])
async def test_a_model_that_only_claims_success_fails_the_check(name):
    task = next(t for t in TASKS if t.name == name)
    claims = type(task)(task.name, task.kind, task.prompt, task.setup, task.check, [{"text": "Done! All taken care of."}])
    [result] = await run_all([claims], SCRIPTED, _scripted)
    assert not result.passed and result.outcome is None


def test_summary_metrics():
    def r(passed, outcome, prompts=0):
        return Result("t", "file", passed, "", "COMPLETED", outcome, prompts, 0, 0, 1, 0.1)
    summary = summarize([r(True, "outcome_verified", 1), r(False, "reported"), r(True, "reported"),
                         r(False, "outcome_verified"), r(True, None, 1)])
    assert summary["pass_rate"] == 0.6 and summary["prompts_per_task"] == 0.4
    assert summary["wrong_reported_rate"] == 0.5 and summary["verified_but_wrong"] == 1
