# Stage 0b — desktop spike report

Date: 2026-10-23. GNOME Shell 50 (headless, `--virtual-monitor` 1280×800 and 1920×1080), xdg-desktop-portal 1.21 with the GNOME backend, AT-SPI 2.60, bubblewrap 0.11.1, xdg-dbus-proxy 0.1.7, GStreamer 1.28.2, on the owner's laptop.

Throwaway code in this folder. Every probe runs in a private, headless Shell on a private session bus, with a private home, XDG dirs, runtime dir, keyfile GSettings, and its own PipeWire with no devices (`run.sh`, `shell.py`), like the e2e test. No screen of the owner's was captured or driven. Results and screenshots went to a scratch folder outside the repository.

Run: `spikes/0b/run.sh <atspi|coords|portals|worker> [output-dir]`. `MEI_0B_SCALE=1.5` runs the worker probe at 150 %, and `MEI_0B_HOST_FRAME=1` also grabs a frame outside the jail.

## Results

### AT-SPI coverage (`atspi.py`)

Each app was launched in the private Shell, its tree walked, and one small task done through AT-SPI alone where the app allowed it.

| App | Appeared | Walk | Nodes | Interactive, showing | Named | With an action | Editable | Task |
|---|---|---|---|---|---|---|---|---|
| Calculator (GTK4/libadwaita) | 2.1 s | 0.05 s | 107 | 38 | 36 | 34 | 2 | 7 + 3 = shows 10, by AT-SPI actions only |
| gtk4-widget-factory | 0.9 s | 0.13 s | 280 | 72 | 41 | 33 | 9 | — |
| Chrome (`--force-renderer-accessibility`) | 1.8 s | 0.08 s | 237 | 17 | 17 | 17 | **0** | a local page's field filled and button pressed; see below |
| Obsidian (Electron) | 1.8 s | 0.03 s | 94 | 6 | 5 | 6 | 0 | — |
| Firefox (snap) | — | — | — | — | — | — | — | not measured: the snap can't join a private session bus |

Roles seen: button, toggle button, check box, radio button, combo box, spin button, slider, page tab, link, text, password text, entry, menu item. On AT-SPI 2.60 a button's role name is `button` (not `push button`).

Gaps that change the design:
- **A GTK4 switch has no AT-SPI action.** It can only be toggled by a pointer click at its bounds.
- **Chrome exposes no EditableText.** `set_text_contents` fails on its entries. Focusing the entry with `Atspi.Component.grab_focus` and then typing key events works (the field got the text and the page greeted).
- **Many interactive nodes are unnamed** (widget-factory: 41 of 72 named). The model needs role, position and neighbouring text for those, not a name alone.

### Geometry (`coords.py`)

Calculator's 7 was clicked from its AT-SPI extents on each monitor at 100 %/100 %, 125 %/150 % and 150 %/125 %.

- **SCREEN extents are zero for GTK4 apps on Wayland** (0 of 38). Chrome and Electron report nonzero ones; they weren't checked for accuracy and aren't used.
- **WINDOW extents plus the window's buffer origin** (`Meta.Window.get_buffer_rect()`) **give the Shell's logical point.** That held on both monitors at every scale: 6 of 6 hits.
- **The frame origin misses** by the client-side shadow (25 px here): 0 of 6.
- A stage screenshot of mixed-scale monitors comes out at logical size × the largest scale.

### Portals from a host process (`portals.py`)

| Call | Result |
|---|---|
| Screenshot, `interactive=false` | **refused**, response 2, no dialog: the portal shows its dialog only for the focused app, and a background service is never focused |
| RemoteDesktop + ScreenCast, `persist_mode=2`, first start | one GNOME dialog: pick a screen, turn on "Allow Remote Interaction", Share. Answered → response 0, keyboard and pointer (devices = 3), one stream, a restore token |
| The same with the restore token | **no dialog**, response 0 |
| The same token after a Shell restart | **no dialog**, response 0 |
| Pointer click through the session | hit (Calculator showed 7) |
- **The token kept working when used again.** The portal documents it as single-use, so the runtime should store the new token that every start returns.
- **Timing:** the host probe's start times (6–10 s) include its own dialog watching, which walks every accessible app every 0.7 s and blocks its loop. The jail's start with the token, which watches nothing, took 0.02–0.06 s (below).
- **Portal helpers need the session's activation environment** (`WAYLAND_DISPLAY`). A real login has it. The probes set it with `UpdateActivationEnvironment` and restart only this bus's portal processes, found by the PID owning each name.

### The desktop worker under its §5.4 profile (`worker.py`, `worker_inside.py`)

Profile:
- `bwrap --unshare-all --die-with-parent --new-session --clearenv`: no network, no home, `/usr` and `/etc` read-only, a tmpfs `/tmp`.
- The session bus only through `xdg-dbus-proxy --filter --talk=org.freedesktop.portal.Desktop --talk=org.a11y.Bus`.
- The accessibility bus's socket bound in, with `AT_SPI_BUS_ADDRESS` set.

| Inside the jail | Result |
|---|---|
| The keyring (`org.freedesktop.secrets`) | unreachable (ServiceUnknown) |
| The Shell (`org.gnome.Shell`) | unreachable (ServiceUnknown) |
| AT-SPI | works: sees gnome-shell, Calculator, both portal backends |
| RemoteDesktop with the token | no dialog. CreateSession + SelectDevices + SelectSources + Start in **0.02–0.06 s** |
| A frame of the stream (`OpenPipeWireRemote` → GStreamer `pipewiresrc`) | first frame in **0.08–0.12 s**, 1920×1080 RGB |
| Pointer clicks | see the next section |

The portal's Request/Response round trip works through the proxy, and so does fd passing (`OpenPipeWireRemote`). GStreamer is the system's (1.28), already on any GNOME desktop: no new Python dependency.

### Pointer and pixel coordinates at 100 %, 125 % and 150 %

Calculator's 7 and C were clicked from inside the jail through the RemoteDesktop session, on a stream of the monitor that held Calculator, and the result was read through AT-SPI. Both monitors were shared.

| Scale | Stream `size` (logical) | Frame size | Absolute motion, logical point | Absolute motion, physical point | Absolute + relative |
|---|---|---|---|---|---|
| 100 % | 1920×1080 | 1920×1080 | 7 hit, C hit | (same) | — |
| 125 % | 1536×864 | 1920×1080 | 7 miss, C miss | 7 hit, C hit | — |
| 150 % | 1280×720 | 1920×1080 | 7 miss, C miss | C hit; **7 refused** (`Invalid position` at y = 720) | 7 hit with relative motion in **logical** units; miss in physical |

- **Absolute positions are frame pixels** (physical) relative to the stream, but **the stack refuses any position past the stream's logical size.** On a scaled monitor that leaves the bottom and right edges out of reach: at 150 % only the top-left two thirds of each side (44 % of the screen). The refusal comes either from xdg-desktop-portal 1.21 or from mutter 50; worth reporting upstream.
- **Relative motion is in logical units**, unaccelerated for this virtual device. So any point is reachable: absolute to a reachable point, then relative for the rest.
- **Frames are physical pixels.** A frame pixel maps to the Shell's logical point as stream position + pixel × (stream width ÷ frame width).

## What this means for Stage 6

- **Perception:** AT-SPI first, as planned. Turning on `toolkit-accessibility` is part of setup. Chrome and Electron need `--force-renderer-accessibility`.
- **Pixels:** not from the Screenshot portal. They come from the ScreenCast stream of the same RemoteDesktop session that carries input, so one consent in setup covers both. A frame takes ~0.1 s, so the session stays open only while a task uses the computer.
- **Acting:** AT-SPI actions where they exist. For text, use EditableText when present, else focus plus typed keys. For switches and unnamed or actionless controls, use a portal pointer click at the element's bounds. The portal path is a first-class one, not a rare fallback.
- **Geometry:** an element's logical point = its window's buffer origin + its WINDOW extents. SCREEN extents are never used. ShellBridge's `ListWindows` must return buffer rects (frame rects alone are wrong) and each window's PID, so an AT-SPI app can be matched to its window.
- **Pointer moves:** absolute motion to (point − stream position) × (frame width ÷ stream width) when that lies inside the stream's logical size. Otherwise move absolutely to the nearest point that does, then relatively, in logical units, for the rest. Either way, re-read the pointer's landing (AT-SPI or a frame) before pressing.
- **Isolation:** the §5.4 profile holds with portals and AT-SPI working. The a11y bus itself is unfiltered: whatever is on it can read and act on every accessible app. That is what "using the computer" consents to.

## Not measured

- Firefox: the snap can't run in a private session. Measuring it means a deb Firefox or the real session with the owner's consent.
- Watching the Shell bridge's name from inside the jail (`--see=org.gnome.Shell`) and unicast `ControlRevoked`: Stage 6 builds and tests those.
- Accuracy of Chrome's and Electron's SCREEN extents; not needed.
- A real (non-virtual) monitor with fractional scaling; the virtual monitors used the same scale paths.
- Pointer acceleration on relative motion with a real session's settings. The probe's virtual device had none; Stage 6 checks the landing point after every relative move.

## Harness lessons (two mistakes, both fixed)

1. **The accessibility bus.**
   - What happened: before 2026-10-23 the e2e test and these probes shared the real session's runtime directory (`/run/user/1000`). The private session's accessibility bus launcher bound `/run/user/1000/at-spi/bus`, the real session's accessibility bus, and removed it on exit. The real launcher still runs, but its socket file is gone, so apps started since can't reach it until the next login.
   - Fix: `scripts/e2e-stage1.sh` and `run.sh` now give the private session its own runtime directory under `/tmp`, with nothing of the real one linked in, and undo the private document portal's mount before cleanup.
2. **A camera, briefly.**
   - What happened: one diagnostic run read the stream straight from PipeWire, not through the portal's fd. At that point the private Shell still used the person's PipeWire. It also named the portal's node id through `target-object`, which takes a serial or a name. Nothing matched, so the stream fell back to the default video source: one of the laptop's cameras. One frame (all zeros by the probe's count, never saved) was read in about 2.5 s.
   - Fix: the probes now run their own PipeWire and WirePlumber with no device monitors, refusing to start if it has any device. The frame grab uses `path` (the node id) with `node.dont-fallback`, and only ever the portal's fd. Stage 6 must do the same: never `target-object` with a portal node id, and always no fallback.
