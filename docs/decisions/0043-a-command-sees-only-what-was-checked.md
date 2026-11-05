# 0043. A command gets a folder only if it was checked for secrets in full, and the watch starts first

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: 0016 (in part: a folder too large to scan only said so; only names new after the start counted)
Superseded-by: —

## Context

Decision 0016 masks the secret files in each folder a command mounts, found by a walk that stops at 20,000 entries, and watches for new ones while the command runs. A review reproduced two gaps with the real jail:

- **The walk's limit.** Past it, the command still ran with the whole folder mounted, and only a note was added to its result. A `.env` in the part not walked was read inside the jail.
- **The order.** The command started first and the watch after it, on the assumption that whatever was there by then had been masked. A secret written in between (by the command, or saved after the walk) was neither masked nor seen. And when the command's end and a trip were both ready, the end won, so its output went to the model.

## Decision

- **A folder that couldn't be checked in full isn't given to a command.** The command is refused before it starts, with a note to use a smaller folder inside it. A higher limit would only move the edge.
- **The watch starts before the command.** The folders are watched first, then what is already in them is compared with what was masked. A secret that wasn't masked (it landed after the walk) stops the command before it starts.
- **A trip counts at the end too.** After the command ends, Mei reads whatever the watch has queued, and a secret that appeared still withholds the output, even though the end was seen first.

## Consequences

`tests/test_shell.py`: a folder past the limit is refused and its nested `.env` never reaches the model; a `.env` saved between the walk and the start stops the command; a command that writes a secret and ends before Mei looks still has its output withheld. These fail against the code before this decision.

Very large folders (a home-sized tree, a big monorepo) now need a narrower folder.

## Known limits

- **The watch is reactive.** It stops a command once a secret file appears, but a command with network access can send bytes before that. Preventing that needs stronger isolation (a filtered view of the folder, or no network while secrets could appear), not a faster watch.
- Past 4,096 folders the watch is still incomplete and says so (0016).
