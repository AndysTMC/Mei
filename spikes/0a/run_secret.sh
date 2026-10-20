#!/usr/bin/env bash
# Stage 0a: Secret Service spike against a throwaway gnome-keyring on a private bus.
# The private XDG_RUNTIME_DIR hides the real keyring daemon (found via $XDG_RUNTIME_DIR/keyring)
# and must be short: Unix socket paths are limited to 108 bytes. Usage: run_secret.sh <python> <data-dir>
set -u
PY=$1; DATA=$2; HERE=$(cd "$(dirname "$0")" && pwd)
RT=$(mktemp -d "/run/user/$(id -u)/mks.XXXX")
trap 'rm -rf "$RT"' EXIT
chmod 700 "$RT"; mkdir -p "$DATA"
env -u GNOME_KEYRING_CONTROL -u SSH_AUTH_SOCK XDG_RUNTIME_DIR="$RT" XDG_DATA_HOME="$DATA" \
  dbus-run-session -- bash -c '
    gnome-keyring-daemon --foreground --components=secrets --unlock <<< "spike-password" > "$XDG_DATA_HOME/daemon.log" 2>&1 &
    for _ in $(seq 1 25); do
        gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
            --method org.freedesktop.DBus.NameHasOwner org.freedesktop.secrets 2>/dev/null | grep -q true && break
        sleep 0.2
    done
    "$0" "$1/secret_spike.py"
  ' "$PY" "$HERE"
