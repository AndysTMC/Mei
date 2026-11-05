#!/usr/bin/env bash
# Record Mei's demo in a nested GNOME Shell of its own (1920×1080, headless): never the real session.
# A private home, XDG dirs, runtime dir, session bus, PipeWire with no devices (the Shell's screencast
# needs one), and a throwaway keyring for the model's key, read from .env and never printed.
# Voice comes from a file and goes to a file: nothing opens a microphone or plays a sound.
# Usage: scripts/demo-record.sh [--out <folder>] [scene...]   (no scene: all)
#   --out: a demo folder of its own (default demo/), with its own copy of the scenes (<folder>/demo.py,
#   copied from runtime/tests/e2e/demo.py the first time): edit that copy, not the original.
# Output: <folder>/clips/NN-name.mp4, report.json, logs. Demo folders are kept out of git.
set -euo pipefail

main() {
    local root out py port run demo=demo
    root=$(cd "$(dirname "$0")/.." && pwd)
    if [ "${1:-}" = "--out" ]; then demo=${2:?--out needs a folder}; shift 2; fi
    demo=${demo%/}
    case "$demo" in /*|*..*) echo "--out takes a folder inside the repo, like demo-codex"; return 1;; esac
    py="$root/runtime/.venv/bin/python"
    [ -x "$py" ] || { echo "run 'uv sync --extra voice' in runtime/ first"; return 1; }
    grep -qx "/$demo/" "$root/.git/info/exclude" 2>/dev/null || echo "/$demo/" >> "$root/.git/info/exclude"
    mkdir -p "$root/$demo/clips" "$root/$demo/voiceover"
    [ -e "$root/$demo/demo.py" ] || cp "$root/runtime/tests/e2e/demo.py" "$root/$demo/demo.py"
    out=$(mktemp -d -t mei-demo.XXXXXX)
    export MEI_VOICE_MODELS=${MEI_VOICE_MODELS:-$HOME/.cache/mei-spikes/0c/models}
    export MEI_DEMO_DIR="$root/$demo" MEI_DEMO_ENV="$root/.env"

    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache \
        "$out"/home
    # One build at a time: several demo runs share dist/. Each takes its own copy while holding the lock.
    (
        flock 9
        cd "$root" && npm run build:dev >/dev/null
        cp -a "$root/dist" "$out/data/gnome-shell/extensions/mei@andystmc.com"
    ) 9>"$root/.git/demo-build.lock"
    printf '[D-BUS Service]\nName=com.andystmc.Mei1\nExec=%s -m mei serve\n' "$py" \
        > "$out/data/dbus-1/services/com.andystmc.Mei1.service"

    port=$("$py" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
    export HOME="$out/home" XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" \
        XDG_CACHE_HOME="$out/cache"
    export GSETTINGS_BACKEND=keyfile MEI_DATA_DIR="$out/mei" MEI_DEV_HOOKS=1 MEI_DEMO=1 MEI_LOG_LEVEL=info
    mkdir -p "$out/voice"
    export MEI_VOICE_SOURCE_FILE="$out/voice/heard.f32" MEI_VOICE_SINK_FILE="$out/voice/played.f32"
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei@andystmc.com']"
    run=$(mktemp -d /tmp/mei-rt.XXXXXX)
    chmod 700 "$run"
    unset PIPEWIRE_REMOTE PIPEWIRE_RUNTIME_DIR PULSE_SERVER PULSE_RUNTIME_PATH
    export XDG_RUNTIME_DIR="$run"
    trap "status=\$?
        for _ in 1 2 3 4 5; do
            fusermount3 -uz '$run/doc' 2>/dev/null || true; fusermount3 -uz '$run/gvfs' 2>/dev/null || true
            rm -rf '$run' 2>/dev/null && break
            sleep 1
        done
        if [ -e '$run' ]; then echo \"warning: couldn't remove $run\" >&2; fi
        rm -rf '$out' 2>/dev/null || true
        exit \$status" EXIT
    echo "demo session: $out"
    dbus-run-session -- "$py" "$root/$demo/demo.py" "$out" "$port" "$@" 2>"$root/$demo/demo.stderr"
}

main "$@"
