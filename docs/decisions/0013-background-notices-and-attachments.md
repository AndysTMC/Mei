# 0013. The Shell notifies while attached and the runtime when it isn't; an attached selection is untrusted content

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: —
Superseded-by: —

## Context

Stage 4 lets tasks run in the background (§18.4). Before it, the popup reopened itself whenever a task finished or asked for something, which takes the keyboard from whatever the person is doing; and with the extension off (screen locked, extension disabled, Shell restarting) nothing told them at all. "Ask about this" attaches the focused window's title and selected text to a question: the person chose to attach it, but someone else wrote it.

## Decision

- **Who notifies.** While the Shell extension is attached, it notifies: it knows whether the popup already shows that conversation. A finished task (completed, failed, stuck), an approval card, or a question in a conversation the popup isn't showing becomes a notification; clicking it (or "Review") opens that conversation. A quick answer (the task ran under 20 s) to the conversation the person just used still reopens the popup, as before. Stopped and interrupted tasks raise nothing.
- **The runtime notifies when nobody else can.** With no Shell attached, it sends the same notices through `org.freedesktop.Notifications`, naming only the conversation, not its content (they can show on the lock screen). "Attached" means the verified Shell bridge is attached, not a client's own claim to be the Shell, so another program can't silence them.
- **The history list shows tasks in progress first**, from a per-conversation `active` state the projection keeps current from task events; the panel indicator shows work in any conversation.
- **An attached selection is untrusted content.** It travels with the message (stored in its metadata), reaches the model inside an `<attachment trust="untrusted">` block (redacted like observations), and taints the task (0010). Items named only in it get untrusted provenance, so acting on them takes a card that says a page suggested them. The person's typed words stay the only instructions.

## Consequences

The nested-Shell e2e covers a long task across an extension restart and across a Shell restart (both notify when the task finishes), a notification opening its conversation, a task finishing while the extension is off (the runtime's notice arrives), and the shortcut attaching a selection. `tests/test_ask_about_this.py` and the `attached_injection` eval cover the attachment rules.

## Known limits

- A task that finishes while no notification server runs at all (the Shell restarting) raises no notice: the runtime logs that it couldn't show it, and the history list still shows the result.
- Disabling the extension (as the lock screen does) removes its notifications from the tray.
- The selection is the primary selection: apps that don't set one (some Electron apps) attach only the window title.
