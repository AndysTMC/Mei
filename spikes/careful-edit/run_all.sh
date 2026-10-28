#!/usr/bin/env bash
# Every option, one process each, one after another (never two at once: they share the CPU).
# Needs fetch_models.sh, then `python audio.py tts|kroko|moonshine-tiny|moonshine-base` for the audio rows.
set -euo pipefail
cd "$(dirname "$0")"
P=${MEI_SPIKE_PY:-$HOME/.cache/mei-spikes/careful-edit/venv/bin/python}
models="t5-tiny t5-mini t5-small-gec t5-small-synth t5-base qwen2.5-0.5b qwen3-0.6b lfm2.5-1.2b"
for o in rules-seam rules+ punct-en punct-ct $models; do $P bench.py "$o"; done
for o in punct-en+guard punct-ct+guard $models; do $P bench.py "$o" --input rules; done
for o in "punct-en+guard>t5-tiny+guard" "punct-en+guard>t5-small-gec+guard" "t5-tiny+guard>punct-en+guard"; do
    $P bench.py "$o" --input rules
done
for o in punct-en+guard t5-tiny t5-mini t5-small-gec "punct-en+guard>t5-tiny+guard" qwen2.5-0.5b; do
    $P bench.py "$o" --input rules --threads 2
done
for o in rules-seam rules+; do $P bench.py "$o" --input kroko; done
for o in rules+ punct-en+guard t5-tiny "punct-en+guard>t5-tiny+guard" t5-small-gec t5-base qwen2.5-0.5b; do
    $P bench.py "$o" --input kroko+rules
done
$P score.py > results/table.txt
