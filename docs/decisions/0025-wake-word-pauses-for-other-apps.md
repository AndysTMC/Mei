# 0025. "Hey Mei" pauses while another app records

Status: accepted
Date: 2026-10-23
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

With the wake word on, Mei holds the microphone all the time (0018). During a call or a recording, that means two apps hold it. GNOME's microphone indicator then can't say which one is listening, and Mei might wake on the call's own words. The owner asked for "Hey Mei" to step aside while another app records, without the microphone being opened to find out.

## Decision

- **The core watches PipeWire's graph with `pw-dump --monitor`.** It reports each change as it happens and opens no audio, so nothing polls the whole graph. It runs only while the wake word is armed: voice on, "Listen for 'Hey Mei'" on, this setting on, the screen unlocked.
- **"Another app recording"** is a `Stream/Input/Audio` node that is not one of these:
  - Mei's own: its recorders are named `mei.microphone`, and its echo canceller's nodes start with `mei.` (0024).
  - A capture of what the speakers play (`stream.capture.sink`, `stream.monitor`).
  - A level meter the Shell also skips: GNOME's sound settings, pavucontrol.
- **While one exists,** the core tells the worker to disarm the wake word. Mei's stream closes, so the indicator shows only the other app, and voice's status says "Paused while another app uses the microphone". When the last one ends, the wake word re-arms. Push to talk works meanwhile. A reload of the worker while paused stays paused.
- **If `pw-dump` stops,** Mei can't tell, so the wake word comes back rather than staying paused on stale news. It restarts `pw-dump` after 1, 5, then 30 s, saying so in the status, and gives up after that, still saying so. A run that lasted a minute starts the back-off afresh.
- **Settings:** "Pause while another app records", under "Listen for 'Hey Mei'", on by default.

## Consequences

- During a call, "Hey Mei" doesn't answer; the shortcut does.
- An app that keeps a capture stream open without using it (some browsers after a call) keeps the wake word paused until it closes that stream. GNOME shows such an app as recording too.
- Not yet checked with a real call and the owner at the machine. The tests replay `pw-dump --monitor` output recorded in a private PipeWire.
