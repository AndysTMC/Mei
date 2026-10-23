# 0023. Computer use as built: Mei makes way before input, a stop from the Shell ends the task, and pictures reach models that see

Status: accepted
Date: 2026-10-23
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Stage 6 built computer use on decision 0022. Running it end to end in a nested Shell (`scripts/e2e-computer.sh`) turned up things neither the architecture (§10) nor 0022 said:

- **Mei's popup took the input meant for apps.** You ask in the popup and approve there. While it is open it holds the Shell's grab: the first pointer click only closed it, and every key went into Mei's own message box.
- **A GTK4 check box has no AT-SPI action,** like a GTK4 switch. Toggling it needs the pointer, so it needs the screen permission.
- **The scripted model finished a task before the kill switch reached the runtime.** With the runtime frozen, the worker stopped typing at once. When the runtime came back, it read the failed act's reply and the model's next turn before the KillSwitch call.
- **Super+Escape is mutter's** (restore shortcuts), and Super+Shift+Escape too (cancel input capture).
- **Models differ on images.** Anthropic takes a picture inside a tool result, Gemini as inline data, and Ollama on the message. OpenAI's chat format allows only text in tool messages. Some models reject images.

## Decision

- **Make way before input.** Before any pointer or keyboard act, the runtime asks the Shell (`MakeWay`) to close Mei's popup and bring the target window to the front. AT-SPI acts don't need it.
- **Who stopped input decides what follows.** The worker reports whether input stopped because of the Shell (the kill switch, the chip, the Shell or Mei's extension going away), the lease running out, or the runtime. Stopped by the Shell, the tasks that used the computer are cancelled as soon as the runtime hears it, before anything else it had queued. A lease running out only fails the act. The end of a lease after a finished act is not a stop at all, and the screen session stays open for the rest of the period of use.
- **The kill switch is Super+Alt+Escape,** beside Mei's other Super+Alt shortcuts. It is changeable in Settings and in setup's Shortcuts step. The chip in the top bar does the same.
- **Pictures:**
  - **Kept** in the conversation's artifacts (deleted with it), not in the ledger.
  - **Sent** only the latest one, and only where the result may be sent at all.
  - **Encoded** as each provider takes them; for OpenAI-style chat, a user message right after the tool results.
  - **Refused:** a model that rejects images is asked again without them, as one that can't use tools is.
- **Labels with outward words** (send, submit, buy, delete…) ask even for a check box ("Send me news"). That is 0022's rule working as meant, and the setup text says acts can ask.

## Consequences

- Asking Mei in the popup and then watching it work means the popup closes when Mei starts clicking or typing. The chip in the top bar shows it is working; the popup reopens with a click.
- Forms with GTK4 check boxes or switches need the screen permission from setup; text fields, buttons and menus don't.
- A frozen runtime can't let a stopped task go on. A runtime that is merely slow still finishes the act it was in, which input-wise already stopped.
- The e2e test covers it, and shows nothing reaches the person's session:
  - **Checks:** a form through AT-SPI only, a password hand-off, setup's one consent, a check box by pointer, a canvas from its picture at 100 % and 150 %, a pause while the mouse moves, and no dialog after setup.
  - **Stopping:** the kill switch with the runtime frozen (input stops at once), the runtime killed, and the extension disabled.
  - **Isolation:** a private keyring, runtime dir and PipeWire with no devices.
