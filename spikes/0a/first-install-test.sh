#!/usr/bin/env bash
# Stage 0a: real first-install test for ADR 0004, using the log-only `mei-late` extension.
#   install  copy mei-late, add it to enabled-extensions, install a one-shot first-login unit
#   (log out and back in)
#   check    show what happened at login: was it already active from enabled-extensions alone,
#            or did the first-login unit have to enable it?
#   remove   undo everything
# Touches only: ~/.local/share/gnome-shell/extensions/mei-late@andystmc.com,
# the mei-late entry in org.gnome.shell enabled-extensions, ~/.config/systemd/user/mei-spike-first-login.service,
# and ~/.cache/mei-first-install-test/.

main() {
    set -u
    local uuid=mei-late@andystmc.com
    local here ext_dir unit dir
    here=$(cd "$(dirname "$0")" && pwd)
    ext_dir="$HOME/.local/share/gnome-shell/extensions/$uuid"
    unit="$HOME/.config/systemd/user/mei-spike-first-login.service"
    dir="$HOME/.cache/mei-first-install-test"

    strv() {  # strv add|remove <uuid>: edit enabled-extensions without touching other entries
        /usr/bin/python3 - "$1" "$2" <<'EOF'
import sys
from gi.repository import Gio
op, uuid = sys.argv[1], sys.argv[2]
s = Gio.Settings.new("org.gnome.shell")
cur = s.get_strv("enabled-extensions")
new = cur + [uuid] if op == "add" and uuid not in cur else [u for u in cur if u != uuid]
s.set_strv("enabled-extensions", new)
Gio.Settings.sync()
EOF
    }

    case "${1:-}" in
    install)
        if [ -e "$ext_dir" ] || [ -e "$unit" ]; then echo "already installed; run remove first"; return 1; fi
        mkdir -p "$dir" "$(dirname "$ext_dir")" "$(dirname "$unit")"
        cp -a "$here/ext/$uuid" "$ext_dir"
        strv add "$uuid"
        cat > "$dir/first-login.sh" <<EOF
#!/usr/bin/env bash
log() { echo "\$(date '+%F %T') \$*" >> "$dir/first-login.log"; }
log "first-login unit started"
for _ in \$(seq 1 120); do
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \\
        --method org.freedesktop.DBus.NameHasOwner org.gnome.Shell.Extensions 2>/dev/null | grep -q true && break
    sleep 0.5
done
state=\$(gnome-extensions info $uuid 2>&1 | grep State | xargs)
log "before: \$state"
if [ "\$state" != "State: ACTIVE" ]; then
    gdbus call --session --dest org.gnome.Shell.Extensions --object-path /org/gnome/Shell/Extensions \\
        --method org.gnome.Shell.Extensions.EnableExtension $uuid >> "$dir/first-login.log" 2>&1
    sleep 1
    log "after EnableExtension: \$(gnome-extensions info $uuid 2>&1 | grep State | xargs)"
fi
systemctl --user disable mei-spike-first-login.service >> "$dir/first-login.log" 2>&1
log "unit disabled itself"
EOF
        chmod +x "$dir/first-login.sh"
        cat > "$unit" <<EOF
[Unit]
Description=Mei Stage 0a first-login test (temporary, safe to delete)
After=graphical-session.target

[Service]
Type=oneshot
ExecStart=$dir/first-login.sh

[Install]
WantedBy=graphical-session.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable mei-spike-first-login.service 2>&1 | tail -1
        echo "Running Shell sees it now? $(gnome-extensions info "$uuid" 2>&1 | head -1)"
        echo "Installed. Log out and back in, then run: $0 check"
        ;;
    check)
        echo "== first-login log"; cat "$dir/first-login.log" 2>/dev/null || echo "(no log: the unit hasn't run yet)"
        echo "== now: $(gnome-extensions info "$uuid" 2>&1 | grep -E 'State' | xargs)"
        echo "== Shell journal this boot:"; journalctl --user -b -o cat 2>/dev/null | grep "\[mei-late\]" | tail -3
        ;;
    remove)
        gnome-extensions disable "$uuid" 2>/dev/null
        strv remove "$uuid"
        systemctl --user disable mei-spike-first-login.service 2>/dev/null
        rm -rf "$ext_dir" "$unit" "$dir"
        systemctl --user daemon-reload
        echo "Removed. enabled-extensions now: $(/usr/bin/gsettings get org.gnome.shell enabled-extensions)"
        ;;
    *) echo "usage: $0 install|check|remove"; return 2 ;;
    esac
}

main "$@"
