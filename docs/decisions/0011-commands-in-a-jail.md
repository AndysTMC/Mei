# 0011. Commands run in a per-conversation jail; a writable folder counts as possible data loss; host commands ask every time

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

Stage 4 adds commands (§13.6): builds, conversions, archives, the jobs file tools can't do. A command can do anything its process can reach, and Mei can't tell from the text what it will change. The policy engine (0008, 0010) judges resources, so a command needs resources that bound what it can touch, and the process has to be held to them.

## Decision

- **`shell.run` runs in a bubblewrap jail inside a `systemd-run --user --scope`.** The jail sees `/usr` and `/etc` read-only, a private `/tmp`, the conversation's workspace (also `$HOME`), and only the folders the call names, each read-only unless marked writable. No network unless the call asks, no session bus, a cleared environment. The scope caps memory, CPU, and process count, and stopping it kills everything the command started; the jail's PID namespace does the same if Mei dies.
- **Secrets stay hidden inside named folders.** Files and folders the path rules treat as secrets (`.env`, keys, keyrings) are masked with an empty file or folder. A folder that holds a place Mei never opens (the home folder holds `~/.ssh`) can't be named at all; the call must name a folder inside it.
- **What the policy sees.** Each named folder is a resource (role `folder`, granted as a tree). The workspace is Mei's own and needs no card. A writable folder outside the workspace is `loses_data`: the floor covers it with a task grant at most, never "Always". Network is `off_machine`.
- **`shell.run_host` asks every time and shows the exact command.** It runs unsandboxed, in a scope, with credential-looking variables removed from the environment. Its effects are `unknown`, and the floor's `always_ask` holds under every preset and grant.
- **Output keeps its head and tail** (12 KiB each) in the observation. Everything goes to a spill file in the conversation's artifacts, readable with `shell.output` from an offset. Command output is untrusted file content: it taints the task (0010).
- **Workspaces and spills are deleted with their conversation.**

## Consequences

`tests/test_shell.py` runs escape attempts against the real jail (no home, no network, read-only elsewhere, masked secrets), stops a `sleep 600` and its children within 2 s, and checks the time limit, the spill, the cards, and deletion. The `archive_report` eval runs a real `tar` through the jail.

## Known limits

- Without bubblewrap, `shell.run` isn't offered. Without a user systemd instance, a process group stands in for the scope: there are no resource limits, but stopping still kills the group, and the jail's PID namespace takes the rest.
- A writable folder is all-or-nothing: the command can delete anything in it. The card says so.
- Host commands are as safe as the person's reading of them; the card shows the whole command, and nothing else vouches for it.
