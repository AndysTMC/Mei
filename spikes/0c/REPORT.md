# Stage 0c — voice spike report

Date: 2026-10-22. Machine: AMD Ryzen 7 4800H (8 cores, 16 threads; AVX2 and FMA, **no AVX-512 or VNNI**), 14 GiB, NVIDIA RTX 3050 Laptop 4 GB (driver 595). Audio: PipeWire 1.6.2 with pipewire-pulse; one sink (the laptop's analog output), two sources (the laptop's analog input and a Logitech Brio 100 webcam mic). sherpa-onnx 1.13.8 (CPU build, onnxruntime inside), Python 3.12 (uv), in a venv outside the repository.

Throwaway code in this folder; models come from k2-fsa's releases through `fetch_models.sh` (sha256 of each archive is printed when fetched) into `~/.cache/mei-spikes/0c/models`, outside the repository. Nothing here touched the microphone or played sound aloud: test speech is **synthesized** by the TTS models themselves (two Piper voices, six Kokoro voices), so word error rates are for synthetic speech, not a person's voice. The measurements that need the speakers and the microphone are scripted (`aec_test.py`, `false_wake_listen.py`) and wait for the owner.

## Results (CPU unless marked)

### Text to speech: time to the first sentence

Six typical first sentences of a reply ("Sure." to a 15-word sentence), one at a time, as the worker would synthesize them; RTF is synthesis time over audio length.

| Engine | First sentence, median | RTF |
|---|---|---|
| Piper amy-low, 2 threads | 0.142 s (max 0.214) | 0.042 |
| Piper amy-low, 4 threads | 0.105 s (max 0.153) | 0.031 |
| Piper lessac-medium, 4 threads | 0.151 s (max 0.185) | 0.052 |
| Kokoro fp32, 4 threads | 1.403 s (max 1.892) | 0.478 |
| Kokoro fp32, 8 threads | 1.301 s (max 1.88) | 0.446 |
| Kokoro int8, 4 threads | 4.711 s (max 6.364) | 1.584 |
| **Kokoro fp32, GPU (CUDA)** | **0.449 s** (max 0.495) | 0.153 |
| Piper amy-low, GPU (CUDA) | 0.496 s (max 0.517) | 0.142 |

Kokoro int8 is *slower* than fp32 here: this CPU has no AVX-512 or VNNI, so onnxruntime's int8 kernels don't pay off. On the GPU, Kokoro takes 658 MB of VRAM and loads in 1.4 s; Piper gets slower (kernel launches outweigh its tiny model), so it stays on the CPU.

### Speech to text (streaming)

40 commands ("move last week's invoices into the taxes folder") from eight synthetic voices, half with noise at 25 dB SNR, fed in 100 ms chunks, each followed by the 0.8 s of silence the VAD leaves before ending an utterance.

| Model | RTF | Word error rate (synthetic voices) |
|---|---|---|
| Kroko streaming Zipformer (2025-08, 68 MB), 2 threads | 0.023 | **0.12** |
| Zipformer en 20M int8, 2 threads | 0.029 | 0.461 |
| Kroko on the GPU | 0.036 | 0.093 (one Piper voice, no noise) |

Kroko is the one to use, on the CPU (the GPU is slower for 100 ms chunks). With only 0.3 s of trailing silence both models drop the last word or two; the first run of the bench did that, and the WER fell from ~0.21 to ~0.06 for a clean voice once the silence matched the endpointing.

### Voice activity and endpointing (Silero)

Minimum silence 0.7 s: the utterance is closed **0.836 s** after speech ends (max 1.224 s), 40/40 detected, 0.0045 CPU-seconds per second of audio.

### Wake word ("Hey Mei", spoken as "hey may"; sherpa-onnx KWS, gigaspeech 3.3M, int8, 1 thread)

96 utterances "Hey May, <command>" (eight voices × three speeds × four commands, half with noise at 20 dB SNR); 24 "Hey May." alone for the delay; 64 near misses ("they may come later", "hey, maybe tomorrow", "hey man…", "in May…", "okay, may I…", "hey Mike…", "the main thing…", "hey, make it quick"); and 0.49 h of ordinary prose from Mei's own documents (Piper voices), which says "may" a lot.

| Threshold, score | Detected | Fires after the keyword ends | False wakes in prose | Near misses that fired |
|---|---|---|---|---|
| 0.25, score 1.0 | 88/96 | 0.59 s | 0 in 0.493 h | 10/64 |
| 0.35, score 1.0 | 67/96 | 0.545 s | 0 in 0.493 h | 9/64 |
| 0.45, score 1.0 | 36/96 | 0.56 s | 0 in 0.493 h | 6/64 |
| 0.25, score 2.0 | 53/96 | 0.59 s | 0 in 0.493 h | 13/64 |

Idle cost: **2.2 % of one core**. Peak memory of the whole bench process (all models loaded at once): 1670 MB.

**Wake word verdict: not good enough as it is.** At its best setting it hears 92 % of wakes and no false wakes in half an hour of prose, but it fires ~0.59 s after the keyword (target: a listening cue within 0.25 s) and 16 % of near misses ("hey, maybe…", "hey, make it quick") trigger it. The delay is the model's chunking (it decodes in ~0.3 s chunks and needs trailing frames), not tuning.

## Voice worker under its profile (`worker_profile.sh`)

bubblewrap with `--unshare-all`, a cleared environment, `/usr` and the ALSA/PipeWire config read-only, the models read-only at `/models`, the venv and its interpreter read-only, and of `$XDG_RUNTIME_DIR` **only the `pipewire-0` socket**. From inside (`worker_inside.py`):

| Check | Result |
|---|---|
| Network | blocked (`Network is unreachable`); DNS fails |
| The person's files | none visible (only the empty folders leading to the bound venv) |
| Session bus, PulseAudio socket | absent; `/run/user/1000` holds only `pipewire-0` |
| Wake-word model load | ~0.9 s |
| PipeWire graph | sinks and sources listed through `pw-dump` (enumeration only) |
| Playback | `pw-cat --raw` played 0.3 s of silence, exit 0 |
| `sounddevice` (PortAudio) | **fails**: Ubuntu's PortAudio starts its PulseAudio host API first and gives up when the Pulse socket is missing |

**With the GPU** (`worker_profile.sh --gpu`): the same jail plus the NVIDIA device nodes (`/dev/nvidiactl`, `/dev/nvidia0`, `/dev/nvidia-uvm*`) and the CUDA libraries from the GPU venv. Kokoro ran on CUDA from inside: loaded in 2.8 s, first sentence **0.475 s**, network still blocked. Device nodes give access to the GPU, not to the network or the person's files.

So the worker talks to PipeWire natively (`pw-cat`/`pw-record` subprocesses, or libpipewire bindings), not through PortAudio. Exposing the Pulse socket instead would be the wrong fix: the PulseAudio protocol lets a client load server modules.

Note: PipeWire treats a client in a plain bubblewrap jail like any host process (its portal access control applies to Flatpak apps), so the worker can open any source. That is the voice worker's job; the core decides when it listens, and the Shell shows GNOME's microphone indicator.

## Stopping playback (`playback_stop.py`)

Killing the `pw-cat` stream takes 1.5 ms (max 2.9 ms over 20 runs). After that, about one graph quantum still plays: the quantum here is 1024 samples at 48 kHz, **21.3 ms**, plus the sound card's own buffer. That leaves the plan's "<150 ms from detection to silence" ample room; the acoustic figure comes from the barge-in run of `aec_test.py`.

## The latency budget (end of speech → first spoken audio, target < 1.5 s)

| Step | CPU only | With the GPU for Kokoro |
|---|---|---|
| Endpoint: VAD sees 0.7 s of silence | 0.84 s | 0.84 s |
| Final transcript after the endpoint (streaming, already decoded) | ~0 | ~0 |
| Model: first sentence of the reply (fast cloud model, measured per provider in Stage 5) | 0.3–0.8 s | 0.3–0.8 s |
| TTS first sentence | Piper 0.1 s / Kokoro 1.3 s | Piper 0.1 s / Kokoro 0.45 s |
| Playback start (one quantum) | 0.02 s | 0.02 s |
| **Total** | **Piper ≈ 1.3–1.8 s**; Kokoro ≈ 2.5–3 s | Kokoro ≈ 1.6–2.1 s |

Only Piper, on a fast model, gets near the target as planned. The endpoint is the biggest single cost: Stage 5 should end the utterance sooner (0.4–0.5 s of silence, confirmed by the recognizer's own endpoint rule) and start the model on the final transcript at once. Synthesizing the first clause rather than the whole first sentence trims Kokoro's share too.

## What this means for Stage 5 (decision 0017)

- **One interface per part, local and cloud behind each**: audio in and out, wake word, VAD, speech to text, text to speech. Settings choose; at least one backend of each must work well.
- **Defaults here**: Kroko streaming STT on the CPU; Silero VAD on the CPU; Piper for speech by default (instant), Kokoro as the natural-sounding choice, on the GPU when one is usable and on the CPU otherwise ("slower to start"). Device by measurement, not by rule: the GPU helps only the large model.
- **GPU when available, CPU otherwise**: each backend probes for a working GPU (CUDA libraries load, a test inference runs) and falls back to the CPU on any failure, saying so in Settings. The GPU build of the engine (~0.45 GB) plus cuDNN (~0.8 GB) is an optional download offered by the Voice setup step only when an NVIDIA GPU is present.
- **Audio through PipeWire's own protocol**, not PortAudio, so the worker needs only the `pipewire-0` socket.
- **Wake word**: push-to-talk first, as planned. sherpa's keyword spotter is a backend, but it misses the latency target and fires on near misses; a dedicated wake-word model (openWakeWord, a small custom "Hey Mei" model) is the backend to measure next, behind the same interface.
- **Cloud speech** (OpenAI, Deepgram, Gemini, ElevenLabs) runs in the core as planned; the worker never gets the network.

## Echo cancellation and barge-in, with the owner (2026-10-22, `results/aec.json`)

- **Laptop speakers, laptop mic:** the echo canceller cut Mei's voice by 15 dB, but what was left still looked like speech two-thirds of the time. A later 3 s silence check found why: the laptop mic's hardware capture gain was at 100% (+30 dB), so silence alone measured −3.4 dB and 19.5% of samples clipped. Those runs are void. The rule that stands: on laptop speakers, interrupting is by shortcut, because talking over Mei's speech isn't reliable with the speakers that close to the mic.
- **The fix:** capture gain at 51% (`amixer -c 3 sset Capture 51%`): silence −29.5 dB, no clipping. The Brio webcam mic was clean as it was (−28.7 dB). Stage 5's Voice setup step should check the mic's level in silence and offer to fix an overdriven one.
- **Earphones:**

| Mic | Mei speaking, person silent: what's left / speech detected | Person talking over Mei: level / speech detected |
|---|---|---|
| Laptop (gain fixed) | −51.6 dB / **0 %** | −17.8 dB / 53 % |
| Brio | −49.2 dB / **0 %** | −28.4 dB / 44 % |

With earphones, Mei hears none of itself and hears the person talking over it: barge-in by voice works on both mics. The barge-in delay (speech onset to silence) wasn't measured; the person's speech has no marked onset in these runs.

## False wakes on room audio, with the owner (2026-10-22, `results/false_wake.json`)

The owner stopped the run after **0.26 h** (about 16 minutes) of ordinary use on the laptop mic (gain fixed): **0 false wakes** at threshold 0.25. That is too short to set a rate against the 8 h target. Together with 0 in 0.49 h of synthetic prose, it is encouraging for false wakes, but the near-miss and latency problems above still stand.

## Word error rate on the owner's voice (2026-10-22, `results/own_voice.json`)

The owner read the 20 commands from `bench.py` into the laptop mic (gain fixed), about a second apart; Silero split the recording, Kroko transcribed each piece. **WER 14 %** over the whole sequence, against 12 % on synthetic voices.

Most errors are the **last word of an utterance cut short** ("meeting" → "meet", "Monday" → "Mon", "bigger" → "big", "ready" dropped), plus a few mishearings ("dark" → "Doc"). The same cut shows on synthetic speech fed the same way, so it is the pipeline, not the voice: the VAD's segment ends close to the last word, and the recognizer needs more audio after it. Stage 5 should keep ~0.3 s of audio past the VAD's end of speech and feed the stream continuously instead of per segment. Two short pauses were too short for the VAD to split (two commands came out as one), which is fine for a real assistant.

## Waiting for the owner

- ~~Echo cancellation~~ done above. **Echo cancellation with the laptop speakers** (`aec_test.py`): loads PipeWire's WebRTC echo canceller only for the test, plays ~8 s of synthesized speech aloud, records the microphone raw and through the canceller with nobody speaking, and reports the echo reduction and how often VAD mistakes the echo for speech; `--barge-in` repeats it while the person talks over Mei. Recordings stay in memory; only numbers are written.
- **False wakes on 8 h of room audio** (`false_wake_listen.py --hours 8`): runs the wake-word model on the microphone for a day of ordinary use and counts triggers. No audio is kept.
- **Word error rate on the owner's voice**: needs the owner reading a few commands.
