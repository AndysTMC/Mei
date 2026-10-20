# Stage 0a — foundation spike report

Date: 2026-10-20. Machine: GNOME Shell 50.1 (Wayland), Ubuntu with dbus-daemon session bus (`--systemd-activation`), ext4 on SSD, 16 threads, 14 GiB. Runtime Python: uv-managed CPython 3.12.13 (SQLite 3.53.1), dbus-fast 5.2.0. System Python: `/usr/bin/python3` 3.14.4 with PyGObject 3.56.2.

Every test ran on a private session bus (`dbus-run-session`) with private XDG directories, so the real session, settings, and keyring were not touched. Raw logs are not committed; rerun the scripts to reproduce.

## Results

| # | Question | Result | Verdict |
|---|---|---|---|
| 1 | Can the Shell extension D-Bus-activate a uv-installed Python service? | Yes. Cold activation (first `Hello` from `enable()`) **367–374 ms**, almost all of it Python start-up; the service itself was ready 1.4 ms after connecting. Warm `Hello`: 10–21 ms. | ✅ |
| 2 | Call latency Shell → runtime | `Ping` round trip from GJS: **p50 0.19–0.23 ms, p99 0.5–0.6 ms** (p99 ~23 ms right after Shell start-up while the Shell is busy) | ✅ |
| 3 | Unicast events | Delivered to the attached extension; a non-attached `gdbus monitor` saw **0** `Event` signals while seeing 3 broadcast `Beacon` control signals in the same 3 s | ✅ |
| 4 | Event latency and throughput | Live ticks: **p50 0.5 ms**. A burst of 1,000 events was queued by the service in 13–15 ms and fully applied by the Shell in **21–30 ms** | ✅ |
| 5 | Reattach after extension disable/enable | After 3 s disabled: `Hello` 21 ms, **32–33 missed events replayed, 0 gaps**, live events buffered during attach and deduplicated by seq | ✅ |
| 6 | Service killed (`SIGKILL`) | Extension saw the name vanish, re-activated the service in **~310 ms** (plus a deliberate 300 ms back-off), detected the new epoch, resynced, 0 gaps | ✅ |
| 7 | Shell restart while the service runs | Service survived (same pid and epoch); the new Shell reattached in 10–12 ms and replayed history from seq 0 | ✅ |
| 8 | fd return (`ReadArtifact`, `(sh)`) | 77,824-byte read-only fd received in GJS, sha256 matches, **0.9–1.2 ms** | ✅ |
| 8b | **Backpressure (found on retest)** | dbus-fast 5.2.0 **disconnects itself** when its socket buffer is momentarily full: `BlockingIOError` (EAGAIN) from `sock.send()` reaches a generic `except` that calls `bus._finalize()`. Seen once in four Shell runs (a burst while the new Shell was starting up), and in **3/3** stress runs (10 × 20,000 signals). Upstream `main` has the same code. With `dbus_fast_patch.py` (wait for writability on EAGAIN/EINTR): **3/3** stress runs delivered all 200,000 signals in ~3.5 s, and **4/4** full Shell runs had no crash and no gaps | ⚠️ fixed by a pinned patch; report upstream |
| 9 | dbus-fast vs PyGObject for the core | dbus-fast: import 57 ms, ping p50 0.078 ms / p99 0.20 ms, fd ok, 30 MB RSS. PyGObject asyncio: import 15 ms, ping p50 0.21 ms / p99 0.48 ms, fd ok, 28 MB RSS. **PyGObject has no wheels on PyPI** (a uv venv would build it from source against system headers), and `asyncio.run()` with its loop policy fails on Python 3.14; the documented `policy.get_event_loop()` pattern works | **dbus-fast for the core**; PyGObject only in the desktop worker on system Python |
| 10 | Secret Service via dbus-fast | `OpenSession("plain")` works (no crypto dependency). Create/read with the existing schema `com.andystmc.mei.provider-api-key` works. **Locked keyring: `GetSecrets` returns zero secrets with no error**; the item appears in the `locked` list. `Unlock` returns a prompt object (completing it shows GNOME's dialog) | ✅, with one rule (below) |
| 11 | Keyring independent of the Shell? | The real `gnome-keyring-daemon` runs as its own systemd user service and socket, not inside or beside gnome-shell's lifetime | ✅ supports ADR-10 |
| 12 | SQLite durability cost | WAL + `synchronous=FULL`: **p50 1.13 ms, p99 2.67 ms, max 10.5 ms, ~850 commits/s** (two-row transaction). `NORMAL`: p50 0.017 ms | ✅ FULL is affordable at durable boundaries |
| 13 | Single writer | `flock(LOCK_EX\|LOCK_NB)` refuses a second instance; the kernel releases it when the holder dies | ✅ |
| 14 | sqlite-vec loadable? (0d preview) | `enable_load_extension` is available in uv's CPython | ✅ |
| 15 | Does a copied extension appear in a running Shell? | **No**: `gnome-extensions info` says it doesn't exist. After a Shell restart it is discovered (`INITIALIZED`), and `gnome-extensions enable` makes it `ACTIVE` immediately | Confirms the log-out step |
| 16 | Does pre-adding it to `enabled-extensions` make it active at next start? | **Yes.** First looked inconclusive, but the nested test was calling Homebrew's `gsettings`, which has no dconf backend and silently wrote to a side file (see 19). With `/usr/bin/gsettings`: listed while the Shell runs → `ACTIVE` at the next start | ✅ |
| 16b | Real session: systemd activation | A temporary `mei-spike.service` (`Type=dbus`) behind a D-Bus service file with `SystemdService=`: cold activation by a call **440 ms**; after `systemctl stop`, the next call re-activated it in **100 ms**; after `SIGKILL`, systemd restarted it (`Restart=on-failure`, NRestarts=1) and calls kept working. dbus-fast client in the real session: ping p50 0.10 ms, fd ok. Removed afterwards (unit not-found, name not activatable) | ✅ |
| 16c | **Real first install** (`first-install-test.sh`, one real log-out) | Copied a log-only extension and added it to `enabled-extensions` through the system GIO. After log-out/in, the Shell enabled it **0.5 s after `graphical-session.target`**, by itself. The first-login fallback unit wasn't needed (and had a bug: it waited for `org.gnome.Shell.Extensions` to have an owner, but that name is activated on demand). Removed afterwards; the real enabled list was intact | ✅ log-out is the only step |
| 17 | Requirement check | `install-check.sh` passes here and prints the right `apt install …` line with tools hidden | ✅ prototype |
| 19 | **Shadowed system tools** | On this machine Homebrew's GLib tools come first on PATH: `gsettings`, `gdbus`, `glib-compile-schemas` (and `python3`). Homebrew's `gsettings` **can't load the dconf module**, so it reads `[]` for `enabled-extensions` and its writes never reach dconf, with no error. `/usr/bin/gsettings` shows the real list | ⚠️ installer and runtime use absolute system paths |
| 18 | extensions.gnome.org rules | No binaries in the extension, no spawning, D-Bus unrestricted. Clipboard access must be declared in the description. **"Extensions must not be AI-generated"**: submissions with prompt-like comments, imaginary APIs, or inconsistent style are rejected; AI-assisted code is fine if the author can justify it | ✅ with a listing risk |

## Things the spikes taught us

- **`bus_watch_name` reports "vanished" immediately** when the runtime isn't running yet. The client must ignore that until it has seen an owner, or it fires a duplicate `Hello`. (Seen in run 1; fixed in run 2.)
- **`Gio.UnixInputStream` is deprecated** in this GLib; use `GioUnix.InputStream`.
- **Unix socket paths are limited to 108 bytes.** gnome-keyring's error for a too-long path is "Address already in use". Runtime sockets and any `XDG_RUNTIME_DIR` overrides must stay short.
- **System tools on PATH can be someone else's.** Here Homebrew shadows `python3` (no PyGObject) and GLib's `gsettings`, `gdbus`, and `glib-compile-schemas`; its `gsettings` has no dconf backend and silently does nothing useful. Users with Nix, conda, or pyenv will hit the same thing. Rules: the installer and runtime call `/usr/bin/gsettings` and `/usr/bin/python3` by absolute path; GSettings reads and writes happen in the desktop worker (system Python and GIO), never in the core's uv Python, which has no GIO at all; the requirement check warns when PATH versions differ. (The project's own `npm run build:schemas` also picks up Homebrew's `glib-compile-schemas`; the output works here, but the build should prefer the system binary.)
- **A locked keyring looks like "no key"** if you only look at `GetSecrets`. The runtime must check `SearchItems`' locked list, report `keyring_locked`, and offer the unlock prompt, never "missing key". This silent failure is a plausible cause of the original ADR 0001 symptom.
- **dbus-fast needs a guard against its own EAGAIN bug** (8b). The runtime pins dbus-fast, applies the patch at start-up, and fails fast if the version changes, so the patch can't silently outlive the bug. Independent of the patch, the runtime should not emit unbounded bursts: deltas are coalesced (33 ms), and a client that falls far behind gets a "resync" marker and re-attaches instead of an ever-growing queue.
- **Bus loss surfaces as `EOFError`** from dbus-fast's `wait_for_disconnect()`. The runtime should treat it as fatal and let systemd restart it.
- **Cold activation is ~370 ms.** The UI should show "Starting Mei…" on the first call after login instead of blocking.

## Decisions taken

- ADR 0002: the runtime is a separate Python user service; the extension is UI only; the runtime owns canonical state and provider config.
- ADR 0003: IPC over the session bus with dbus-fast, JSON payloads, one fd exception, unicast events, a global seq, and attach/replay.
- ADR 0004: per-user install script; copy + `enabled-extensions` + one log-out is enough (verified in a real session). The first-login unit from the first draft was dropped.
- ADR-10 (keyring-only keys, superseding 0001) is confirmed by results 10–11 and will be written when it takes effect in Stage 2a, as planned.

## Not covered (and why)

- **Completing the keyring unlock prompt.** It is interactive by design; the spike dismissed it.
- **Fedora 44 and Ubuntu 26.04 VMs.** No VMs here; the requirement check maps package names for apt/dnf/pacman/zypper but has only run on this machine.

## Retest (same day)

Every spike was rerun from scratch; numbers matched the first runs within noise (e.g. ping p50 0.22 ms, reattach replayed 32 events with 0 gaps, SQLite FULL p50 1.12 ms, PyGObject ping p50 0.19 ms vs dbus-fast 0.10 ms). The retest found the backpressure bug (8b) and added the real-session systemd test (16b). `npm run check` passed: 80 tests, typecheck, format, build.

## Reproduce

```bash
uv venv --python 3.12 /path/to/venv && uv pip install --python /path/to/venv/bin/python dbus-fast
spikes/0a/run_ipc.sh /path/to/venv/bin/python /path/to/out        # 1–8, 15
spikes/0a/run_late.sh /path/to/out-late                           # 16
spikes/0a/run_secret.sh /path/to/venv/bin/python /path/to/keyring-data  # 10
/path/to/venv/bin/python spikes/0a/sqlite_spike.py ~/.cache/mei-sqlite-spike   # 12–14
dbus-run-session -- /path/to/venv/bin/python spikes/0a/backpressure_spike.py          # 8b, unpatched: crashes
dbus-run-session -- /path/to/venv/bin/python spikes/0a/backpressure_spike.py patched  # 8b, patched
spikes/0a/install-check.sh                                        # 17
```

`client_bench.py` (result 9) needs a private bus with the service activatable; see how `run_ipc.sh` sets that up.
