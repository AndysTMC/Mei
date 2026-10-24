# 0026. Listening ends when the person ends it; an 8 s pause before sending; the shortcut keeps the popup closed

Status: accepted
Date: 2026-10-24
Deciders: owner
Supersedes: 0018 (in part: the 0.5 s end of an utterance, and listening once more for 6 s after a reply)
Superseded-by: —

## Context

0018 ended listening by itself in several places:
- dictation stopped after one utterance;
- a conversation listened once more for 6 s after a reply, then closed;
- an utterance ended after 0.5 s of quiet.

The owner asked for listening to end only when the person ends it, with one exception: when started by the shortcut or "Hey Mei", it ends after 30 s of quiet. They also asked for a longer pause before what was said is sent, and for the shortcut and "Hey Mei" not to open the popup.

## Decision

- **Dictation (the mic)** writes what's said into the message box, utterance after utterance, across pauses, until the mic is pressed again. Nothing is sent. The microphone stays open throughout: one stream, which the lab test confirms. Each utterance adds to the box rather than replacing what came before.
- **A conversation the voice button started** listens again after each reply, with no time limit, until closed: the voice button, Stop or Esc.
- **A conversation the shortcut or "Hey Mei" started** goes on the same way, and ends after 30 s with nothing said. The 30 s count from the end of the person's last words or of Mei's reply; time Mei spends thinking doesn't count.
- **Pressing the shortcut or the voice button while listening:**
  - with someone talking, sends what they said at once;
  - with nothing said, ends listening.
  - Pressing the mic again ends dictation, keeping the words heard so far.
- **The pause that sends what was said** is 8 s by default and adjustable from 0.3 to 10 s. The trade-off is that replies come up to 8 s later unless the person presses again. With a 0.5 s pause, people stopping to think were cut off. Pressing again sends in ~0.15 s, against ~8 s for waiting it out.
  - The setting is renamed `end_pause_ms`. A stored `end_silence_ms` (0.5 s, at most 2 s) is dropped rather than carried over, since it was chosen for the old behaviour.
- **What still closes the microphone, and isn't an ending:**
  - **The screen locking:** 0018's privacy rule. Listening comes back on unlock if a conversation or dictation was going on.
  - **Another app recording (0025):** it gets the microphone, and voice shows "Paused while another app uses the microphone". Mei listens again when that app stops. Pressing the shortcut or a button still listens during a call already going on; a call that starts while Mei listens still takes the microphone.
  - **Mei's own speech**, unless "Interrupt by talking" is on (0024): without that, Mei doesn't listen while it talks, or it would hear itself.
- **The shortcut and "Hey Mei" don't open the popup.** Listening, thinking and speaking show as a mark in the top bar. The popup opens when Mei answers (starts speaking, or finishes on screen) or needs something: an approval or a question. The voice button and the mic are in the popup, so it is open already.

## Consequences

- Spoken replies come up to 8 s later than before unless the person presses again; the Settings text says so.
- The microphone indicator stays on for as long as a conversation or dictation goes on (it is listening), except while paused or locked.
- `"stop"` and `"cancel that"` stop the running task without closing voice.
- Measured in the lab (`runtime/tests/test_voice_sessions.py`): Mei let go of the microphone 44 ms after another app began recording, and took it back 40 ms after that app stopped.
