#!/usr/bin/env bash
# Stage 1 end-to-end test in a nested GNOME Shell on a private session bus.
# Nothing touches the real session: private XDG dirs, keyfile GSettings, and a stub keyring.
# The driver configures the provider through the runtime, as Settings does.
# Usage: scripts/e2e-stage1.sh [output-dir]
set -euo pipefail

main() {
    local root out py port
    root=$(cd "$(dirname "$0")/.." && pwd)
    out=${1:-$(mktemp -d -t mei-e2e.XXXXXX)}
    py="$root/runtime/.venv/bin/python"
    [ -x "$py" ] || { echo "run 'uv sync' in runtime/ first"; return 1; }

    (cd "$root" && npm run build:dev >/dev/null)
    mkdir -p "$out"/data/gnome-shell/extensions "$out"/data/dbus-1/services "$out"/config "$out"/state "$out"/cache
    rm -rf "$out/data/gnome-shell/extensions/mei@andystmc.com"
    cp -a "$root/dist" "$out/data/gnome-shell/extensions/mei@andystmc.com"
    printf '[D-BUS Service]\nName=com.andystmc.Mei1\nExec=%s -m mei serve\n' "$py" \
        > "$out/data/dbus-1/services/com.andystmc.Mei1.service"
    # Shadow the system keyring service so the nested session can't reach the real keyring.
    printf '[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/bin/false\n' \
        > "$out/data/dbus-1/services/org.freedesktop.secrets.service"

    port=$("$py" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
    export XDG_DATA_HOME="$out/data" XDG_CONFIG_HOME="$out/config" XDG_STATE_HOME="$out/state" XDG_CACHE_HOME="$out/cache"
    export GSETTINGS_BACKEND=keyfile MEI_DATA_DIR="$out/mei" MEI_DEV_HOOKS=1 MEI_LOG_LEVEL=info
    /usr/bin/gsettings set org.gnome.shell disable-user-extensions false
    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei@andystmc.com']"
    echo "e2e output: $out"
    dbus-run-session -- "$py" "$root/runtime/tests/e2e/shell_e2e.py" "$out" "$port" 2>"$out/e2e.stderr"
}

main "$@"
