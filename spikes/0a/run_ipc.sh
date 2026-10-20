#!/usr/bin/env bash
# Stage 0a IPC spike harness. Runs everything on a private session bus (dbus-run-session)
# with private XDG dirs, so the real session is untouched. Usage: run_ipc.sh <venv-python> <out-dir>
set -u
PY=$1
OUT=$2
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"/data/gnome-shell/extensions "$OUT"/data/dbus-1/services "$OUT"/config "$OUT"/state "$OUT"/cache
cp -a "$HERE/ext/mei-spike@andystmc.com" "$OUT/data/gnome-shell/extensions/"
cat > "$OUT/data/dbus-1/services/com.andystmc.Mei1.service" <<EOF
[D-BUS Service]
Name=com.andystmc.Mei1
Exec=$PY $HERE/service.py
EOF
export XDG_DATA_HOME="$OUT/data" XDG_CONFIG_HOME="$OUT/config" XDG_STATE_HOME="$OUT/state" XDG_CACHE_HOME="$OUT/cache"
export GSETTINGS_BACKEND=keyfile
/usr/bin/gsettings set org.gnome.shell disable-user-extensions false
/usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei-spike@andystmc.com']"

dbus-run-session -- bash -c '
OUT=$1; HERE=$2
mark() { echo "[harness $(date +%s.%N | cut -c1-14)] $*" >> "$OUT/shell.log"; }
start_shell() { gnome-shell --devkit --wayland --no-x11 >> "$OUT/shell.log" 2>&1 & SHELL_PID=$!; mark "shell started pid=$SHELL_PID"; }
svc_pid() { pgrep -f "$HERE/service.py" | head -1; }

start_shell; sleep 12
mark "unicast check: a non-attached monitor should see 0 Event signals"
timeout 3 gdbus monitor --session --dest com.andystmc.Mei1 > "$OUT/monitor.txt" 2>&1
mark "monitor saw $(grep -c "Runtime.Event" "$OUT/monitor.txt") Event (unicast) and $(grep -c "Runtime.Beacon" "$OUT/monitor.txt") Beacon (broadcast) signals"

mark "disable extension for 3 s"; gnome-extensions disable mei-spike@andystmc.com; sleep 3
mark "enable extension"; gnome-extensions enable mei-spike@andystmc.com; sleep 3

mark "SIGKILL service pid=$(svc_pid)"; kill -9 "$(svc_pid)"; sleep 4
mark "service now pid=$(svc_pid)"

mark "late copy: install mei-late into the running Shell"
cp -a "$HERE/ext/mei-late@andystmc.com" "$XDG_DATA_HOME/gnome-shell/extensions/"
gnome-extensions list > "$OUT/late-list-before.txt" 2>&1
gnome-extensions enable mei-late@andystmc.com >> "$OUT/late-enable.txt" 2>&1; echo "enable exit=$?" >> "$OUT/late-enable.txt"
gnome-extensions info mei-late@andystmc.com > "$OUT/late-info-before.txt" 2>&1
mark "pre-enable mei-late through GSettings, as an install script would"
/usr/bin/gsettings set org.gnome.shell enabled-extensions "['mei-spike@andystmc.com', 'mei-late@andystmc.com']"
sleep 2

SVC_BEFORE=$(svc_pid)
mark "restart Shell (service should survive) svc=$SVC_BEFORE"
kill -TERM $SHELL_PID; wait $SHELL_PID 2>/dev/null
mark "shell stopped; service pid=$(svc_pid)"
start_shell; sleep 12
gnome-extensions info mei-late@andystmc.com > "$OUT/late-info-after.txt" 2>&1
mark "after restart service pid=$(svc_pid)"
kill -TERM $SHELL_PID; wait $SHELL_PID 2>/dev/null
kill -TERM "$(svc_pid)" 2>/dev/null
mark "done"
' _ "$OUT" "$HERE"
