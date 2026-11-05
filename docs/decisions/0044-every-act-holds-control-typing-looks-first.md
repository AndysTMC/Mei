# 0044. Every act holds control; typing looks at the focus first

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Computer use (0022, 0023) prefers asking the app itself (an AT-SPI action, EditableText, `grab_focus`) to injecting input. Those were treated as needing no input, so they took no control lease and never checked control. A review showed a press, or a field's text replaced, still going through after the person had taken control back, or while a frozen core had stopped renewing.

The password hand-off looked only at the element named. Typing with no element (at whatever has the focus, as on a screen picture) never checked what had it, and typing into a named element trusted that focusing it had worked.

## Decision

- **Every act holds control** for as long as it lasts, one at a time, AT-SPI actions included. The worker checks control just before each native call, as it already did before each key and pointer event. Only injected input still needs the screen session and the window brought forward. A call already made to an app can't be taken back.
- **Text is typed only where the focus is known and isn't a password field.** Just before typing (after any window was raised or element focused), the worker looks up what has the focus. If it's a password field, or nothing can be told (a whole-screen picture, an app that shows nothing to accessibility tools), the person is asked to type it, as for a named password field.
- **A key (Return, a shortcut) may go where the focus can't be told,** since canvases need them, but never into a password field.

## Consequences

`tests/test_computer.py` covers native actions without control, after a revoke, and with control, and typing at a focus that is a text field, a password field, or unknown. The nested computer-use run (`scripts/e2e-computer.sh`) passes with these changes.

Typing into apps without accessibility support (some canvases and games) is always handed to the person.
