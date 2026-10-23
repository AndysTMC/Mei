#!/usr/bin/env bash
# Spike 0b: a probe inside a private, headless GNOME Shell with two virtual monitors, the same
# isolation as the e2e test (private home and XDG dirs, keyfile GSettings, a private session bus, no
# keyring). Nothing touches the real session: no screen of the person's is captured or driven.
# Usage: spikes/0b/run.sh <probe> [output-dir]    (probe: atspi | coords | portals | worker)
set -euo pipefail

main() {
    local root out probe
    root=$(cd "$(dirname "$0")/../.." && pwd)
    probe=${1:?probe name}
    out=${2:-$(mktemp -d -t mei-0b.XXXXXX)}
    (cd "$root" && npm run build:dev >/dev/null)
    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache "$out"/home
    rm -rf "$out/data/gnome-shell/extensions/mei@andystmc.com"
    cp -a "$root/dist" "$out/data/gnome-shell/extensions/mei@andystmc.com"  # its dev hooks: screenshots, clicks
    printf '[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/bin/false\n' \
        > "$out/data/dbus-1/services/org.freedesktop.secrets.service"
    printf '[D-BUS Service]\nName=com.andystmc.Mei1\nExec=/bin/false\n' \
        > "$out/data/dbus-1/services/com.andystmc.Mei1.service"  # no runtime: the probes talk to the desktop
    export HOME="$out/home" XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" \
        XDG_CACHE_HOME="$out/cache" GSETTINGS_BACKEND=keyfile MEI_DEV_HOOKS=1
    unset DISPLAY WAYLAND_DISPLAY
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei@andystmc.com']"
    /usr/bin/gsettings set org.gnome.desktop.interface toolkit-accessibility true
    # A private runtime dir too: the nested session's sockets (Wayland, the accessibility bus) must not
    # land in, or replace, the real session's (at-spi/bus there is the person's accessibility bus).
    # Short, for socket paths' 108-byte limit. Nothing of the real one is linked in: not even PipeWire,
    # so nothing here can reach the person's microphone, camera or speakers.
    local run
    run=$(mktemp -d /tmp/mei-rt.XXXXXX)
    chmod 700 "$run"
    unset PIPEWIRE_REMOTE PIPEWIRE_RUNTIME_DIR PULSE_SERVER PULSE_RUNTIME_PATH
    export XDG_RUNTIME_DIR="$run"
    # Expanded now (run is local). The private document portal's FUSE mount may outlive the session.
    trap "fusermount3 -uz '$run/doc' 2>/dev/null; rm -rf '$run'" EXIT
    echo "0b $probe output: $out"
    dbus-run-session -- /usr/bin/python3 "$root/spikes/0b/$probe.py" "$out" 2>"$out/probe.stderr"
}

main "$@"
