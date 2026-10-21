# 0009. Outcomes are checked by the runtime; badges claim only what checks established

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

Models say "done" when they aren't. An action that ran without error doesn't prove the person's request is satisfied either: a file can land in the wrong folder. A UI that shows "Done ✓" on the model's word teaches people to trust something unchecked. This is ADR candidate 9 (architecture §8.5).

## Options

- Show the model's summary as the outcome: simple, and as reliable as the model.
- A second model call to judge the first: costs a request, and a model grading a model gives confidence it hasn't earned.
- Acceptance criteria with typed checks the runtime runs itself; everything else labelled as reported.

## Decision

- Before its first change, the model records **acceptance criteria** with `plan.update`. A criterion may carry a typed check from a closed set: `file_exists`, `file_absent`, `dir_contains`, `setting_equals`, or `window_present` (through the Shell bridge). Criteria appear in the task's header card.
- A task that changed anything ends with `task.finish`. The runtime runs every typed check against the world as it is now, never against what earlier actions reported. A failed check goes back to the model once. On a second failure the task completes as `partially_verified`, with the failure listed.
- The outcome is `outcome_verified` only when every criterion passed a runtime check. It is `partially_verified` when some did or one failed, and `reported` when none could be checked. A model that changes things and doesn't call `task.finish` gets one nudge, then the task completes as `reported`. Pure answers carry no badge.
- Each capability also checks its own postcondition after it runs (a read-back or a stat). A failed postcondition is told to the model and shown on the action's row.

## Assumptions

- [A1] Most Stage 3 requests can be expressed in the closed check set. The evals measure how often they are.
- [A2] A check that can't run (no Shell attached for `window_present`, no GSettings) is `unverifiable`, never `passed`.

## Consequences

Badges in the popup say "Verified by Mei", "Partly verified", or "Reported, not checked". The eval suite (`runtime/evals/`) scores tasks by the world they leave behind and reports how often a task that wasn't verified was actually wrong (the wrong-reported rate), and how often a verified one was (which should be zero).

## Revisit if

The wrong-reported rate stays high for common tasks (add checks), or Stage 6–7 actions need checks the closed set can't express (element state, URL reached).
