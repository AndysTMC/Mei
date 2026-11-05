# 0040. The Live bar: dots that follow how loud the person or Mei is

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

In Live, the composer said what voice was doing in words ("Listening…", "Thinking…", "Speaking…"). The owner sketched something to look at instead: a thin bar with light dots that move apart as they talk, and a white bar with dark dots while Mei speaks. They asked for it to look great without being overly animated, with each state behaving its own way, and wanted three things ruled out: dots touching the bar's edges, dots overflowing its width, and a border that looks like a text box. The motion was tried out in a browser prototype first.

## Decision

- **Under the buttons in Live, a bar replaces the status words** for listening, thinking and speaking. The other states (getting ready, paused while another app records, unavailable) keep their words. What the person said still shows as text above. The bar's accessible name says the state in words.
- **Each state has its own look** (`LOOKS` in `src/ui/conversation/voiceBarModel.ts`):
  - **Listening:** an outline only, no fill, with ten light dots. Your voice spreads them apart, stretches them toward short bars and brightens them.
  - **Pausing:** listening that has been quiet for 0.5 s. The same bar, nearly still, with a faint slow wave.
  - **Thinking:** six dots and a calm wave. Sound doesn't move them.
  - **Speaking:** a taller bar, filled in the text colour, with its dots cut out. They follow Mei's voice.

  Moving between states blends over about 160 ms, and dots that a state doesn't use fade out.
- **The motion is physics, bounded by construction:**
  - **Springs:** each dot rides a damped spring (a speed in Hz and a bounce).
  - **Following the sound:** the level follows sound with a quick rise and a slower fall.
  - **Ripple:** sound reaches the inner pair first and the outer pairs later.
  - **Height:** a dot never grows taller than the bar less a margin (at least 2 px), easing toward that limit.
  - **Width:** the row widens evenly up to the bar's rounded ends, so dots never cross or overflow at any width.
- **Loudness, never audio, reaches the Shell:**
  - **Measured:** the voice worker turns each 25 ms into a number from 0 to 1, where −60 dBFS or quieter is 0 and −15 dBFS or louder is 1 (`parts.loudness`).
  - **What it measures:** the person's microphone as each chunk arrives, after noise suppression; Mei's voice for each sentence as it starts playing.
  - **Sent:** the core forwards it as the ephemeral `voice.level` event: `source` (`mic` or `mei`), `levels`, `step_ms`.
  - **Played back:** the extension plays the levels on its own clock. Dictation and Read aloud send none.
- **With animations off in GNOME,** the dots stay put. Only Mei's filled bar still shows when it speaks.

## Consequences

- About 10 small D-Bus signals a second while the person talks, and one per sentence while Mei speaks.
- The bar redraws at the display's rate only while it is shown. It stops when Live ends or the popup closes.
- The looks are constants, not settings. Tuning one is an edit to `LOOKS`, and the model's tests keep every look inside the bar.
