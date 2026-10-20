# 0004. Install per user with a script; the extension activates at the next login

Status: accepted
Date: 2026-10-20
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Mei needs a runtime service (0002) and a matching Shell extension. The owner wants a one-command install like opencode or Hermes Agent (`curl … | bash`). On Wayland, GNOME Shell reads the extensions folder only at login: Stage 0a confirmed that a running Shell reports a freshly copied extension as nonexistent, that it is discovered after a Shell restart, and that `gnome-extensions enable` then activates it at once. A real-session test (copy, add to `enabled-extensions`, log out and in) showed the Shell enabling the extension on its own 0.5 s into the new session, and the nested test agreed once it used the system `gsettings` (`spikes/0a/REPORT.md`, results 16 and 19).

## Options

- A. extensions.gnome.org only.
- B. Distro packages only.
- C. A per-user install script, with packages and extensions.gnome.org added later.

## Decision

C. `install.sh` checks requirements without changing anything (and never runs `sudo`), installs `uv` if needed, installs a pinned `mei-runtime`, and runs `mei-runtime install`. That writes the systemd user unit and D-Bus activation file, copies the matching extension to `~/.local/share/gnome-shell/extensions/mei@andystmc.com/`, and adds it to `enabled-extensions`. The script ends with "Log out and back in (or restart) to finish." System GNOME tools are always called by absolute path (`/usr/bin/gsettings`, `/usr/bin/python3`): on machines with Homebrew, Nix, or conda, the `gsettings` on PATH may lack the dconf backend and silently read defaults and drop writes.

(Amended the same day after the real-session test: an earlier draft added a one-shot first-login unit to call `EnableExtension`. It isn't needed, and it also had a bug: it waited for `org.gnome.Shell.Extensions` to have an owner, but that name is served on demand and has none until someone calls it.)

## Assumptions

- [A1] One log-out after the first install is acceptable (owner confirmed).
- [A2] The script is served over HTTPS from a domain the project controls, wrapped in a function, with pinned versions and published checksums.

## Consequences

Installing works the same on every GNOME 50+ distro, without root, with one log-out. extensions.gnome.org remains a later channel (it can load without a log-out), subject to its review rules, including the rule against AI-generated submissions.

## Revisit if

A GNOME release stops honouring `enabled-extensions` for newly discovered extensions at login, or distro packages become the main channel.
