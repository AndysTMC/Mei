# 0003. Talk between Shell and runtime over the session bus with dbus-fast

Status: accepted
Date: 2026-10-20
Deciders: owner (via the agent architecture review)
Supersedes: —
Superseded-by: —

## Context

The Shell extension and the runtime (0002) have independent lifecycles. The UI must reconnect after Shell restarts, extension disable/enable, and runtime crashes without losing or duplicating state, and must stay responsive while answers stream.

## Options

- A. Session D-Bus.
- B. A Unix socket with a custom protocol.
- C. stdio to a child process.
- D. A localhost HTTP/WebSocket server.

For the Python side of A: dbus-fast (pure pip install, asyncio) or PyGObject (system bindings).

## Decision

A, with dbus-fast in the runtime. Well-known name `com.andystmc.Mei1`, object `/com/andystmc/Mei1`, interface `com.andystmc.Mei1.Runtime`. Methods take and return one JSON string; `ReadArtifact` is the one exception and returns `(sh)` with a read-only fd. Events are a single `Event(s)` signal sent **unicast** to attached clients, with one global sequence number; `Attach(scope, after_seq)` returns a snapshot then replays missed events. D-Bus is delivery only: durability and ordering come from the runtime's store.

Stage 0a measured this (`spikes/0a/REPORT.md`): unicast events invisible to other bus clients, 1,000-event bursts applied in ~25 ms, reattach with zero gaps, fd transfer ~1 ms. dbus-fast beat PyGObject on call latency (0.08 vs 0.21 ms) and, unlike PyGObject, installs from wheels into any Python. PyGObject remains the right tool in the desktop worker, which runs on the system Python for AT-SPI.

## Assumptions

- [A1] Event rates stay in the hundreds per second (deltas are coalesced at 33 ms).
- [A2] Same-user processes are outside the threat model; approvals are still accepted only from the gnome-shell process.

## Consequences

Activation, crash detection (`NameOwnerChanged`), and peer identity come from the bus. dbus-fast 5.2.0 drops its own connection when the socket buffer is momentarily full (EAGAIN treated as fatal; reproduced 3/3 under load, also upstream). The runtime pins dbus-fast and applies a small patch at start-up that waits for writability instead (`spikes/0a/dbus_fast_patch.py`), refusing to start on an unpatched version, until upstream fixes it. Event emission is also bounded: deltas are coalesced and lagging clients are told to re-attach. The client must ignore `bus_watch_name`'s initial "vanished" callback, and the runtime must exit on bus loss (`EOFError`) so systemd restarts it. B, C, and D are rejected: B rebuilds activation and identity, C ties the runtime to the Shell, D adds ports and auth for no benefit.

## Revisit if

Payloads or event rates outgrow D-Bus (for example, live audio or video to the UI), in which case add a side channel rather than replacing the control protocol.
