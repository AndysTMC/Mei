#!/usr/bin/env bash
# Mei installer. Per-user: it never uses sudo and writes only under your home directory.
#
#   curl -fsSL https://raw.githubusercontent.com/AndysTMC/Mei/main/install.sh | bash
#   bash install.sh [--check] [--wheel FILE] [--uninstall [--purge]]
#
#   --check      check the system and change nothing
#   --wheel F    install from a local mei-runtime wheel instead of downloading the release
#   --uninstall  remove the service and the extension; --purge also deletes conversations,
#                settings, and API keys
#
# Re-running it upgrades in place. The whole body is one function called on the last line, so a
# cut-off download runs nothing.

main() {
    set -euo pipefail
    local MEI_VERSION=0.1.0
    local MEI_WHEEL_SHA256=  # set by scripts/build-release.sh; empty in a source checkout
    local UV_VERSION=0.11.32
    local UV_SHA256_X86_64=  # uv's published checksums for UV_VERSION, set by scripts/build-release.sh
    local UV_SHA256_AARCH64=
    local RELEASES=https://github.com/AndysTMC/Mei/releases/download

    local mode=install purge=0 wheel=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --check) mode=check ;;
            --uninstall) mode=uninstall ;;
            --purge) purge=1 ;;
            --wheel) wheel=${2:?--wheel needs a file}; shift ;;
            -h|--help) echo "usage: install.sh [--check] [--wheel FILE] [--uninstall [--purge]]"; return 0 ;;
            *) echo "unknown option: $1" >&2; return 2 ;;
        esac
        shift
    done

    if [ "$(id -u)" = 0 ]; then
        echo "Run the Mei installer as your own user, not as root (it installs only for you)." >&2
        return 1
    fi

    local tool_bin="$HOME/.local/bin"
    if [ "$mode" = uninstall ]; then
        uninstall_mei
        return
    fi

    if [ "${MEI_INSTALL_SKIP_CHECK:-}" != 1 ]; then  # skipped only by scripts/install-test.sh
        check_system || return
    fi
    [ "$mode" = check ] && return 0

    local work  # downloads land here; removed however the script ends
    work=$(mktemp -d)
    trap "rm -rf $(printf %q "$work")" EXIT
    ensure_uv
    install_runtime
    local bin
    bin=$("$(uv_cmd)" tool dir --bin)
    "$bin/mei-runtime" install
}

# ── System check ─────────────────────────────────────────────────────────────

check_system() {
    local missing=() problems=() ver state

    have() { command -v "$1" >/dev/null 2>&1; }
    ok() { printf '  ok    %s\n' "$1"; }
    miss() { printf '  MISS  %s\n' "$1"; missing+=("$2"); }
    fail() { printf '  FAIL  %s\n' "$1"; problems+=("$1"); }

    echo "Checking this system for Mei $MEI_VERSION"
    ver=$(gnome-shell --version 2>/dev/null | awk '{print $3}') || true
    if [ -z "$ver" ]; then
        fail "GNOME Shell not found (Mei is a GNOME extension)"
    elif [ "${ver%%.*}" -ge 50 ] 2>/dev/null; then
        ok "GNOME Shell $ver"
    else
        fail "GNOME Shell $ver (Mei needs 50 or newer)"
    fi
    if [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
        ok "Wayland session"
    else
        fail "session type '${XDG_SESSION_TYPE:-unknown}' (Mei needs a Wayland session; run this from your desktop)"
    fi
    state=$(/usr/bin/systemctl --user is-system-running 2>/dev/null) || true
    case "$state" in
        running|degraded|starting) ok "systemd user manager" ;;
        *) fail "no systemd user manager for this session" ;;
    esac
    # System tools by absolute path: the ones on PATH may be Homebrew's, Nix's, or conda's.
    if [ -x /usr/bin/gsettings ] && [ -x /usr/bin/gdbus ]; then ok "GLib tools (/usr/bin/gsettings, gdbus)"; else miss "GLib tools (gsettings, gdbus)" glibbin; fi
    if [ -x /usr/bin/dconf ]; then ok "dconf"; else miss "dconf" dconf; fi
    if /usr/bin/gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.ListActivatableNames 2>/dev/null | grep -q "'org.freedesktop.secrets'" ||
       /usr/bin/gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner org.freedesktop.secrets 2>/dev/null | grep -q true; then
        ok "keyring (Secret Service)"
    else
        miss "keyring (Secret Service), where Mei keeps API keys" keyring
    fi
    if ! have curl && { [ -z "$wheel" ] || [ ! -x "$(uv_cmd)" ]; }; then miss "curl (to download Mei and uv)" curl; fi
    # Optional: computer use runs its desktop worker on the system's Python, in a jail (decision 0022).
    local computer=()
    [ -x /usr/bin/bwrap ] || computer+=(bubblewrap)
    [ -x /usr/bin/xdg-dbus-proxy ] || computer+=(xdg-dbus-proxy)
    /usr/bin/python3 -c 'import gi; gi.require_version("Atspi", "2.0"); gi.require_version("Gst", "1.0")
from gi.repository import Gst; Gst.init(None); assert Gst.ElementFactory.find("pipewiresrc")' 2>/dev/null ||
        computer+=("PyGObject with AT-SPI and GStreamer's PipeWire plugin (python3-gi gir1.2-atspi-2.0 gstreamer1.0-pipewire)")
    if [ ${#computer[@]} -eq 0 ]; then
        ok "computer use (optional)"
    else
        printf '  note  computer use (optional) needs: %s\n' "${computer[*]}"
    fi

    if [ ${#problems[@]} -gt 0 ]; then
        echo; echo "Mei can't be installed here:"; printf '  - %s\n' "${problems[@]}"
        return 1
    fi
    if [ ${#missing[@]} -gt 0 ]; then
        echo; echo "Install the missing packages, then run the installer again:"
        echo "  $(package_hint "${missing[@]}")"
        return 1
    fi
    echo "  all requirements met"
}

package_hint() {
    local id like k pkgs=""
    id=$(. /etc/os-release 2>/dev/null && echo "${ID:-}") || true
    like=$(. /etc/os-release 2>/dev/null && echo "${ID_LIKE:-}") || true
    local -A deb=([glibbin]=libglib2.0-bin [dconf]=dconf-cli [keyring]=gnome-keyring [curl]=curl)
    local -A rpm=([glibbin]=glib2 [dconf]=dconf [keyring]=gnome-keyring [curl]=curl)
    local -A arch=([glibbin]=glib2 [dconf]=dconf [keyring]=gnome-keyring [curl]=curl)
    local -A suse=([glibbin]=glib2-tools [dconf]=dconf [keyring]=gnome-keyring [curl]=curl)
    case " $id $like " in
        *" debian "*|*" ubuntu "*) for k in "$@"; do pkgs+=" ${deb[$k]}"; done; echo "sudo apt install$pkgs" ;;
        *" fedora "*|*" rhel "*) for k in "$@"; do pkgs+=" ${rpm[$k]}"; done; echo "sudo dnf install$pkgs" ;;
        *" arch "*) for k in "$@"; do pkgs+=" ${arch[$k]}"; done; echo "sudo pacman -S$pkgs" ;;
        *" suse "*|*" opensuse "*) for k in "$@"; do pkgs+=" ${suse[$k]}"; done; echo "sudo zypper install$pkgs" ;;
        *) echo "(install them with your distribution's package manager)" ;;
    esac
}

# ── uv and the runtime ───────────────────────────────────────────────────────

uv_cmd() {
    if command -v uv >/dev/null 2>&1; then command -v uv; else echo "$tool_bin/uv"; fi
}

# Gets the uv program itself (no install script is run): a pinned version from uv's GitHub
# releases, checked against a checksum pinned in this file, unpacked into ~/.local/bin.
ensure_uv() {
    [ -x "$(uv_cmd)" ] && return 0
    local target sha binary
    case "$(uname -m)" in
        x86_64) target=x86_64-unknown-linux-gnu; sha=$UV_SHA256_X86_64 ;;
        aarch64|arm64) target=aarch64-unknown-linux-gnu; sha=$UV_SHA256_AARCH64 ;;
        *) echo "uv is needed and this installer can't get it for $(uname -m); install uv" \
                "(https://docs.astral.sh/uv/), then run the installer again." >&2; return 1 ;;
    esac
    if [ -z "$sha" ]; then
        echo "uv is needed, and this install.sh has no pinned checksum for it (it isn't from a release)." >&2
        echo "Install uv (https://docs.astral.sh/uv/), then run the installer again." >&2
        return 1
    fi
    echo "Downloading uv $UV_VERSION"
    curl -fsSL --proto '=https' --tlsv1.2 -o "$work/uv.tar.gz" \
        "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
    if [ "$(sha256sum "$work/uv.tar.gz" | cut -d' ' -f1)" != "$sha" ]; then
        echo "The uv download doesn't match its pinned checksum; nothing was installed." >&2
        return 1
    fi
    mkdir -p "$work/uv" "$tool_bin"
    tar -xzf "$work/uv.tar.gz" -C "$work/uv"
    binary=$(find "$work/uv" -type f -name uv | head -n 1)
    [ -n "$binary" ] || { echo "The uv download has no uv program in it." >&2; return 1; }
    install -m 0755 "$binary" "$tool_bin/uv"
    echo "Installed uv into $tool_bin"
}

install_runtime() {
    local file
    if [ -n "$wheel" ]; then
        [ -f "$wheel" ] || { echo "no such file: $wheel" >&2; return 1; }
        file=$(cd "$(dirname "$wheel")" && pwd)/$(basename "$wheel")
        echo "Installing mei-runtime from $file"
    else
        if [ -z "$MEI_WHEEL_SHA256" ]; then
            echo "This install.sh isn't from a release (no pinned checksum)." >&2
            echo "Build one with scripts/build-release.sh, or pass --wheel FILE." >&2
            return 1
        fi
        file="$work/mei_runtime-$MEI_VERSION-py3-none-any.whl"
        echo "Downloading mei-runtime $MEI_VERSION"
        curl -fsSL --proto '=https' --tlsv1.2 -o "$file" "$RELEASES/v$MEI_VERSION/$(basename "$file")"
        if [ "$(sha256sum "$file" | cut -d' ' -f1)" != "$MEI_WHEEL_SHA256" ]; then
            echo "The download doesn't match the published checksum; nothing was installed." >&2
            return 1
        fi
    fi
    # With voice's engine (the `voice` extra, ~35 MB); where it has no build, Mei installs without voice.
    if ! "$(uv_cmd)" tool install --quiet --force --reinstall-package mei-runtime --python '>=3.12' \
        "mei-runtime[voice] @ file://$file"; then
        echo "Voice's engine couldn't be installed here; installing Mei without voice." >&2
        "$(uv_cmd)" tool install --quiet --force --reinstall-package mei-runtime --python '>=3.12' "$file"
    fi
}

uninstall_mei() {
    local uv bin
    uv=$(uv_cmd)
    if [ -x "$uv" ]; then bin=$("$uv" tool dir --bin); fi
    if [ -n "${bin:-}" ] && [ -x "$bin/mei-runtime" ]; then
        if [ "$purge" = 1 ]; then "$bin/mei-runtime" uninstall --purge; else "$bin/mei-runtime" uninstall; fi
        "$uv" tool uninstall --quiet mei-runtime
        echo "removed the mei-runtime tool"
    else
        echo "mei-runtime isn't installed for this user; nothing to remove."
    fi
}

main "$@"
