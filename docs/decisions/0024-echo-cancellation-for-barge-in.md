# 0024. Echo cancellation for barge-in: PipeWire's canceller, private, only while Mei talks through speakers

Status: accepted
Date: 2026-10-23
Deciders: owner (delegated)
Supersedes: 0018 (in part: "no echo cancellation yet")
Superseded-by: —

## Context

0018 shipped barge-in without echo cancellation. With speakers, Mei's own voice reaches the microphone, so "Interrupt by talking" is off by default and Settings says it works with earphones. §11.4 planned capture from PipeWire's echo-cancel source (`libpipewire-module-echo-cancel`, WebRTC AEC), loaded by a drop-in that setup would offer. That is a lasting change to the person's audio setup, and the owner's rules allow none without asking. Spike 0c's run with the laptop's speakers is void: the microphone was overdriven.

The measurements below come from a private PipeWire: a daemon and WirePlumber on their own socket, with null devices only (`runtime/tests/pipewire_lab.py`). Mei's voice comes back from a null "speaker" into a virtual "microphone" through a synthetic room's impulse response. A "talker" sink stands in for the person. One three-channel recorder keeps the microphone, the talker and the speaker sample-aligned, so barge-in latency runs from the person's first sample to the last sample Mei played. Nothing played aloud and no real microphone opened.

- **GNOME shows the microphone in use while any recording stream exists, running or not** (the Shell's `_maybeShowInput`). The module's capture streams are passive, so the microphone runs only while something records the canceller's source. They still exist, though, so a canceller that lived as long as voice is on would keep the indicator lit all that time.
- **Rate:** run at 16 kHz, the module removed ~11 dB of the room's echo, and Mei stopped on its own voice. At 48 kHz it removed 30–68 dB, with no such stops.
- **Earphones:** a canceller just started, with no echo to learn from, holds the person's voice down for about a second. Barge-in through it took 0.96 s median, against 0.29 s without it.
- **The real PipeWire path:** with the plain microphone, barge-in took 358 ms median reading 100 ms chunks. 0018's 286 ms came from recorded audio, which leaves out capture, the chunk wait and the stop.
- **Through the canceller** (a laptop on a desk): its own buffering adds 36 ms. It also holds down the start of a voice while Mei talks, more so once it has settled: talking over Mei 4 s in was slower than 1.5 s in.
- **Rooms:** in a laptop-like room (direct sound 6 dB above the reverberation, RT60 0.4 s), Mei never stopped on its own voice: 0 of 32 replies, with the echo at the microphone 6 dB below, or level with, Mei's playback. With a speaker across a lively room (−6 dB, RT60 0.6 s), Mei stopped on its own voice every time, with or without a shorter speech rule.
- **A shorter rule doesn't fix it:** 0.15 s of speech instead of 0.2 s brought the laptop room's median to ~0.33 s but not its tail (~0.58 s), and in louder rooms it let echo through.
- **Robustness:** setting the module's `node.latency` to 256/48000 crashes it (SIGFPE). A quantum another app forces on the graph (64–2048) doesn't.
- **WebRTC's mobile mode** (AECM) missed talk-overs and didn't help with earphones.

## Decision

- **The canceller.** PipeWire's echo-cancel module with its WebRTC plugin, run by `pipewire -c` on a configuration the worker writes into its jail's private `/tmp`. It is a client of the session's PipeWire, so the person's PipeWire configuration is never touched, and its nodes vanish when it ends. Its settings:
  - **Monitor mode:** the reference is the speakers' monitor, so Mei's speech plays straight to the speakers rather than through the canceller, and other sounds playing are removed too.
  - **48 kHz**, mono.
  - **WebRTC's gain control and noise suppression are off**, so what Mei hears changes only by the echo.
  - Its source is `mei.echo-cancel.<random>.source`, at session priority 0, so it never becomes the default microphone. Settings' device list leaves it out.
- **It lives only while the barge-in watch has the microphone:** while Mei talks, with "Interrupt by talking" on. It is not kept for as long as voice is on, because of the microphone indicator. That is also why the worker starts it, not the core: only the worker knows when the watch begins. It runs in the worker's jail and needs nothing from it but `pipewire-0`, which `test_in_its_jail_mei_does_not_hear_itself_through_the_speakers` checks.
- **Only with speakers.** As each reply starts, the worker reads the output's form factor and active route with `pw-dump` (~30 ms, no audio). Headphones, headsets and earpieces mean the plain microphone; anything unknown counts as speakers. A laptop's jack switches its route, so plugging in earphones takes effect at the next reply.
- **The recorder waits for the canceller's source** (`node.dont-fallback`, `node.linger`). A race can never record the plain microphone in its place.
- **Failure falls back, saying so:**
  - **Module or plugin missing:** voice's status ends with "…, so talking over Mei works with earphones only", and the watch uses the plain microphone.
  - **Canceller exits, or gives no audio within 2 s:** that reply has no barge-in (through speakers, the plain microphone would hear Mei at once). The status says why, and from the next reply on the plain microphone is used.
- **The barge-in watch reads Silero's own 32 ms windows instead of 100 ms chunks,** so it decides once enough speech is heard rather than at the end of a chunk. It hands the last 0.8 s to listening, counted by duration. Listening and the wake word keep 100 ms chunks.
- **The rule stays 0.3 s of grace, then 0.2 s of speech,** with or without the canceller.
- **Settings:** "Cancel echo from speakers", under "Interrupt by talking" and shown when that is on, on by default. Its text gives the trade-off: a little processor time while Mei talks, slower than with earphones, and an echoey room can still stop Mei.
- **"Interrupt by talking" stays off by default.** It is not safe without measuring a real room. The lab's speaker is linear, and a laptop's small speakers distort at volume, which a canceller handles worse. A lively room already defeats it in the lab. And a false stop cuts Mei's answer off and leaves it listening, possibly to its own echo. Turning it on by default (when the canceller runs and the output is speakers) waits for `runtime/tests/voice_room.py` at the owner's machine to show two things at usual volume: Mei never stopping on its own voice, and every talk-over caught.

## Measured

`runtime/tests/voice_bench.py --only echo --trials 20`, a laptop-like room (echo 6 dB below playback, direct sound 6 dB above the reverberation, RT60 0.4 s). Half the trials talk over Mei 1.5 s in, half 4 s in.

| Measure | Trials | Median | p95 | Max | Target |
|---|---|---|---|---|---|
| Barge-in, plain microphone (earphones) | 20 | 288 ms | 342 ms | 342 ms | 20/20 under 350 ms |
| Barge-in through the canceller, speakers | 20 | 363 ms | 741 ms | 769 ms | 4/20 under 350 ms (**missed**) |
| Mei stopped by its own voice, with the canceller | 20 replies | 0 | | | 0 |
| … without it | 5 replies | 5 | | | |
| Canceller: start → first audio | 5 | 172 ms | | 173 ms | inside the 0.3 s grace |
| Canceller CPU while Mei speaks | 5 | 2.9 % of one core | | 3.3 % | |

Ryzen 7 4800H. Latency runs from the person's first sample to the last sample Mei played, in the lab's graph. The device's own buffers add ~20–40 ms on real hardware.

With recorded audio (`--only barge-in`, as 0018 measured), the 32 ms watch takes barge-in from 286 ms to 263 ms median (p95 285 ms, 20/20 under 350 ms).

## Consequences

- With earphones, talking over Mei on the real PipeWire path is within §4's 350 ms again, and the canceller isn't used.
- With speakers, talking over Mei works in a laptop-like room, without Mei stopping on its own voice. It misses §4's 350 ms: the canceller's buffering, and the way it holds down the start of a voice while Mei talks, cost ~0.08 s at the median and up to ~0.45 s. The lab tests guard against a regression at 1 s.
- While Mei talks through speakers with barge-in on, the canceller costs ~3 % of one core, and a "Mei (echo cancelled)" input shows in the system's sound settings.
- Open:
  - **The owner's room and speakers:** `voice_room.py` needs the owner at the machine. Speaker distortion isn't simulated in the lab.
  - **Reverberant rooms with distant speakers:** Mei stops on its own voice there.
  - **§4's 350 ms through the canceller.** Possible follow-ups: a double-talk detector comparing the plain microphone with the canceller's output, or a canceller whose suppression can be tuned.
