#!/usr/bin/env bash
# End-to-end test in a nested GNOME Shell on a private session bus (Stage 1 chat, Stage 3 agent).
# Nothing touches the real session: a private home and XDG dirs, keyfile GSettings, a stub keyring.
# The driver configures the provider through the runtime, as Settings does.
# Usage: scripts/e2e-stage1.sh [output-dir]
set -euo pipefail

main() {
    local root out py port
    root=$(cd "$(dirname "$0")/.." && pwd)
    out=${1:-$(mktemp -d -t mei-e2e.XXXXXX)}
    py="$root/runtime/.venv/bin/python"
    [ -x "$py" ] || { echo "run 'uv sync' in runtime/ first"; return 1; }
    # Voice (Stage 5): the spike's models, and files instead of the microphone and speakers (test-only).
    export MEI_VOICE_MODELS=${MEI_VOICE_MODELS:-$HOME/.cache/mei-spikes/0c/models}

    (cd "$root" && npm run build:dev >/dev/null)
    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache \
        "$out"/home/Music "$out"/home/Downloads
    echo "an old file" > "$out/home/Music/old.txt"  # for the approval-card scenario
    rm -rf "$out/data/gnome-shell/extensions/mei@andystmc.com"
    cp -a "$root/dist" "$out/data/gnome-shell/extensions/mei@andystmc.com"
    printf '[D-BUS Service]\nName=com.andystmc.Mei1\nExec=%s -m mei serve\n' "$py" \
        > "$out/data/dbus-1/services/com.andystmc.Mei1.service"
    # Shadow the system keyring service so the nested session can't reach the real keyring.
    printf '[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/bin/false\n' \
        > "$out/data/dbus-1/services/org.freedesktop.secrets.service"

    port=$("$py" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
    # A private home too: the agent scenarios run real file and app actions.
    export HOME="$out/home" XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" \
        XDG_CACHE_HOME="$out/cache"
    export GSETTINGS_BACKEND=keyfile MEI_DATA_DIR="$out/mei" MEI_DEV_HOOKS=1 MEI_LOG_LEVEL=info
    mkdir -p "$out/voice"
    export MEI_VOICE_SOURCE_FILE="$out/voice/heard.f32" MEI_VOICE_SINK_FILE="$out/voice/played.f32"
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei@andystmc.com']"
    # A private runtime dir too: the nested session's sockets (Wayland, the accessibility bus) must not
    # land in, or replace, the real session's (at-spi/bus there is the person's accessibility bus).
    # Short, for socket paths' 108-byte limit. Nothing of the real one is linked in: not even PipeWire,
    # so nothing here can reach the person's microphone, camera or speakers.
    local run
    run=$(mktemp -d /tmp/mei-rt.XXXXXX)
    chmod 700 "$run"
    unset PIPEWIRE_REMOTE PIPEWIRE_RUNTIME_DIR PULSE_SERVER PULSE_RUNTIME_PATH
    export XDG_RUNTIME_DIR="$run"
    # Expanded now (run is local). The private document portal's and GVFS's FUSE mounts may outlive the
    # session.
    # The session's own daemons (AT-SPI, GVFS) can still be exiting, and writing here, after the bus is
    # gone: retry for a few seconds. The run's result stays the checks', never the cleanup's.
    trap "status=\$?
        for _ in 1 2 3 4 5; do
            fusermount3 -uz '$run/doc' 2>/dev/null || true; fusermount3 -uz '$run/gvfs' 2>/dev/null || true
            rm -rf '$run' 2>/dev/null && break
            sleep 1
        done
        if [ -e '$run' ]; then echo \"warning: couldn't remove $run\" >&2; fi
        exit \$status" EXIT
    echo "e2e output: $out"
    dbus-run-session -- "$py" "$root/runtime/tests/e2e/shell_e2e.py" "$out" "$port" 2>"$out/e2e.stderr"
}

main "$@"
