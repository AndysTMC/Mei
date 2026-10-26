#!/usr/bin/env bash
# Careful-edit spike: fetch every model measured in REPORT.md into ~/.cache/mei-spikes/careful-edit/models
# (outside the repository, on disk rather than tmpfs so RAM numbers stay honest). Re-running skips what is there.
set -euo pipefail
dest=${MEI_SPIKE_MODELS:-$HOME/.cache/mei-spikes/careful-edit/models}
mkdir -p "$dest"
cd "$dest"
gh=https://github.com/k2-fsa/sherpa-onnx/releases/download
sherpa() {  # tag archive
    [ -e "${2%.tar.bz2}" ] || { curl -fsSL --retry 3 -o "$2" "$gh/$1/$2" && sha256sum "$2" && tar xjf "$2" && rm "$2"; }
}
hf() {  # repo dir file...
    local repo=$1 dir=$2; shift 2
    mkdir -p "$dir"
    for f in "$@"; do
        [ -e "$dir/$(basename "$f")" ] || curl -fsSL --retry 3 -o "$dir/$(basename "$f")" "https://huggingface.co/$repo/resolve/main/$f"
    done
}
# 2. Punctuation and casing
sherpa punctuation-models sherpa-onnx-online-punct-en-2024-08-06.tar.bz2
sherpa punctuation-models sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2
# 3. Second-pass recognizers
sherpa asr-models sherpa-onnx-moonshine-tiny-en-quantized-2026-02-27.tar.bz2
sherpa asr-models sherpa-onnx-moonshine-base-en-quantized-2026-02-27.tar.bz2
# 4. Grammar correction, T5 at four sizes (int8 ONNX)
hf visheratin/t5-efficient-tiny-grammar-correction t5-tiny-visheratin \
    encoder_model_quant.onnx init_decoder_quant.onnx tokenizer.json config.json
hf visheratin/t5-efficient-mini-grammar-correction t5-mini-visheratin \
    encoder_model_quantized.onnx init_decoder_model_quantized.onnx tokenizer.json config.json
hf JonaWhisper/jonawhisper-gec-t5-small-onnx t5-small-unbabel-gec \
    encoder_model_int8.onnx decoder_model_int8.onnx tokenizer.json config.json
hf Xenova/grammar-synthesis-small t5-small-grammar-synthesis \
    onnx/encoder_model_quantized.onnx onnx/decoder_model_quantized.onnx tokenizer.json config.json
hf Xenova/t5-base-grammar-correction t5-base-vennify \
    onnx/encoder_model_quantized.onnx onnx/decoder_model_quantized.onnx tokenizer.json config.json
# 5. Tiny LLMs in-process (GGUF for llama.cpp)
hf Qwen/Qwen2.5-0.5B-Instruct-GGUF qwen2.5-0.5b qwen2.5-0.5b-instruct-q4_k_m.gguf
hf unsloth/Qwen3-0.6B-GGUF qwen3-0.6b Qwen3-0.6B-Q4_K_M.gguf
du -sh "$dest"/*
