#!/usr/bin/env bash
# Stage 0a: does an install script's "copy + add to enabled-extensions" make the extension
# active after the next Shell start? Private bus + private dconf db. Usage: run_late.sh <out-dir>
set -u
OUT=$1; HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"/data/gnome-shell/extensions "$OUT"/config "$OUT"/state "$OUT"/cache
export XDG_DATA_HOME="$OUT/data" XDG_CONFIG_HOME="$OUT/config" XDG_STATE_HOME="$OUT/state" XDG_CACHE_HOME="$OUT/cache"
unset GSETTINGS_BACKEND
dbus-run-session -- bash -c '
OUT=$1; HERE=$2
/usr/bin/gsettings set org.gnome.shell disable-user-extensions false
/usr/bin/gsettings set org.gnome.shell enabled-extensions "[]"
gnome-shell --devkit --wayland --no-x11 >> "$OUT/shell.log" 2>&1 & P=$!; sleep 10
echo "dconf db: $(ls "$XDG_CONFIG_HOME/dconf" 2>&1)"
cp -a "$HERE/ext/mei-late@andystmc.com" "$XDG_DATA_HOME/gnome-shell/extensions/"
cur=$(/usr/bin/gsettings get org.gnome.shell enabled-extensions)
/usr/bin/gsettings set org.gnome.shell enabled-extensions "[\"mei-late@andystmc.com\"]"
echo "set while running: $(/usr/bin/gsettings get org.gnome.shell enabled-extensions) (was $cur)"
echo "running shell sees: $(gnome-extensions info mei-late@andystmc.com 2>&1 | head -1)"
sleep 2
kill -TERM $P; wait $P 2>/dev/null
echo "after shell exit: $(/usr/bin/gsettings get org.gnome.shell enabled-extensions)"
gnome-shell --devkit --wayland --no-x11 >> "$OUT/shell.log" 2>&1 & P=$!; sleep 10
gnome-extensions info mei-late@andystmc.com | grep -E "Enabled|State"
grep -c "\[mei-late\] enabled" "$OUT/shell.log" | sed "s/^/mei-late enable log lines: /"
kill -TERM $P; wait $P 2>/dev/null
' _ "$OUT" "$HERE"
