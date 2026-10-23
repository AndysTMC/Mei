# 0022. Computer use as measured: AT-SPI first; one RemoteDesktop session for pixels and input; the desktop worker behind a filtered bus

Status: accepted
Date: 2026-10-23
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

ADR-8 in the architecture (§10, §23) chose AT-SPI first, with portals for pixels and input, and left the details to spike 0b. The spike (`spikes/0b/REPORT.md`) ran on GNOME Shell 50, xdg-desktop-portal 1.21 and AT-SPI 2.60, in a private headless Shell with two virtual monitors at 100 %, 125 % and 150 %. Its findings change parts of ADR-8:

- **The Screenshot portal refuses a background service.** It shows its dialog only for the focused app, and answers response 2 otherwise.
- **RemoteDesktop with `persist_mode=2` needs one consent.** The person picks the screens, allows interaction, and shares. Its restore token then starts sessions with no dialog, also after a Shell restart. Inside the worker's jail a start took 0.02–0.06 s, and a frame of its ScreenCast stream ~0.1 s.
- **Absolute pointer positions are the stream's frame pixels,** but positions past the stream's logical size are refused. On a scaled monitor the bottom and right edges can't be reached that way: at 150 %, a third of each side. Relative motion is in logical units and reaches them.
- **AT-SPI extents.** SCREEN extents are zero for GTK4 apps on Wayland. WINDOW extents plus the window's buffer origin give the Shell's logical point at every scale; the frame origin is off by the client-side shadow.
- **AT-SPI coverage gaps.**
  - Calculator, GTK4 and Electron expose usable trees, and Chrome does with `--force-renderer-accessibility`.
  - A GTK4 switch has no action.
  - Chrome has no EditableText.
  - Many controls are unnamed.
- **The §5.4 profile holds.** Under bubblewrap with no network and no home, and the session bus only through `xdg-dbus-proxy` (portal and a11y bus), AT-SPI, the portal and fd passing work. The keyring and the Shell are unreachable.

## Decision

- **Perception is AT-SPI first.** The worker returns a pruned tree with ids bound to a snapshot (§10.1). Setup turns on `toolkit-accessibility`, with the person's consent, and tells them which apps need a flag. Firefox wasn't measured: the snap can't join a private session. Its coverage is reported per app by `doctor` once Stage 6 runs on a real session.
- **Pixels and input share one RemoteDesktop session.**
  - Its ScreenCast stream is the only pixel source; the Screenshot portal isn't used.
  - Setup's "Using the computer" step asks for the one consent: all screens, interaction allowed.
  - The runtime keeps the restore token in the keyring and stores the new one that each start returns.
  - A session is opened when a task starts using the computer and closed when it stops, so the Shell's sharing indicator shows exactly when Mei can see or act.
- **Frames are read in the desktop worker** through the portal's PipeWire fd, with the system's GStreamer (`pipewiresrc`). The stream is named by its node id (`path`), never by `target-object`, and with `node.dont-fallback`: a miss must fail, not fall back to a camera. No Python dependency is added.
- **Acting** works in this order:
  - an AT-SPI action;
  - EditableText;
  - focus (`Component.grab_focus`) and typed keys;
  - a pointer click at the element's bounds.

  The pointer path is a first-class one, not a rare fallback. Switches, unnamed and actionless controls, and canvases need it.
- **Geometry** lives in one module (`desktop/geometry.py`):
  - **An element's logical point** is its window's buffer origin plus its WINDOW extents. SCREEN extents are never used.
  - **A frame pixel's logical point** is the stream's position plus pixel × (stream width ÷ frame width).
  - **A pointer move** goes absolute to the point in frame pixels when it lies within the stream's logical size. Otherwise it goes absolute to the nearest point that does, then relative, in logical units, for the rest.
  - **Before pressing**, the landing is checked through AT-SPI, or through a frame where there's no tree.
- **ShellBridge `ListWindows`** returns each window's buffer rect, frame rect, monitor, title and PID, so an AT-SPI app is matched to its window.
- **The desktop worker's profile is §5.4's:**
  - bubblewrap with no network and no home;
  - the session bus only through `xdg-dbus-proxy --filter`, which allows talking to the portal and the a11y bus and seeing the Shell's name (for the control token);
  - the a11y bus's socket bound in.

  The a11y bus itself is unfiltered: whatever is on it can read and act on every accessible app. That is what "using the computer" consents to.
- **Tests and spikes run on a private everything:** home, session bus, runtime directory, and a PipeWire with no devices. Nothing of the real runtime directory is linked in. The spike broke this twice (see the report) before it was fixed.

## Consequences

- One dialog in setup, then none. Revoking access in GNOME Settings invalidates the token, and the next task asks again.
- On a scaled screen, a pointer move to the bottom or right edge takes two steps and one more check.
- The worker needs GStreamer's PipeWire plugin (`gstreamer1.0-pipewire`). `install.sh --check` and `doctor` report it.
- Firefox coverage stays unknown until measured on a real session.
- The refusal of positions past the logical size looks like a bug in the portal or mutter. Mei works around it, and a fix upstream would make the workaround unnecessary, not wrong.
