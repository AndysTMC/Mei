# 0007. The agent loop keeps a durable action ledger; waiting is a state, and recovery is a table

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

Stage 3 gives Mei tools. A tool call can change the person's files and settings, so the loop has to survive a crash, a Shell restart, an approval that waits for hours, and a person who changes their mind mid-task, without running anything twice and without breaking the provider's rule that every tool call gets exactly one result before the next request. This is ADR candidate 4 (architecture §7, §8.2, §15).

## Options

- Keep tool calls in memory and re-plan after a restart: simple, but a crash after a file moved and before its result was stored either repeats the move or loses it.
- An event-sourced log replayed into state: complete history, but every read pays for a replay, and the store already keeps a journal of events.
- A ledger of explicit records (batches, actions, approvals, input requests) written in the same transaction as the state they describe, with pure transition checks.

## Decision

The ledger. In `runtime/src/mei/store/agent.py` and `core/`:

- An assistant message with tool calls creates a **batch**, and all of its **actions** are stored as PROPOSED in the same transaction as the message. The batch has a durable cursor.
- An action has three separate fields: execution state, verification state, and effect disposition (§7.3). Execution changes are checked against `check_action_transition`.
- An action is marked STARTED (with the runtime's epoch) in its own committed transaction before its side effect. Its result, its tool-result message, and the cursor move are one transaction. Every terminal state, including SKIPPED and SUPERSEDED, gets exactly one tool-result message, so the stored transcript is valid for every provider.
- Waiting for an approval or an answer is a task state (WAITING_APPROVAL, WAITING_INPUT). No coroutine is held. Answering resumes the loop, which finds the open batch and continues at its cursor.
- A new message while a task runs joins that task as a **steer**. Unstarted actions are skipped, a pending card is superseded, and the model reads the message next.
- **Recovery** (`core/recovery.py`) is the §15 table. An action STARTED under an old epoch becomes IN_DOUBT. On resume it is re-run if it is idempotent, otherwise its capability probes the world, and if the probe can't tell, the person is asked. A one-time approval doesn't outlive the runtime. A task that was running comes back INTERRUPTED, and the person resumes it: the model is never re-called automatically, because the request may already have been billed.

## Assumptions

- [A1] One runtime writes the store (the writer lock from 0002), so transactions are the only concurrency control needed.
- [A2] Capabilities that aren't idempotent can probe their effect well enough to settle most IN_DOUBT cases. The file tools can; desktop actions (Stage 6) will often answer "unknown" and ask.

## Consequences

`tests/test_recovery.py` kills the runtime at every durable boundary (model call, reply stored, decision, action started, action ran, result stored) and checks that each case recovers as the table says, with the file moved exactly once. `tests/test_agent_loop.py` runs the batch scenario from §20 (approve, deny, steer, cancel, kill while waiting), and every request in each case passes a provider-validity check. Messages gained a `tool` role, which required rebuilding the table (migration 3).

## Revisit if

Mei runs actions in parallel within a batch (the cursor assumes order), or a second process needs to write the store.
