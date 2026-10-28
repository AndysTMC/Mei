# Voice samples

The same three sentences in each voice, one WAV per voice, for the owner to listen to before choosing an engine. Nothing here was played aloud.

> Good morning. It's 7 degrees and cloudy, with rain likely after 3 this afternoon.
> I found two emails from Priya about Thursday's review. Do you want me to read the newer one?
> Done. I've set a timer for twenty-five minutes, and I'll stay quiet until it ends.

Piper and Kokoro run exactly as Mei runs them (`mei.voice.local`, sherpa-onnx 1.13.8, Piper on 2 threads, Kokoro on 4, CPU only), from the models Mei downloads (`mei.voice.models`, hashes checked). Each sentence is synthesized on its own, as Mei speaks a reply, and the WAV joins them with a 0.6 s pause. `synth.py` makes them; `results-sherpa.json` has the raw numbers.

## Results (AMD Ryzen 7 4800H, 8 cores / 16 threads)

| Engine | Voice | File | Size on disk | Time to synthesize (3 sentences) | Audio | Real-time factor |
|---|---|---|---|---|---|---|
| Piper | Amy (low, 16 kHz), Mei's default | `piper-amy.wav` | 81 MB | 1.35 s | 17.3 s | 0.08 |
| Piper | Lessac (medium, 22 kHz) | `piper-lessac.wav` | 81 MB | 1.15 s | 13.7 s | 0.08 |
| Kokoro v0.19 | af: default blend (American, woman) | `kokoro-af.wav` | 369 MB for all voices | 11.4 s | 15.1 s | 0.76 |
| Kokoro v0.19 | af_bella: Bella (American, woman) | `kokoro-af_bella.wav` | (same model) | 12.4 s | 14.8 s | 0.84 |
| Kokoro v0.19 | af_sarah: Sarah (American, woman) | `kokoro-af_sarah.wav` | (same model) | 15.7 s | 15.4 s | 1.02 |
| Kokoro v0.19 | am_michael: Michael (American, man) | `kokoro-am_michael.wav` | (same model) | 17.7 s | 16.4 s | 1.08 |
| Kokoro v0.19 | bf_emma: Emma (British, woman) | `kokoro-bf_emma.wav` | (same model) | 16.0 s | 15.1 s | 1.06 |
| Kokoro v0.19 | bm_george: George (British, man) | `kokoro-bm_george.wav` | (same model) | 16.9 s | 16.5 s | 1.03 |
| KittenTTS | – | – | – | not run (see below) | – | – |

Real-time factor is synthesis time over audio length: below 1 is faster than speech. Each sentence was synthesized five times after a warm-up, and the fastest run counts.

**The machine was busy.** Other work ran throughout: load average 9 at the start, 25 at the end, on 16 threads. Kokoro's voices share one model, so the spread between its rows (0.76–1.08) is that noise, not the voices. On a quiet machine, spike 0c measured Kokoro at RTF 0.48 on 4 threads, Piper Amy at 0.04 on 2 threads and Piper Lessac at 0.05 on 4 (`spikes/0c/REPORT.md`). Read the table as an upper bound, and the spike as the expected figure.

Check: Mei's own speech-to-text (Kroko) transcribed every file back to the script, digits as "seven" and "three". Its few misses ("in cloudy" for "and cloudy" on three Kokoro voices) are the recognizer's, not the voices'. No file clips (peak 0.38–0.88).

## KittenTTS: not run yet

The install into a throwaway scratchpad venv was refused by this session's permission check, so no KittenTTS files are here. `kitten.py` is ready. It runs KittenTTS's lightweight ONNX models (0.8: mini, micro, nano int8) with the same sentences, timing and four threads, and writes `kitten-*.wav` and `results-kitten.json`. Its docstring has the venv commands (`kittenml==0.9.6 --no-deps` plus onnxruntime, phonemizer, espeakng_loader, soundfile, numpy, huggingface_hub; nothing goes into the project). Model sizes from the KittenTTS README: mini 80 MB, micro 41 MB, nano 56 MB (fp32) / 25 MB (int8).

KittenTTS 2, the flagship (1.7B parameters, 0.5–1 GB of weights), was left out. It needs PyTorch, even through its C++ bindings, which is far outside Mei's footprint. The 0.8 ONNX models are the ones comparable to Piper and Kokoro.

## Reproduce

```bash
runtime/.venv/bin/python spikes/voice-samples/synth.py --models ~/.local/share/mei/voice/models --models <folder with vits-piper-en_US-lessac-medium> --out spikes/voice-samples
```

Lessac isn't in Mei's basic download. It came from the same pinned release URL and sha256 as `PIPER["lessac"]` in `mei/voice/models.py`, into a scratch folder.
