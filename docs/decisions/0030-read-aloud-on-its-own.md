# 0030. Read aloud stands on its own; the voice worker says its version; Stop reaches speech not yet playing

Status: accepted
Date: 2026-10-28
Deciders: owner
Supersedes: 0029 (in part: how Read aloud plays)
Superseded-by: —

## Context

- **Read aloud acted like Live.** 0029 played it as a spoken answer, so voice's state turned to "speaking". The message box turned into Live's status line, and the tone and check-ins could start. The owner wants Read aloud to read the reply and nothing else.
- **The tone was refused.** The owner saw "protocol: Invalid value 'cue'". The `Cue` command existed, but it was missing from the list of commands the worker decodes. The tests drove the check-in timer directly and never sent a cue to a real worker.
- **Old code could outlive an update.** A worker started from older code than the core refuses whatever it doesn't know, and nothing noticed the mismatch.
- **Stop could miss the first sentence.** Stop and the screen lock only stopped speech already playing. A reply whose first sentence was still being synthesized played after Stop (one of the review findings).

## Decision

- **A second speaker in the worker, on its own audio stream, for speech outside any conversation:** Read aloud, and the tone and check-ins while Mei works.
  - It emits no Speaking or Spoken, so voice's state never changes.
  - Nothing listens after it, the wake word doesn't listen to it, and talking over it doesn't stop it.
  - Live starting, a spoken answer starting, Stop (Esc), the screen locking, or a reload end it.
- **Read aloud:**
  - **Commands:** `ReadAloud(id, sentences)` and `StopReading` to the worker. It answers with `Reading(id)` and `ReadDone(id, stopped)`, which the core passes on as the ephemeral event `voice.reading` (protocol 2.5).
  - **Runtime methods:** `VoiceReadAloud(text, message_id)` and `VoiceStopReading`, Shell only.
  - **While Live is on:** Read aloud is refused ("Live is on: end it…").
  - **The button:** the speaker icon becomes Stop ("Stop reading") while its reply is read, and turns back after.
- **The worker says its version** (`wire.VERSION`) in Ready. If it differs from the core's, the core starts the worker again, once. If the new worker differs too, voice is unavailable with "Mei was updated while running: log out and back in to use voice".
- **A test checks every command and event is decodable,** so a new message type can't be left out of its list again.
- **Stop, the screen lock and Live starting stop a reply from its first `say`,** not only once it is audible.

## Consequences

- A reply can be read while voice is idle. It doesn't open the microphone or change the message box.
- The tone can no longer collide with a reply: they use separate streams, and a reply starting ends the tone.
