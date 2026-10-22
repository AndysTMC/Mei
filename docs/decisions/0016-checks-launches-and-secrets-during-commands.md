# 0016. Checks, probes, and app launches use what was judged; a secret appearing during a command stops it

Status: accepted
Date: 2026-10-22
Deciders: owner (delegated)
Supersedes: 0015 (in part: its first three known limits)
Superseded-by: —

## Context

Decisions 0014 and 0015 made file changes, reads, and the command sandbox act on the paths policy judged, through folders held open. Three gaps remained:
- Completion checks and an action's own checks and crash probes still looked by path, so a link swapped in while they looked could make them report on another place.
- `apps.launch` handed the app the path as given.
- Secrets in a folder bound into a command's sandbox were masked once, when it started, so a secret file written there during the run was visible to the command.

Each was reproduced against the code before this decision: a swapped look made a `file_exists` check pass, a write's own check passed by reading an identical file outside, an app launched on the swapped folder, and a `.env` saved during a command reached the model in its output.

## Decision

- **Checks look without following links.** Completion checks (`file_exists`, `file_absent`, `dir_contains`) resolve the path once, then walk it with `O_NOFOLLOW` (`fs_at.look`, `fs_at.names`). If a link appears on the way while they look, the check is `unverifiable`: it says it couldn't tell, rather than passing or failing for somewhere else. A swap made before the check starts is the world as it is, and the check reports on it.
- **An action's own checks and crash probes use its judged paths**, like the action did, and read through held folders. After a crash, the loop gives probes the judged paths it recorded. A probe that finds the path changed answers "unknown", so the person is asked.
- **Apps get the judged real path, checked just before launch.** Each file is matched against what policy judged and walked once more without following links, and the app is given the real path. A swap after the check stops the launch as `changed`.
- **A secret appearing during a command stops it.** While a command runs, inotify watches every folder it can see, reached through the held descriptors, including folders it makes. If a new name is one Mei hides (secret files, keys, the places Mei never opens), Mei stops the command at once, deletes its saved output, and tells the model only that it stopped and why. Files already there were masked when it started, so only new ones count. A folder made during the run is checked as soon as it is seen, since files can land in it before the watch does. If inotify drops events, that also stops the command, since a secret could have been among them.
- **A folder too large to scan fully for secrets says so** in the command's result, instead of the scan's limit passing silently.

## Consequences

`tests/test_security.py`: a check whose look is swapped mid-way comes out unverifiable; a write's own check refuses to pass on an identical file outside; an app isn't launched on a swapped folder. `tests/test_shell.py`: a `.env`, or an `id_rsa` in a folder made during the run, stops the command within a fraction of a second, and none of its output or the secret reaches the model. A `.env` already present stays masked, and an ordinary new file changes nothing. All of these fail against the code before this decision.

Watching costs one inotify watch per folder, at most 4,096 per command. Past that, the result says the folders weren't all watched.

## Known limits

- The app opens the file by path after Mei hands it over, so a swap in the moment between the last check and the app's own open isn't caught. Mei can't hold a file open on another process's behalf.
- A command that writes a secret-named file itself (say, `cp .env.example .env` in a writable folder) is stopped too: inotify can't tell who wrote a file. The message says which file, and the person can run that step another way.
- Between a secret appearing and the command being stopped (milliseconds), a command with network access could send it. Without network access, nothing it read leaves.
- As in 0014, a held folder that is itself moved elsewhere during the run is used at its new place.
