# 0015. Reads and the command sandbox use the folders policy judged, held open, too

Status: accepted
Date: 2026-10-22
Deciders: owner (delegated)
Supersedes: 0014 (in part: its first two known limits, reads and the sandbox's folder binds)
Superseded-by: —

## Context

Decision 0014 made file changes act on the judged path through held folders, so a link swapped in after policy's last check can't redirect them. Reads and `shell.run`'s folder binds still went by path. Reproduced against that code with `~/Documents/proj` swapped for a link to another folder right after the re-check: `fs.read_text`, `fs.list`, and `fs.search` sent the other folder's names and contents to the model. With the swap just before the command started, `shell.run` bound the other folder into its sandbox, and `shell.run_host` ran in it. A search also opened files through links inside the searched folder, which reached files nobody judged.

## Decision

- **Reads act on the judged path.** As for changes, the run refuses as `changed` if its path no longer leads where policy judged. It then reaches the file or folder through the held folder (0014). `fs.read_text` reads from a file it opened with `O_NOFOLLOW`. `fs.list` lists the held folder. The sources a read reports (for the disclosure rules and the "read from" line on cards) are the judged paths.
- **PDFs go to the parser by descriptor.** Inside its jail, `pdftotext` gets the opened file through `--ro-bind-fd`. Without a jail it reads `/proc/self/fd/N`, its own copy of that descriptor.
- **Searches never follow links.** `fs.search` walks with `os.fwalk` from the held folder: each folder is entered through its parent's descriptor, links to folders aren't entered, and links to files are listed as links and never opened for their contents. `fs.list` marks links too.
- **The sandbox binds descriptors.** `shell.run` holds each judged folder and the workspace open from before the command starts until it ends, and bubblewrap binds them with `--bind-fd`/`--ro-bind-fd`. bubblewrap checks that what it mounted is the descriptor's own folder (same device and inode) and refuses to start otherwise. The secret scan that decides what to mask walks the held folder the same way. A command naming several folders is checked folder by folder, in order, so a swap can't trade a read-only folder for a writable one.
- **Host commands run in the folder approved.** `shell.run_host` holds its judged working folder open and starts the command in it (`/proc/self/fd/N` as the child's working directory).

## Consequences

`tests/test_security.py` swaps the folder after the re-check for reading text, reading a PDF, listing, and searching: each fails as `changed`, and nothing from the other folder reaches the model's requests. It also checks that a search doesn't open links inside the folder. `tests/test_shell.py` swaps the folder after it is held but before the sandbox starts: the command sees the judged folder's file, and its writes land there. Swapped right after the re-check, the command never starts. A host command swapped the same way still runs in the approved folder. Against the code before this decision, the sandbox and host cases ran against the other folder, and the text, listing, and search cases sent its contents.

`TextExtractor.pdf_text` now takes an open file instead of a path.

## Known limits

- Completion checks and crash probes (`file_absent`, `dir_contains`, verify, probe) still look by path. A swap could make one report wrongly, but it can't change or send anything.
- Opening files in an app (`apps.launch` with files) hands the app a path, and the app opens whatever that path leads to.
- Masks are worked out when the command starts; a secret file created inside a bound folder while the command runs isn't masked.
- As in 0014, a held folder that is itself moved elsewhere during the run is used at its new place.
