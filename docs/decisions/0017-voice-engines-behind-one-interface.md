# 0017. Voice: one interface per part with local and cloud backends; device by measurement; PipeWire's own protocol

Status: accepted
Date: 2026-10-22
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

ADR-7 in the architecture (§11, §23) proposed local-first voice on sherpa-onnx, with PipeWire echo cancellation, an offline worker, and spoken approval per §11.6, pending spike 0c. The spike (`spikes/0c/REPORT.md`) measured on this machine: Ryzen 7 4800H (AVX2, no AVX-512), RTX 3050 4 GB.

- **Speech to text:** Kroko streaming Zipformer gets 12 % WER on synthetic voices at RTF 0.02 on the CPU. The 20M Zipformer gets 46 %.
- **Silence detection:** Silero closes an utterance 0.84 s after speech ends.
- **Speech:** Piper speaks a first sentence in 0.1 s on the CPU. Kokoro takes 1.3 s on the CPU (its int8 build is slower still on this CPU) and 0.45 s on the GPU. Piper and the speech recognizer are *slower* on the GPU.
- **Wake word:** sherpa's keyword spotter heard 92 % of "Hey Mei"s with no false wakes in half an hour of prose. It fires ~0.6 s after the keyword (target 0.25 s), and 16 % of near misses ("hey, maybe…") trigger it.
- **Audio:** `sounddevice` (PortAudio) won't start without the PulseAudio socket. Native PipeWire clients work with only `pipewire-0`.
- **The jail:** the worker's profile holds (no network, no files, PipeWire only), with CUDA working inside once the NVIDIA device nodes are bound.

Separately, the owner set a rule for all of Mei: one interface per subsystem, with the important backends behind it, local and API both. At least one must work well. Use the GPU when there is one, and the CPU otherwise.

## Decision

- **One interface per part of voice:** audio in and out, wake word, voice activity, speech to text (streaming, with partials), and text to speech (streamed by sentence). Each has local and cloud backends; Settings picks, setup offers sensible defaults, and a backend that fails to load falls back to the next working one, saying so.
- **Backends at first:**
  - **Speech to text:** Kroko (local) and a cloud provider through the core.
  - **Text to speech:** Piper (local, the default for speed), Kokoro (local, the natural-sounding choice), and a cloud provider.
  - **Voice activity:** Silero (local).
  - **Wake word:** sherpa's keyword spotter, plus a dedicated wake-word model to be measured. Until a wake-word backend meets the latency and near-miss targets, wake word stays off by default and push-to-talk is the way in.
- **Device by measurement:** a backend runs on the GPU only where that helped in the spike (today, Kokoro). Each GPU backend checks at load that the CUDA libraries load and a test inference runs, and falls back to the CPU otherwise. The CUDA build and cuDNN (~1.2 GB together) are an optional download, offered only when an NVIDIA GPU is present.
- **Audio through PipeWire's own protocol** (its clients, or libpipewire), never PortAudio's PulseAudio path. The worker's jail holds only `pipewire-0`, plus the NVIDIA device nodes when the GPU is in use. Cloud speech runs in the core, which streams audio frames to and from the worker. The worker never gets the network or credentials.
- **Shorter endpointing:** end an utterance after 0.4–0.5 s of silence, confirmed by the recognizer's own endpoint rule, and start the model on the final transcript at once. The plan's 0.7 s alone costs half the 1.5 s budget.
- Echo cancellation and spoken approvals remain as ADR-7 proposed. AEC quality with laptop speakers, false wakes on 8 h of room audio, and WER on the owner's voice are measured with the owner (scripts in `spikes/0c/`) before Stage 5's acceptance.

## Consequences

Stage 5 builds the interfaces first, then Piper, Kroko, Silero, and push-to-talk as the working path, then Kokoro (GPU/CPU), cloud speech, and wake word behind the same interfaces. Kokoro on the CPU and the current wake-word backend don't meet §4's targets on this machine; Settings says so plainly rather than hiding the choice.
