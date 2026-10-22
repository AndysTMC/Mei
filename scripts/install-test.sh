#!/usr/bin/env bash
# Install test: build a release, then install, re-run, uninstall, and purge it with install.sh in a
# private home on a private session bus. The real session is never touched: the script checks that
# your dconf database, extension folder, and service file are byte-for-byte unchanged afterwards.
# Usage: scripts/install-test.sh [work-dir]
set -euo pipefail

main() {
    local root work real_dconf real_unit real_ext before after fails=0
    root=$(cd "$(dirname "$0")/.." && pwd)
    if [ -n "${1:-}" ]; then mkdir -p "$1"; work=$(cd "$1" && pwd); else work=$(mktemp -d -t mei-install.XXXXXX); fi
    real_dconf="$HOME/.config/dconf/user"
    real_unit="$HOME/.config/systemd/user/mei-runtime.service"
    real_ext="$HOME/.local/share/gnome-shell/extensions/mei@andystmc.com"
    before=$(fingerprint "$real_dconf" "$real_unit" "$real_ext")

    MEI_RELEASE_OFFLINE=1 "$root/scripts/build-release.sh" "$work/release" >/dev/null  # uv is already here
    rm -rf "$work/home" "$work/run"
    mkdir -p "$work/home/.local/share/dbus-1/services" "$work/run"
    chmod 700 "$work/run"
    # Keep the private session away from the real keyring. (The XDG variables below matter: without
    # XDG_DATA_HOME, dbus-daemon finds service files in the real home, not in $HOME.)
    printf '[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/bin/false\n' \
        > "$work/home/.local/share/dbus-1/services/org.freedesktop.secrets.service"

    uv_download_checks "$root" || fails=1
    echo "install test in $work"
    env -i PATH="$PATH" HOME="$work/home" USER="$USER" LANG=C.UTF-8 \
        XDG_RUNTIME_DIR="$work/run" XDG_SESSION_TYPE=wayland GSETTINGS_BACKEND=keyfile \
        XDG_DATA_HOME="$work/home/.local/share" XDG_CONFIG_HOME="$work/home/.config" \
        XDG_STATE_HOME="$work/home/.local/state" XDG_CACHE_HOME="$work/home/.cache" \
        UV_CACHE_DIR="$(uv cache dir)" UV_PYTHON_INSTALL_DIR="$(uv python dir)" \
        MEI_INSTALL_SKIP_CHECK=1 \
        dbus-run-session -- bash "$root/scripts/install-test.sh" --inside "$work" || fails=1

    after=$(fingerprint "$real_dconf" "$real_unit" "$real_ext")
    if [ "$before" = "$after" ]; then echo "ok    the real session is unchanged"; else echo "FAIL  the real session changed"; fails=1; fi
    return $fails
}

# ensure_uv from install.sh, run against a fake uv archive (curl is stubbed: no network): a matching
# checksum installs the program; a mismatch installs nothing.
uv_download_checks() {
    local root=$1 dir good fails=0
    [ "$(uname -m)" = x86_64 ] || { echo "skip  uv download checks (not x86_64)"; return 0; }
    dir=$(mktemp -d)
    mkdir -p "$dir/pkg/uv-x86_64-unknown-linux-gnu" "$dir/work"
    printf '#!/bin/sh\necho fake-uv\n' > "$dir/pkg/uv-x86_64-unknown-linux-gnu/uv"
    chmod +x "$dir/pkg/uv-x86_64-unknown-linux-gnu/uv"
    tar -czf "$dir/uv.tar.gz" -C "$dir/pkg" .
    good=$(sha256sum "$dir/uv.tar.gz" | cut -d' ' -f1)
    (
        curl() { while [ $# -gt 0 ]; do [ "$1" = -o ] && { cp "$dir/uv.tar.gz" "$2"; return 0; }; shift; done; return 1; }
        eval "$(sed -n '/^ensure_uv() {/,/^}/p' "$root/install.sh")"
        uv_cmd() { echo "$tool_bin/uv"; }
        local UV_VERSION=0.0.0 UV_SHA256_AARCH64="" work="$dir/work"
        local tool_bin="$dir/good" UV_SHA256_X86_64=$good
        ensure_uv >/dev/null && [ "$("$dir/good/uv")" = fake-uv ] || exit 1
        tool_bin="$dir/bad" UV_SHA256_X86_64=$(printf '0%.0s' {1..64})
        ! ensure_uv 2>/dev/null && [ ! -e "$dir/bad/uv" ] || exit 2
    ) || fails=$?
    rm -rf "$dir"
    if [ $fails = 0 ]; then echo "ok    uv: a verified download is installed, a tampered one is refused"
    else echo "FAIL  uv download checks ($fails)"; return 1; fi
}

fingerprint() {
    local f
    for f in "$@"; do
        if [ -L "$f" ]; then echo "$f -> $(readlink "$f")"; elif [ -f "$f" ]; then sha256sum "$f"; else echo "$f absent"; fi
    done
}

# Runs inside the private session.
inside() {
    local work=$1 wheel out fails=0 bin
    wheel=$(ls "$work"/release/mei_runtime-*.whl)
    local ext="$HOME/.local/share/gnome-shell/extensions/mei@andystmc.com"
    local unit="$HOME/.config/systemd/user/mei-runtime.service"
    local svc="$HOME/.local/share/dbus-1/services/com.andystmc.Mei1.service"
    check() { if eval "$2"; then echo "ok    $1"; else echo "FAIL  $1"; fails=1; fi; }
    enabled() { /usr/bin/gsettings get org.gnome.shell enabled-extensions; }
    hello() {
        /usr/bin/gdbus call --session --dest com.andystmc.Mei1 --object-path /com/andystmc/Mei1 \
            --method com.andystmc.Mei1.Runtime.Hello \
            "'{\"client\": {\"kind\": \"install-test\"}, \"protocol\": [2, 0]}'"
    }

    /usr/bin/gsettings set org.gnome.shell enabled-extensions "['other@example.org']"
    out=$(bash "$work/release/install.sh" --wheel "$wheel" 2>&1)
    echo "$out" > "$work/install-1.log"
    bin=$(uv tool dir --bin)
    check "mei-runtime is installed as a uv tool" '[ -x "$bin/mei-runtime" ]'
    check "voice's engine is installed with it" \
        '"$(uv tool dir)/mei-runtime/bin/python" -c "import sherpa_onnx, numpy" && ! grep -q "without voice" "$work/install-1.log"'
    points_at_tool() {  # ExecStart= quotes the program and doubles any % (a systemd specifier)
        local python
        python="$(uv tool dir)/mei-runtime/bin/python"
        grep -qxF "ExecStart=\"${python//%/%%}\" -m mei serve" "$unit" && grep -q "Name=com.andystmc.Mei1" "$svc"
    }
    check "service files point at the tool's python" points_at_tool
    check "the bundled extension is installed" \
        '[ -f "$ext/metadata.json" ] && [ -f "$ext/extension.js" ] && [ -f "$ext/schemas/gschemas.compiled" ]'
    check "the bundle is the production build" '! grep -q "MEI_DEV_HOOKS" "$ext/extension.js"'
    check "enabled-extensions keeps others and adds Mei" '[ "$(enabled)" = "['"'"'other@example.org'"'"', '"'"'mei@andystmc.com'"'"']" ]'
    check "it ends by asking for a log-out" 'grep -q "Log out and back in (or restart) to finish" <<<"$out"'
    local reply
    reply=$(hello 2>&1) || true
    local pid
    pid=$(sed -n 's/.*"pid":\([0-9]*\).*/\1/p' <<<"$reply")
    check "the installed runtime answers over D-Bus activation" \
        '[ -n "$pid" ] && tr "\0" " " < "/proc/$pid/cmdline" | grep -q "^$(uv tool dir)/mei-runtime/bin/python -m mei serve"'
    echo "$reply" > "$work/hello.log"

    out=$(bash "$work/release/install.sh" --wheel "$wheel" 2>&1)
    echo "$out" > "$work/install-2.log"
    check "a re-run doesn't copy the extension again" '! grep -q "installed the extension" <<<"$out"'
    check "a re-run leaves enabled-extensions as it was" '[ "$(enabled)" = "['"'"'other@example.org'"'"', '"'"'mei@andystmc.com'"'"']" ]'

    mkdir -p "$HOME/.local/share/mei" && echo keep > "$HOME/.local/share/mei/marker"
    out=$(bash "$work/release/install.sh" --uninstall 2>&1)
    echo "$out" > "$work/uninstall.log"
    check "uninstall removes service, extension, and tool" \
        '[ ! -e "$unit" ] && [ ! -e "$svc" ] && [ ! -e "$ext" ] && [ ! -e "$bin/mei-runtime" ]'
    check "uninstall removes only Mei from enabled-extensions" '[ "$(enabled)" = "['"'"'other@example.org'"'"']" ]'
    check "uninstall keeps the user's data" '[ -f "$HOME/.local/share/mei/marker" ]'

    bash "$work/release/install.sh" --wheel "$wheel" >/dev/null 2>&1
    out=$(bash "$work/release/install.sh" --uninstall --purge 2>&1)
    echo "$out" > "$work/purge.log"
    check "uninstall --purge also deletes the data" '[ ! -e "$HOME/.local/share/mei" ] && [ ! -e "$ext" ]'
    return $fails
}

if [ "${1:-}" = --inside ]; then inside "$2"; else main "$@"; fi
