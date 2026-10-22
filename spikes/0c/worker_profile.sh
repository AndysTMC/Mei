#!/usr/bin/env bash
# Spike 0c: run worker_inside.py under the voice worker's profile (§5.4): models read-only, no
# $HOME, no network, no session bus, and of the runtime dir only the PipeWire socket.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
models=${MEI_SPIKE_MODELS:-$HOME/.cache/mei-spikes/0c/models}
# --gpu: the CUDA venv (gpu_bench.py), the NVIDIA device nodes, and gpu_inside.py instead.
gpu=false; [ "${1:-}" = "--gpu" ] && gpu=true
venv=${MEI_SPIKE_VENV:-$HOME/.cache/mei-spikes/0c/venv}  # uv venv --python 3.12; uv pip install sherpa-onnx==1.13.8 numpy sounddevice
$gpu && venv=$HOME/.cache/mei-spikes/0c/venv-gpu
prefix=$("$venv/bin/python" -c 'import sys; print(sys.prefix)')
base=$("$venv/bin/python" -c 'import sys; print(sys.base_prefix)')
rt=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
extra=() script=worker_inside.py
if $gpu; then
    nv=$prefix/lib/python3.12/site-packages/nvidia
    for dev in /dev/nvidiactl /dev/nvidia0 /dev/nvidia-uvm /dev/nvidia-uvm-tools; do
        [ -e "$dev" ] && extra+=(--dev-bind "$dev" "$dev")
    done
    extra+=(--ro-bind-try /sys/module/nvidia /sys/module/nvidia
            --setenv LD_LIBRARY_PATH "$nv/cuda_runtime/lib:$nv/cudnn/lib:$nv/cublas/lib:$nv/cuda_nvrtc/lib")
    script=gpu_inside.py
fi
exec /usr/bin/bwrap --unshare-all --die-with-parent --new-session --clearenv \
    --setenv PATH /usr/bin:/bin --setenv HOME /nonexistent --setenv XDG_RUNTIME_DIR "$rt" --setenv LANG C.UTF-8 \
    --ro-bind /usr /usr --ro-bind-try /lib /lib --ro-bind-try /lib64 /lib64 --ro-bind-try /bin /bin \
    --ro-bind /etc/ld.so.cache /etc/ld.so.cache --ro-bind-try /etc/alsa /etc/alsa \
    --ro-bind-try /etc/pipewire /etc/pipewire \
    --proc /proc --dev /dev --tmpfs /tmp \
    --ro-bind "$(dirname "$base")" "$(dirname "$base")" --ro-bind "$prefix" "$prefix" \
    --ro-bind "$models" /models --ro-bind "$here/$script" "/$script" \
    --dir "$rt" --bind "$rt/pipewire-0" "$rt/pipewire-0" "${extra[@]}" \
    "$prefix/bin/python" "/$script" "$HOME"
