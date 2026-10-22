#!/usr/bin/env bash
# Spike 0c: fetch the sherpa-onnx models measured in REPORT.md into ~/.cache/mei-spikes/0c/models
# (outside the repository). Re-running skips what is already there. Prints each archive's sha256.
set -euo pipefail
base=https://github.com/k2-fsa/sherpa-onnx/releases/download
dest=${MEI_SPIKE_MODELS:-$HOME/.cache/mei-spikes/0c/models}
mkdir -p "$dest"
cd "$dest"
fetch() {  # tag file
    [ -e "$2" ] || [ -e "${2%.tar.bz2}" ] || curl -fsSL --retry 3 -o "$2" "$base/$1/$2"
    if [ -e "$2" ]; then
        sha256sum "$2"
        case "$2" in *.tar.bz2) tar xjf "$2" && rm "$2" ;; esac
    fi
}
fetch kws-models sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2
fetch asr-models silero_vad.onnx
fetch asr-models sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06.tar.bz2
fetch asr-models sherpa-onnx-streaming-zipformer-en-20M-2023-02-17.tar.bz2
fetch tts-models vits-piper-en_US-amy-low.tar.bz2
fetch tts-models kokoro-int8-en-v0_19.tar.bz2
fetch tts-models kokoro-en-v0_19.tar.bz2
fetch tts-models vits-piper-en_US-lessac-medium.tar.bz2
du -sh "$dest"/*
