# 0029. The popup grows into a large page: what Mei is doing, and attachments, read-only; the runtime draws PDF pages

Status: accepted
Date: 2026-10-26
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

The owner asked for a large page in Mei's popup after seeing History. It has two uses:

- **Watching computer use.** Mei already keeps a picture of the screen after each look (decision 0023), in the conversation's artifacts. The person only sees the steps as text, and the chip in the top bar.
- **Looking at an attachment.** Before this, the chip ("Attached: notes.txt") and a sent message's note were labels only.

Constraints met on the way:

- **The Shell has no Poppler typelib,** so it can't draw a PDF itself. PDFs come from anywhere, and their parsers are a classic way in (the reason `pdftotext` runs jailed, decisions 0015 and 0016).
- **Pictures of the screen are the person's.** Action views go to every attached client, including programs the person allowed in (§13.7).
- **The popup makes way before every pointer or keyboard act** (0023). A page that shows Mei clicking closes while it clicks.
- **The Shell's menu manager closes a menu on Escape** from the menu's own `captured-event`, connected in `addMenu`.
- **St's image loader fills the box it is given.** `St.TextureCache.load_file_async` makes the actor the whole box and draws the picture into it, out of shape or off to one side.

## Decision

- **One page, many contents.**
  - **The page:** `LargePage` (`src/ui/popup/largePage.ts`), a top bar with Back, a title and the content's actions.
  - **A content:** an object with `actor`, `title`, `actions` and `destroy`.
  - **Adding a file type** means adding one small viewer in `src/ui/viewers/`, chosen by `fileKind` (name first, then the content type).
- **Size and motion.**
  - **Size:** 65% of the primary monitor's width at 16:10, kept 24 px inside the work area at the sides and bottom. That is 1248×780 on 1920×1080 and 832×520 on 1280×800 (`pageSize.ts`).
  - **Placement:** centred under the whole top bar. While the page shows, the popup's BoxPointer hangs from the panel instead of Mei's button, which isn't quite in the middle; the chat hangs from the button again. Opening the menu puts it back under the button, so the popup re-applies this on open.
  - **Transition:** the page fades and resizes like History.
  - **Leaving:** Back or Escape return to the chat. The popup's own Escape handler is connected before `addMenu`, so it runs first, and Escape no longer closes the popup while the page shows.
  - **Pictures:** each is loaded at its fitted size (from its known size or the file's header, never enlarged) and centred.
- **What Mei is doing (the work page).**
  - **In the chat:** the running-steps block shows the latest picture as a thumbnail above the steps. Clicking it opens the page.
  - **On the page:** the picture fills the left and updates after each look. A narrow column on the right shows the steps and what Mei waits for.
  - **Buttons:**
    - *Pause / Go on.* Pause holds the task before its next act.
    - *Stop.* The kill switch's path, then a cancel of the task.
    - *Take over.* Disabled: it and a live stream come with a later hidden session.
  - **Runtime:**
    - `ActionView.pictures` counts the pictures an action kept.
    - `LatestPicture` returns the newest picture's path and size, from the conversation's own artifacts only, and only to the Shell.
    - `Pause` holds a task (in memory). The next act waits in `WAITING_RESOURCE` with "Paused by you", as it does while the person uses the pointer. `Resume` (Go on) lets it continue. Anyone may pause, as anyone may cancel. Going on still needs the Shell (or allowed input).
- **Attachment viewers.** Clicking the chip, or a sent message's note, opens the attachment. Several files step with Previous and Next.
  - **Text, code, logs and CSV:** monospace and selectable. Only the first 256 KiB shows, with a note.
  - **Markdown:** the conversation's renderer, with a Plain text toggle.
  - **Images:** fitted to the page; a click shows them at their own size, scrolling.
  - **PDF:**
    - `PdfInfo` counts the pages with `pdfinfo`. `PdfPage` draws one page with `pdftoppm`, as the person scrolls to it, two at a time, and says its size in pixels: each page gets exactly its room.
    - Both run in the same bubblewrap jail as `pdftotext`. The jail sees only `/usr`, the fonts, and the one file, by its descriptor.
    - The PNG comes back on stdout and is kept in `$XDG_RUNTIME_DIR/mei/pages` (gone at logout; at most 200 pages).
    - Without poppler's tools, a PDF shows as "anything else".
  - **Anything else:** the file's icon, name, size and kind. A file whose name says nothing but whose content type is text shows as text.
  - **Every file page:** "Open in its app" (the default handler) and "Show in Files" (`org.freedesktop.FileManager1.ShowItems`). Both close the popup.
  - **Read-only:** nothing here writes, renames or moves a file.

## Consequences

- The person can see what Mei saw, and hold it between acts, without leaving the chat. When Mei clicks or types, the popup still closes first (0023). Reopened, it is back on the page, with the newer picture.
- Pause is not durable. A runtime restart interrupts the task anyway (§15), and recovery doesn't depend on the hold.
- A task that never used the computer has no picture, so no thumbnail.
- Stop from the page is the kill switch plus a cancel, so it also ends a task that hasn't used the computer yet.
- The Shell reads attached files itself (it runs as the person), except PDFs, which only the runtime's jailed tools parse. The runtime's file methods take absolute, normalized paths and answer only the Shell.
- Tests:
  - **Unit:** `runtime/tests/test_large_page.py` (latest picture, Pause, PDF pages with real poppler) and `tests/largePage.test.ts` (size, file kinds, caps, the work view).
  - **Nested-Shell e2e** (`scripts/e2e-stage1.sh`): opens each viewer and checks its size, toggles Markdown, zooms an image, and leaves with Escape. It opens files from the chip and from a sent message. It opens the work page from the thumbnail, then pauses, goes on, and stops.
  - **The e2e's picture is planted:** the nested Shell has no screen session, so a dev-only hook (`SetDebugPicture`) stands in for the latest picture. The real lookup is covered by the unit tests.

## Known limits

- No live stream and no Take over yet: the picture is the latest look, not the screen now.
- A large text file is cut at 256 KiB. Even that is taller than the GPU's largest texture, so while it fades in, Clutter logs that it couldn't make an offscreen buffer. It still draws correctly.
- Large images load whole, off the main loop, through St's texture cache.
- PDF pages are drawn at one width. Zooming a PDF page isn't offered.
