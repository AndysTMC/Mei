# 0014. File changes go through the folders policy judged, held open; a link can't redirect them after the check

Status: accepted
Date: 2026-10-22
Deciders: owner (delegated)
Supersedes: 0010 (in part: its first known limit, the symlink swap between the re-check and the write)
Superseded-by: —

## Context

Decision 0010 binds authority to where a path really leads and checks an action's resources again just before it runs. It left one gap open: a folder on the way swapped for a link in the moment between that re-check and the write. The file capabilities acted on paths, so the kernel followed the new link. Reproduced against the Stage 4 code: with `~/Documents/proj` swapped for a link to another folder right after the re-check, a named write, edit, move, and folder creation all landed in the other folder, and a trash took the other folder's file.

## Decision

- **The run acts on what was judged.** The loop hands each file action the paths policy recorded for it, re-checked just before the run. The run resolves the path it was given and refuses as `changed` if it now leads anywhere else.
- **No link on the way.** A judged path has no links in it (it was resolved). The run walks it from `/` one folder at a time with `O_NOFOLLOW`, creating missing folders as it goes when the action makes them, and holds the last folder open. A link anywhere on the way stops the walk as `changed`.
- **Everything after is relative to the held folder** (`openat`, `renameat`, `mkdirat`, `unlinkat`), and the last component is never followed: files are read and replaced with `O_NOFOLLOW`, written as a temp file renamed into place, and moved with `renameat2(RENAME_NOREPLACE)`, so a move or a new file never replaces anything, even something that appears meanwhile. Where a file system can't promise "no replace", the rename checks first. A move across drives copies and then removes through the held folders, creating each new file exclusively and copying links as links. The trash's `files` and `info` folders are reached the same way.
- **Moving or trashing a link moves or trashes the link.** Policy judges the place a link leads to, and the run still checks that. But a move or a trash acts on the item itself, as a rename does, not on the file it points to. Writing or editing through a link changes the file it points to, which is what policy judged. Before, it replaced the link with a copy.
- **Backups are taken from the file the run holds open**, not from the path again.

## Consequences

`tests/test_security.py` swaps the folder after the re-check for each of write, edit, move, trash, and make-folder, and once more between the run's own check and its walk: each fails as `changed`, nothing outside changes, and without a swap the same requests succeed. Against the code before this decision, all five of the first group changed the outside folder. Unit tests cover the walk (links, files in the way, creation), no-replace renames with and without `renameat2`, a move across drives into a held folder whose path was swapped, and moving and trashing a link.

## Known limits

- Reads (`fs.read_text`, listing, search, PDF text) and checks still go by path: a swap after the check could show Mei a different file than the one judged. The disclosure rules still apply to what it reads, but the file could be another one.
- `shell.run` binds the named folders into its sandbox by path when it starts; a swap in that moment binds wherever the link leads.
- The held folder is the one that was at the judged path when the run opened it; if that folder is itself renamed elsewhere during the run, the change lands in it at its new place.
