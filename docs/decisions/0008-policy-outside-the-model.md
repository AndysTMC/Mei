# 0008. Authority lives outside the model: a policy engine with presets over a fixed floor

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

A model can be wrong, and content it reads can try to steer it (prompt injection). Whether an action goes ahead without asking can't depend on what the model says the action does. People also want different amounts of asking, but no choice of theirs should open the cases a hijacked model would exploit. This is ADR candidates 5 and 13 (architecture §13.2–§13.5).

## Options

- Ask for everything: safe, but people learn to click Allow without reading.
- Let the model declare an action's risk: cheap, but the model is the thing being guarded against.
- A deterministic engine over facts the runtime computes itself, with rules as data (the architecture's `defaults.toml`), or with presets as parameters and the floor in code.

## Decision

A pure engine (`runtime/src/mei/policy/engine.py`) decides allow, ask, or deny from facts the runtime establishes:

- **Effects** are computed by the capability from its parameters and the world (§9.1), never from model text.
- **Resources and their provenance** (`policy/provenance.py`). A path is *user-anchored* when the person named it or a folder holding it. It is *untrusted* when it or a folder holding it appears in content Mei read. Otherwise it is *model-derived*. Apps and settings carry the words that name them ("Files", "dark mode"), so "switch to dark mode" names the setting.
- **Path rules** (`policy/paths.py`). Keys, keyrings, browser profiles, and Mei's own data are hard-denied. Credential files need a card even to read. Changing a whole top-level folder (home, Documents, …) always needs a card. That last rule is an addition to §13.2: it stops "trash ~/Documents" even when the person named Documents for another reason.
- **Presets are parameters, and the floor is code.** Cautious, Balanced (the default), and Hands-off change only whether local changes to named, or home-folder, things go ahead. The floor rows come before any preset or grant is consulted: hard denies, sensitive paths, no-undo data loss, changes to protected folders, unknown effects, and off-machine disclosure involving untrusted values. Their cards offer only "Allow once". This replaces the rule file in the architecture: a data file could express a preset that turns the floor off; code can't.
- **Approvals are bound to the params hash.** Scopes are once, this task, or always (always only for undoable local changes). Only the gnome-shell process can approve or answer (`ipc/peers.py`): its executable must be named `gnome-shell` and not be writable by the user. Settings can list and revoke grants but never create them.
- **Disclosure** (`core/context.py`). File contents go to cloud models only as the Privacy setting says (by default, only from files the person pointed at). Sensitive files need a card that says where the contents go. Untrusted observations are wrapped and marked as data.

## Assumptions

- [A1] Textual provenance is conservative, not data-flow tracking. It removes most needless cards and keeps the ones that matter. It can't follow a path a model assembles from pieces of several documents.
- [A2] Same-user malware is out of scope (§5). The Shell-only check stops casual misuse, not a determined local attacker.

## Consequences

`tests/test_policy.py` runs every floor case under all three presets, with and without grants. In the invoices slice, the PDFs taint the task and still no card is needed. An injected "trash ~/Documents" reaches a card that names the file it came from, and the eval's careful-person policy denies it.

## Revisit if

The Stage 8b evals show the floor asks too often for AUTO mode, or a capability needs a provenance kind the textual check can't establish (for example a value derived from untrusted content but rewritten).
