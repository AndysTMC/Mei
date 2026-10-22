# 0019. The GPU on demand: woken when used, let go when idle, with the CPU covering meanwhile

Status: accepted
Date: 2026-10-23
Deciders: owner
Supersedes: 0018 (in part: "voice never uses the GPU")
Superseded-by: —

## Context

0018 dropped the GPU. To be quick, Kokoro would have to stay loaded there, and an open CUDA context keeps a laptop's NVIDIA GPU powered for as long as voice is on. The owner then asked for something different. The GPU may serve speaking, listening, local models, or anything else that gains from it, but only on demand: it wakes when used and sleeps after some idle minutes, each use restarting the clock, and the CPU covers until it is awake. Quality and a seamless experience come first.

Measured on the owner's laptop (Ryzen 7 4800H, RTX 3050 4 GB) with `runtime/tests/voice_bench.py --only gpu`:
- **Waking the GPU voice** (process start, CUDA, Kokoro loaded and warmed): 2.4 s median, 3.8 s on a cold disk cache.
- **First sentence once awake:** 448 ms, against 1.37 s on the CPU.
- **Memory:** 642 MiB of GPU memory while awake.

Spike 0c found the GPU slower for listening (Kroko and Silero work on 100 ms chunks) and for Piper. Kokoro is the only voice part that gains.

## Decision

- **A shared mechanism:** `mei/ondemand.py`. A costly resource starts on first use, or when warmed ahead of use. It stays while used and stops after an idle time, each use restarting the clock. A failed start is reported and tried again on the next use. Voice uses it now; local models can use it later.
- **The GPU only where measured to help.** Today that is Kokoro, the natural voice. Listening and the quick voice stay on the CPU.
- **The GPU voice runs in a process of its own** inside the voice worker's jail. Ending that process is what lets the card sleep; unloading a model inside a long-lived process doesn't release the CUDA context. It is woken when listening starts, while the person talks and the model thinks (usually 2–4.5 s, against a 2.4 s wake). It is let go after `gpu_idle_min` minutes unused (default 5, Settings 1–60).
- **The CPU covers, in the same voice.** Any sentence due before the GPU is awake, or after it fails, is said by Kokoro on the CPU, so nobody hears a switch. A GPU that won't start, or that stops, is said once in voice's status.
- **The engine is an optional download, offered only with an NVIDIA GPU:**
  - What: sherpa-onnx's CUDA 12 build from its author's wheel repository, and NVIDIA's CUDA runtime, cuBLAS, cuDNN and NVRTC from PyPI. ~1.9 GB to download, ~2.9 GB unpacked.
  - How it's checked and placed: every wheel is pinned by URL, size and sha256 and checked before unpacking. Wheels are unpacked member by member (no absolute paths, `..`, or links) into a staging folder that becomes the engine in one rename. It can be removed from Settings.
  - Where it's used: only the GPU voice process puts it on its import path.
- **The jail** gains the NVIDIA device nodes and the engine folder (read-only) only while the settings may use the GPU and the engine is present. The worker restarts when that changes, since a jail can't widen in place.
- **Settings** (natural voice with an NVIDIA GPU): "Use the graphics card" (on by default once the engine is downloaded), "Let it sleep after" (minutes), and the engine's row with Download or Remove.

## Consequences

- The first answer after a long idle can come before the GPU is awake. Its first sentence then takes the CPU's ~1.4 s, and the next sentences are quick.
- The CPU Kokoro stays loaded beside the GPU one (RAM, not GPU), so the cover is always ready.
- The same mechanism is how a future local model or GPU listener would be woken and let go.
- Settings shows the 1.9 GB size before downloading.
