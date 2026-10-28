# 0031. Authority checks are conjunctive and fail closed; content with no source stays local; the Shell is its bus name

Status: accepted
Date: 2026-10-28
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Outside reviews of the code (2026-10-26) found five routes around safeguards that hold elsewhere. Each was checked against the code before this decision:

- **A grant could allow sending data off this computer.** The policy returned an existing task grant for a data-losing or unknown-effect action before it looked at off-machine disclosure. Grants record what they cover, but not what the card said would happen. A folder granted for commands therefore also covered the same command with the network on.
- **The last check before an action runs failed open.** If an action could no longer be judged (its tool turned off, computer use switched off, what it names gone), it ran anyway. When its resources hadn't changed, policy wasn't consulted again, so a revoked grant or a tightened setting went unnoticed. A wait for the person to stop using the computer also came after that check.
- **`shell.output` read any spill.** It treated the model's run id as a filename pattern (`../another-conversation/…`, `*`). Its result named no sources, and the cloud-files filter let file content with no sources through (`all([])`).
- **Local-only memories reached cloud models.** `memory.search` and `memory.forget` put the memory's text in their results. Only automatic recall respected "local only".
- **The Shell check trusted a file name.** Any program called `gnome-shell`, in a file its user can't modify, passed.

## Decision

- **Policy is conjunctive.**
  - Off-machine disclosure is judged before anything a grant made for something else could allow.
  - Only a grant made on a card that said data would leave the computer covers sending (`grants.discloses`, migration 7). Grants from before can't vouch for that, so they ask again.
  - Floors (untrusted disclosure, protected folders, files that run code) apply even when such a grant matches.
- **The recheck is judged again, always, right before the action runs, after any wait.**
  - It still runs when it is allowed, or when the person approved exactly this.
  - What can't be judged ends `POLICY_DENIED`, with the reason.
- **`shell.output` matches a run id as text** (hex, 8–36 characters) against this conversation's own spills, never as a path or a pattern.
  - It reads only as much as the offset and length can reach.
  - A run that spills writes its sources beside the spill, and the output carries them.
- **File content with no source is kept from cloud models.** Clipboard keeps its rule.
- **Memory tools never include a local-only memory's text.** A search says how many it held back. On this computer those memories still reach the model through recall.
- **A Shell-only call must come from the connection that owns `org.gnome.Shell` right now**, and its process must still run `gnome-shell` from a file the user can't modify.

## Consequences

- Some actions that went ahead under an old grant now ask once more: a network command in a folder granted before this change.
- An action whose tool or feature was turned off while it waited doesn't run. The model is told why.
- These remain open:
  - wake-word requests seeing the screen without asking (the owner's call);
  - fuzzy matching for spoken "stop" and "yes, do it";
  - the review findings not yet verified.
