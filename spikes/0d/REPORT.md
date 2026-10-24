# Spike 0d — drag and drop from Wayland apps onto Mei (GNOME Shell 50.1, Mutter 50.1)

Run: `spikes/0d/run.sh [out] [scenario-prefixes]`. Private headless Shell (one 1280×800 virtual
monitor), private home, bus and runtime dir, as the e2e. A throwaway extension stands in for Mei's
button, a GTK4 app (`source.py`) is the drag source, `dropwin.js` the drop window, and a virtual
pointer drags. Times are CLOCK_MONOTONIC in every process, so they compare.

## What the Shell gets

Read from the Shell's own `ui/xdndHandler.js` and `ui/dnd.js` (extracted from `libshell-18.so`):

- Mutter's `Meta.Dnd` (`global.backend.get_dnd()`) has three signals and no methods: `dnd-enter`,
  `dnd-position-change (x, y)` and `dnd-leave`. `XdndHandler` turns them into `drag-begin`, positions
  for drag monitors, `handleDragOver` on the picked actor's delegate, and `drag-end`.
- It never calls `acceptDrop`, and nothing hands the Shell the drag's data. `dnd-leave` fires at the
  release whether or not anything took the drop.
- The Shell's own uses only react to hovering: the Activities button and hot corner open the overview,
  and in the overview the dash activates a window so the drop lands on a real one. The overview drops
  its modal grab while an xdnd drag is on (`overview.js`, `shouldBeModal = !this._inXdndDrag`).

Measured (scenario A): a file dragged onto a Shell actor gives `drag-begin`, 23 positions and 8
`handleDragOver` calls, no `acceptDrop`, and the source's drag is cancelled (GDK reason `error`).
**A Shell actor can't receive a drop from a Wayland client.**

## A window of Mei's under the button

Mutter 50's API for this: `Meta.WaylandClient.new_subprocess` (+ `owns_window`), and on
`Meta.Window`: `set_type`, `hide_from_window_list`, `move_frame`, `override_constraints`, `make_above`.

| Scenario | Result |
|---|---|
| Normal window over the button | constrained to the work area: placed at y=32, under the bar; no drop |
| Normal + `override_constraints(MONITOR…)` | still y=32 |
| DOCK type (`set_type` at `window-created`) | placed at y=0, over the button's rect |
| DOCK, chrome still reactive | the pick hits the panel button; drag never enters the window; cancelled |
| DOCK, button and panel made non-reactive | **drag enters 1–2 ms after the window's first frame; drop received** (file path, and text) |
| TOOLTIP, DND, NOTIFICATION, OVERRIDE_OTHER, `make_above` | all stay in `window_group` (none moves to `top_window_group`), y=32; no drop. Changing to OR types logs a Mutter CRITICAL (`stack_position >= 0`) |
| Pointer held still after the window appears | still entered (+2 ms): Mutter re-picks the drag focus without motion |
| Focus | stayed on the source app in every run; the drop window was never active |
| Hiding the window at `drag-end` | cancels the drop in flight (`gdk_drop_finalize … DROPPING`): it must wait for the data |

The DOCK window sits under the panel (it's in `window_group`, the bar is chrome above it), so it is
never seen; the Shell draws the highlight on the button.

## In time?

From the drag reaching the button to the drag entering the window:

| How the window's process was started | enter after reaching the button |
|---|---|
| Already running, GL renderer, first show | 185–230 ms (GSK's GL start-up) |
| Already running, GL, second show | 18 ms |
| Already running, `GSK_RENDERER=cairo`, first show | 16–18 ms |
| Started at `drag-begin` (cairo), drag took ~490 ms to reach the button | 19 ms |
| Started when the drag reached the button (cairo) | 142–145 ms |
| Process start alone (gjs + GTK4 to ready) | 114–128 ms |

A quick fling (button reached 33 ms after `drag-begin`, released 100 ms later) misses when the process
starts at `drag-begin` (window at 100–105 ms) and works when it is already running (18 ms).

## The popup

Mei's popup is a `PopupMenu` with a modal grab.
- Open before the drag: the press in the other app never starts a drag (3 tries, no `drag-begin`).
- Opened in the middle of a drag (hover 300 ms): positions stop, the drop window gets `leave`, and the
  drag never ends: no `drag-end`, the source never hears back, until the app quits.

**So the drop target is the button, and the popup opens after the drop.**

## Meanwhile

Other ways to attach that work today, or with little work:
- "Ask about this" for selected text.
- A FileChooser-portal attach button: no Shell limits, but a new control in the popup (decision 0020
  asks for fewer).
- Files' "Open With" through a desktop file with `%F`: needs a launcher that hands the paths to the
  runtime.
