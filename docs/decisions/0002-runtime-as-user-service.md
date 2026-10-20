# 0002. Run the agent in a separate Python user service; the extension is UI only

Status: accepted
Date: 2026-10-20
Deciders: owner (via the agent architecture review)
Supersedes: —
Superseded-by: —

## Context

Mei is becoming an agent that plans, acts on the desktop, talks, and remembers. Today all of that would run inside `gnome-shell`: `src/extension.ts` owns the HTTP session, provider, messages, persistence, and cancellation, and `disable()` tears it all down. GNOME may call `disable()` at any time (lock screen, updates, Shell restarts). Any blocking work in the Shell freezes the desktop, and GTK can't be loaded there.

## Options

- A. Keep everything in the Shell process.
- B. A child process spawned by the extension.
- C. An independent user service (systemd user unit, D-Bus activated) that owns all agent state; the extension only renders and sends commands.

## Decision

C. The runtime is a Python 3.12+ service in a uv-managed environment, started by D-Bus activation, owning tasks, providers, policy, memory, and the store. Provider configuration moves into the runtime (SQLite); GSettings keeps only UI preferences. The extension holds no canonical state and makes no network calls once Stage 2a lands.

Stage 0a measured this on GNOME 50.1 (`spikes/0a/REPORT.md`): cold activation from the extension ~370 ms, call round trip ~0.2 ms, the service survives Shell restarts and extension disable/enable, and the Shell reattaches with no lost events.

## Assumptions

- [A1] Users accept a separately installed service (install script, §21.2 of the architecture doc). Revisit if extensions.gnome.org starts requiring self-contained extensions.
- [A2] Python start-up (~370 ms) is acceptable on the first call after login.

## Consequences

Two languages (TypeScript UI, Python runtime) joined by a versioned protocol. Provider code is ported to Python in Stage 2a and then deleted from the extension. B is rejected because a child process dies with the Shell; A because agent work can't depend on the Shell's lifetime.

## Revisit if

GNOME offers a supported way to run long-lived extension work outside the compositor, or the service model proves unworkable on a target distro.
