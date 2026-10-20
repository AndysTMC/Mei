#!/usr/bin/env bash
# Stage 0a prototype of install.sh's requirement check (§21.1/§21.2). Read-only: it changes nothing.
# The body is one function called on the last line, so a truncated download runs nothing.

main() {
    set -u
    local missing=() problems=() id like

    have() { command -v "$1" >/dev/null 2>&1; }
    ok() { printf '  ok    %s\n' "$1"; }
    bad() { printf '  MISS  %s\n' "$1"; missing+=("$2"); }
    fail() { printf '  FAIL  %s\n' "$1"; problems+=("$1"); }

    echo "Mei requirement check"

    local ver
    ver=$(gnome-shell --version 2>/dev/null | awk '{print $3}')
    if [ -z "$ver" ]; then
        fail "GNOME Shell not found"
    elif [ "${ver%%.*}" -ge 50 ]; then
        ok "GNOME Shell $ver"
    else
        fail "GNOME Shell $ver (Mei needs 50 or newer)"
    fi

    if [ "${XDG_SESSION_TYPE:-}" = wayland ]; then ok "Wayland session"; else fail "session type '${XDG_SESSION_TYPE:-unknown}' (Mei needs Wayland)"; fi
    if systemctl --user is-system-running >/dev/null 2>&1 || [ "$(systemctl --user is-system-running 2>/dev/null)" = degraded ]; then
        ok "systemd user manager"
    else
        fail "no systemd user manager"
    fi

    if [ -x /usr/bin/gsettings ]; then ok "system gsettings (/usr/bin/gsettings)"; else bad "system gsettings" glibbin; fi
    local tool sys_path path_tool
    for tool in python3 gsettings gdbus; do
        sys_path=/usr/bin/$tool
        path_tool=$(command -v "$tool" 2>/dev/null)
        if [ -n "$path_tool" ] && [ -x "$sys_path" ] && [ "$(readlink -f "$path_tool")" != "$(readlink -f "$sys_path")" ]; then
            printf '  note  %s on PATH is %s; Mei uses %s\n' "$tool" "$path_tool" "$sys_path"
        fi
    done

    if have bwrap; then ok "bubblewrap $(bwrap --version | awk '{print $2}')"; else bad "bubblewrap" bwrap; fi
    if have xdg-dbus-proxy; then ok "xdg-dbus-proxy"; else bad "xdg-dbus-proxy" dbusproxy; fi
    if [ -e /usr/share/xdg-desktop-portal/portals/gnome.portal ]; then ok "xdg-desktop-portal-gnome"; else bad "xdg-desktop-portal-gnome" portal; fi
    if have pw-cli; then ok "PipeWire"; else bad "PipeWire" pipewire; fi
    if /usr/bin/python3 -c 'import gi; gi.require_version("Atspi", "2.0"); from gi.repository import Atspi' 2>/dev/null; then
        ok "system python3 with PyGObject and AT-SPI"
    else
        bad "system python3 with PyGObject and AT-SPI (desktop control)" pygobject
    fi
    if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.ListActivatableNames 2>/dev/null | grep -q "org.freedesktop.secrets"; then
        ok "Secret Service (keyring)"
    else
        bad "Secret Service (keyring)" keyring
    fi

    if [ ${#problems[@]} -gt 0 ]; then
        echo; echo "Mei can't be installed on this system:"; printf '  - %s\n' "${problems[@]}"; return 1
    fi
    if [ ${#missing[@]} -eq 0 ]; then
        echo; echo "All requirements met."; return 0
    fi

    id=$(. /etc/os-release && echo "${ID:-}"); like=$(. /etc/os-release && echo "${ID_LIKE:-}")
    local -A deb=([glibbin]=libglib2.0-bin [bwrap]=bubblewrap [dbusproxy]=xdg-dbus-proxy [portal]=xdg-desktop-portal-gnome [pipewire]=pipewire [pygobject]="python3-gi gir1.2-atspi-2.0" [keyring]=gnome-keyring)
    local -A rpm=([glibbin]=glib2 [bwrap]=bubblewrap [dbusproxy]=xdg-dbus-proxy [portal]=xdg-desktop-portal-gnome [pipewire]=pipewire [pygobject]="python3-gobject at-spi2-core" [keyring]=gnome-keyring)
    local -A arch=([glibbin]=glib2 [bwrap]=bubblewrap [dbusproxy]=xdg-dbus-proxy [portal]=xdg-desktop-portal-gnome [pipewire]=pipewire [pygobject]="python-gobject at-spi2-core" [keyring]=gnome-keyring)
    local -A suse=([glibbin]=glib2-tools [bwrap]=bubblewrap [dbusproxy]=xdg-dbus-proxy [portal]=xdg-desktop-portal-gnome [pipewire]=pipewire [pygobject]="python3-gobject typelib-1_0-Atspi-2_0" [keyring]=gnome-keyring)
    local pkgs="" cmd k
    case " $id $like " in
        *" debian "*|*" ubuntu "*) for k in "${missing[@]}"; do pkgs+=" ${deb[$k]}"; done; cmd="sudo apt install$pkgs" ;;
        *" fedora "*|*" rhel "*) for k in "${missing[@]}"; do pkgs+=" ${rpm[$k]}"; done; cmd="sudo dnf install$pkgs" ;;
        *" arch "*) for k in "${missing[@]}"; do pkgs+=" ${arch[$k]}"; done; cmd="sudo pacman -S$pkgs" ;;
        *" suse "*|*" opensuse "*) for k in "${missing[@]}"; do pkgs+=" ${suse[$k]}"; done; cmd="sudo zypper install$pkgs" ;;
        *) cmd="(install the missing items with your distribution's package manager)" ;;
    esac
    echo; echo "Install the missing packages, then run the installer again:"; echo "  $cmd"
    return 2
}

main "$@"
