# 0027. Files and text dropped on Mei's button are taken by a window of Mei's own; dropped files count as named by the person

Status: accepted
Date: 2026-10-24
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

People want to drag a file from Files (or text from a page) onto Mei and ask about it. Spike 0d
(`spikes/drop/REPORT.md`) measured what GNOME Shell 50.1 on Wayland allows:
- **The Shell sees a drag but not its data.** Mutter's `Meta.Dnd` gives the Shell `dnd-enter`,
  `dnd-position-change` and `dnd-leave`, and nothing else. A file dropped on a Shell actor is cancelled
  at the source.
- **A window can take the drop, even one that appears mid-drag.** It works if it is a DOCK (only
  docks may sit over the top bar's area) and if the button and panel above it stop being pickable.
  Measured: the drag enters it 18 ms after reaching the button when its process is already running
  with cairo drawing, and 185–230 ms with GL. Focus stayed with the source app in every run.
- **The popup can't be a target.** It is a modal `PopupMenu`. Open first, the press in the other app
  never starts a drag. Opened mid-drag, it strands the drag (no `drag-end` at all).

## Decision

- **Drop on the button.** While a Wayland drag is over Mei's panel button:
  - the button is highlighted (grey, as decision 0020);
  - a borderless, see-through GTK4 window of Mei's (`dist/dropWindow.js`, run with gjs) sits exactly
    under it, as a DOCK hidden from the window list;
  - the button and the actors holding it are unpickable until the drag leaves or the drop is in.
- **What the window does.** It takes a copy only (never a move), of local files by path or of text.
  Non-local files (a browser link) are taken as their addresses, as text. Each drop goes to the
  extension as one line on stdout, checked there.
- **Its process.** The extension starts it through `Meta.WaylandClient`, so `owns_window` says which
  window is Mei's, when any drag begins. It uses `GSK_RENDERER=cairo`, and leaves two minutes after
  the last drag.
- **After the drop**, the popup opens with a chip: "Attached: notes.txt" (more files join, up to 20),
  or "About: “…”" for text. The attachment goes with the next message in the current conversation.
- **Dropped files are named by the person.**
  - The paths (`Attachment.kind = "files"`) are anchors for policy, as if typed: the file itself counts
    as named, and what's inside a dropped folder as the person's (home and `/` stay too broad).
  - Under "Files I point to", what Mei reads from them may go to a cloud model without a card. Under
    "Never", nothing goes.
  - They don't taint the task. Reading one does, as any read does (0010).
  - The model gets the paths, not the contents, in `<attachment kind="files">`, and reads them with the
    file tools, so the reads go through the usual policy, sandbox, size limits and redaction.
- **Dropped text is content others wrote**, like a selection (0013): `<attachment kind="text"
  trust="untrusted">`, redacted, and it taints the task.

## Consequences

- Dragging a file onto "Mei" and asking works from any Wayland or X11 app that offers files or text.
  The person sees one highlight and then the popup with a chip; no window shows or takes focus.
- The runtime validates dropped paths (absolute, normalized, at most 20, text and paths never mixed).
  The extension checks what the window sends.
- Unit tests: `runtime/tests/test_drop_on_mei.py` and `tests/runtimeAttachment.test.ts`. The
  nested-Shell e2e drags a file and then text from a GTK4 app onto the button: the file reaches a
  scripted cloud model through a read with no card.

## Known limits

- **Quick flings.** A drag released on the button within ~120 ms of starting, when no drag happened
  in the last two minutes, misses: the window's process is still starting. The drop is cancelled, and
  the person drops again.
- **The overview.** It hides `window_group`, so a drop on the button there isn't taken.
- **No popup target.** Dropping on the open popup isn't possible while it is a modal menu.
- **Pickability.** While the window is up, the panel itself is unpickable for that drag (for
  example, the Activities hover doesn't fire meanwhile). It is restored on leave, drop, or after
  1.5 s.
- **Sandboxed apps.** Files from a sandboxed app arrive as document-portal paths
  (`/run/user/…/doc/…`). They are named by the person all the same.
- **Meanwhile.** Until there are other ways in (a FileChooser-portal attach button, Files' "Open
  With" through a desktop file), "Ask about this" and typed paths remain the alternatives.
