# 0036. Mei can look at the whole screen, not only inside one window

Status: accepted
Date: 2026-10-29
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

The owner asked Mei about a notification on their screen, and Mei couldn't see it. Computer use (§10, decisions 0022–0023) was designed as "look at a window, act in a window":
- **Elements:** a window's controls come from its AT-SPI tree.
- **Pictures:** were added as a crop of that one window.

The ScreenCast stream it captures already holds every monitor whole, but nothing asked for it uncropped. So notifications, the top bar, the dock, and everything outside the window in front were invisible. That was an oversight, not a choice. The owner: "the whole screen look should be inbuilt from the start".

## Decision

- **`desktop_observe` takes `screen=true`:**
  - **The picture:** every monitor, joined in one picture at one scale (logical units), so monitors at different scalings line up as they do on screen.
  - **Size:** at most 1,600 pixels wide.
  - **Gaps:** space between monitors stays dark.
- **The observation lists the open windows by title, app and id,** so the model can look at one for its controls.
- **A screen snapshot has no elements of its own,** only its picture.
  - **Clicking:** a point in it maps back to the logical point under it, as a window picture's does, and is clicked there.
  - **Making way:** closes Mei's popup and raises no window.
  - **Approval:** the act's target is named "screen" for approvals and grants.
- **The prompt says when to use it:** what's on the screen, or something the person sees. Window looks are for acting on controls.

## Consequences

- Notifications, the top bar and anything across monitors can be seen, and clicked from the picture.
- A whole-screen picture costs about the same as a window picture (one image, at most 1,600 wide). Small text may need a window look, or the window picture, to read.
- The computer-use e2e clicks the test canvas from a whole-screen look on two monitors, at 100 % and at 150 %.
