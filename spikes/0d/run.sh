#!/usr/bin/env bash
# Spike 0d: drag and drop from a Wayland app onto a Shell extension, in a private headless GNOME
# Shell (private home and XDG dirs, keyfile GSettings, a private session bus and runtime dir), the
# same isolation as the e2e test. Nothing touches the real session.
# Usage: spikes/0d/run.sh [output-dir] [scenario-prefixes,comma-separated]
set -euo pipefail

main() {
    local here out run
    here=$(cd "$(dirname "$0")" && pwd)
    out=${1:-$(mktemp -d -t mei-0d.XXXXXX)}
    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache "$out"/home
    rm -rf "$out/data/gnome-shell/extensions/mei-dnd-spike@andystmc.com"
    cp -a "$here/ext/mei-dnd-spike@andystmc.com" "$out/data/gnome-shell/extensions/"
    printf '[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/bin/false\n' \
        > "$out/data/dbus-1/services/org.freedesktop.secrets.service"
    export HOME="$out/home" XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" \
        XDG_CACHE_HOME="$out/cache" GSETTINGS_BACKEND=keyfile MEI_SPIKE_DIR="$here" MEI_DROP_LOG="$out/drop.log"
    unset DISPLAY WAYLAND_DISPLAY
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei-dnd-spike@andystmc.com']"
    # Short, for socket paths' 108-byte limit; nothing of the real runtime dir is linked in.
    run=$(mktemp -d /tmp/mei-rt.XXXXXX)
    chmod 700 "$run"
    unset PIPEWIRE_REMOTE PIPEWIRE_RUNTIME_DIR PULSE_SERVER PULSE_RUNTIME_PATH
    export XDG_RUNTIME_DIR="$run"
    trap "fusermount3 -uz '$run/doc' 2>/dev/null; rm -rf '$run'" EXIT
    echo "0d output: $out"
    dbus-run-session -- /usr/bin/python3 "$here/probe.py" "$out" ${2:-} 2>"$out/probe.stderr"
}

main "$@"
