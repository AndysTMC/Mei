# 0018. Voice as built: push to talk first, cloud speech falls back to this computer, and no echo cancellation yet

Status: accepted
Date: 2026-10-22
Deciders: owner (delegated)
Supersedes: —
Superseded-by: 0019 (in part: the GPU); 0021 (in part: echo cancellation)

## Context

0017 set the shape of voice: one interface per part, with local and cloud backends behind each, the device chosen by measurement, and PipeWire's own protocol. Stage 5 built it. Building it settled questions 0017 and §11 left open. In three places it does less than §11 says, and this record says where.

The owner asked for voice that feels like an everyday phone assistant: press, talk, hear the answer, with nothing missing. They also asked that at least one backend behind each interface works well. That rules out failing silently when a cloud provider is down.

## Decision

- **Push to talk is the way in.** `Super+Alt+Space` or the popup's mic button starts listening. Pressing again means "done talking", and Esc or Stop hushes Mei. The wake word ("Hey Mei", sherpa's keyword spotter) sits behind the same interface but stays off by default: it is ~0.6 s late against the 0.25 s target. The second wake-word backend 0017 named has not been built yet.
- **When an utterance ends:** after 0.5 s of quiet (Settings: 0.3–2.0 s), or when the person presses again. Quiet counts from when the speech ended, not from when the detector noticed (Silero takes 0.1 s to notice). The recognizer then gets 1.2 s of silence at once (~40 ms of compute). With less, Kroko drops the last word or two, which was the cut-off the owner heard in spike 0c. The recognizer's own endpoint rule isn't used.
- **After a spoken answer, Mei listens once more** without a press (6 s), so a follow-up needs no shortcut. With the wake word, a follow-up within 5 minutes continues the same conversation.
- **Cloud speech falls back to this computer, per utterance and per sentence.** If the cloud provider can't answer (no key, offline, an HTTP error), Kroko writes down what was said and Piper says the reply. Voice's status says why until the cloud answers again. So Silero, Kroko, and a Piper voice are always kept, even when cloud speech is chosen. Kokoro tries the GPU and falls back to the CPU, saying why.
- **A cloud voice name that belongs to another provider** (after switching between them) means that provider's default voice, not an error.
- **Stop words never reach the model.** "Stop", "cancel that", "never mind", and a few more cancel the running task. Any other utterance during a task joins it as a steer, as §11.4 says.
- **Spoken approvals follow §11.6 exactly.** Mei reads the action back and asks for "yes, do it" (or "yes, go ahead") only when its effects are local, recorded for undo, private, not sent off the machine, and lose no data. Anything else is "I need your OK for that. It's on screen." The card stays on screen either way. A spoken approval is recorded as `decided_by=voice`, for this action only.
- **A locked screen suspends voice:** the microphone closes, and nothing is heard until unlock.
- **No echo cancellation yet, so barge-in is off by default.** §11.4's echo-cancel source isn't loaded. Talking over Mei is reliable with earphones, and Settings says so. With speakers, the shortcut stops Mei. Barge-in itself is as §11.4 says: 0.2 s of speech after a 0.3 s grace window, the last 0.8 s handed to listening. The 0.2 s counts from when the speech began, in the detector's 32 ms windows; stacking it on Silero's own 0.15 s cost ~100 ms and missed the target. Playback stops by ending the output stream, not by a ramp.
- **Mei never records.** §11.5's "Keep voice recordings" isn't built. Audio lives in memory only, and the worker's jail has nowhere to write but a private tmpfs.
- **Models** come from k2-fsa's sherpa-onnx releases at pinned URLs and sha256 digests. The core downloads them (the worker has no network) over HTTPS only, checks size and digest before unpacking, extracts with tarfile's `data` filter, and moves them into place atomically.
- **The engine installs with Mei.** `install.sh` installs `mei-runtime[voice]`: sherpa-onnx, its onnxruntime, and numpy, ~35 MB. Where the engine has no build, Mei installs without voice and says so. The GPU build is an optional download, used on demand (superseded by 0019).
- **Devices are chosen by PipeWire node name,** which stays the same across sessions, unlike node ids. The list comes from `pw-dump`, which opens no audio. A chosen device that isn't plugged in stays chosen and is marked "not connected" rather than silently switching.
- **The microphone check** measures 3 s of silence and reports only numbers: level, peak, and clipping. Fix sets the chosen microphone's capture level to 50 % with `wpctl`, then measures again.

## Measured

On the spike's machine (Ryzen 7 4800H, RTX 3050), from recorded speech, with `runtime/tests/voice_bench.py --trials 20`, and the model's time to a short reply from `MEI_LIVE_CHAT=1 npm run smoke:providers`:

| Measure | Median | p95 | Target (§4) |
|---|---|---|---|
| End of speech → final text | 678 ms | 748 ms | — |
| First sentence synthesized, Piper (CPU) | 149 ms | 155 ms | — |
| First sentence synthesized, Kokoro (CPU; the runtime's engine has no GPU build) | 1367 ms | 1494 ms | — |
| Barge-in: speech onset → playback stopped | 286 ms | 294 ms | <350 ms: 20/20 (max 302 ms) |
| A real output stream stopping, after that | 2 ms | 2 ms | (plus ≤20 ms of PipeWire buffer) |

End of speech → first spoken audio is therefore about 830 ms plus the model's time to its first sentence:

| Provider (model) | Short reply | End of speech → first audio, with Piper | <1.5 s |
|---|---|---|---|
| Groq (gpt-oss-20b) | 413 ms | ~1.24 s | met |
| Gemini (gemini-flash-lite-latest) | 1735 ms | ~2.6 s | missed |
| OpenRouter (openrouter/free) | 9824 ms | ~10.7 s | missed |

One request each, with a minimal prompt. Mei's real prompt is larger, so these are lower bounds. Kokoro on the CPU adds ~1.2 s over Piper.

## Consequences

- Voice works with no cloud key and keeps working when a cloud provider fails. Cloud choices cost a ~125 MB local download even so.
- Stage 5's acceptance is met except for:
  - **Barge-in with speakers.** Echo cancellation needs a PipeWire echo-cancel source, measured with the owner's speakers.
  - **Wake-word latency, and false wakes on 8 h of room audio.** Both need the owner's recordings and a better backend.
  - **The 1.5 s target with slower providers.** Only a fast provider (Groq here) meets it. §11.3's separate fast model for voice turns isn't built yet.
- Each of these is a follow-up behind an interface that already exists.
