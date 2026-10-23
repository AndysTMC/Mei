#!/usr/bin/env bash
# End-to-end test of computer use (Stage 6) in a nested GNOME Shell. Nothing touches the real session:
# a private home, XDG and runtime dirs, keyfile GSettings, a private session bus, a private unlocked
# keyring (the screen session's restore token goes there), and PipeWire with no devices.
# Usage: scripts/e2e-computer.sh [output-dir]
set -euo pipefail

main() {
    local root out py run
    root=$(cd "$(dirname "$0")/.." && pwd)
    out=${1:-$(mktemp -d -t mei-e2e-computer.XXXXXX)}
    py="$root/runtime/.venv/bin/python"
    [ -x "$py" ] || { echo "run 'uv sync' in runtime/ first"; return 1; }

    (cd "$root" && npm run build:dev >/dev/null)
    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache \
        "$out"/home
    rm -rf "$out/data/gnome-shell/extensions/mei@andystmc.com"
    cp -a "$root/dist" "$out/data/gnome-shell/extensions/mei@andystmc.com"
    printf '[D-BUS Service]\nName=com.andystmc.Mei1\nExec=%s -m mei serve\n' "$py" \
        > "$out/data/dbus-1/services/com.andystmc.Mei1.service"

    export HOME="$out/home" XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" \
        XDG_CACHE_HOME="$out/cache"
    export GSETTINGS_BACKEND=keyfile MEI_DATA_DIR="$out/mei" MEI_DEV_HOOKS=1 MEI_LOG_LEVEL=info
    unset DISPLAY WAYLAND_DISPLAY
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei@andystmc.com']"
    /usr/bin/gsettings set org.gnome.desktop.interface toolkit-accessibility true
    # A private runtime dir: the nested session's sockets (Wayland, the accessibility bus, PipeWire, the
    # keyring) must not land in, or replace, the real session's. Short, for socket paths' 108-byte limit.
    run=$(mktemp -d /tmp/mei-rt.XXXXXX)
    chmod 700 "$run"
    unset PIPEWIRE_REMOTE PIPEWIRE_RUNTIME_DIR PULSE_SERVER PULSE_RUNTIME_PATH
    export XDG_RUNTIME_DIR="$run"
    # Expanded now (run is local). The private document portal's FUSE mount may outlive the session.
    trap "fusermount3 -uz '$run/doc' 2>/dev/null; rm -rf '$run'" EXIT
    echo "e2e (computer use) output: $out"
    dbus-run-session -- bash -c 'echo -n test | gnome-keyring-daemon --unlock --components=secrets --daemonize \
        >/dev/null 2>&1; exec /usr/bin/python3 "$0" "$1"' "$root/runtime/tests/e2e/computer_e2e.py" "$out" \
        2>"$out/e2e.stderr"
}

main "$@"
