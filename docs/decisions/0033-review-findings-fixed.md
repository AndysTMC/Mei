# 0033. Fixes from the October reviews: pipes, questions, drafts, cards, PDFs, downloads, keys, the pointer, purge; noise suppression primed

Status: accepted
Date: 2026-10-28
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Outside reviews of the code (2026-10-26) listed findings that 0030–0032 didn't cover. Each one below was checked against the code and confirmed. A test reproduces it, fails without its fix, and passes with it.

## Decision

- **A named pipe can't hang the runtime.** Files are opened non-blocking, then refused if they aren't regular files. A pipe with no writer used to hold the open, and with it the whole runtime.
- **A question with choices also takes another answer.** The popup offered "Something else…", but the runtime refused anything but a choice. A hand-off still takes only its own answer.
- **A message that couldn't be sent goes back in the box.** The box was cleared before the runtime took the message, so a refusal (no provider, runtime unreachable, an error) lost it.
- **Question cards are bounded:**
  - at most 12 options a field, 80 characters an option or choice;
  - 200 characters a label, 2,000 characters a question.
  - Each option is a widget built at once in the compositor. A model asking with thousands is refused.
- **PDFs are read only inside bubblewrap.** Without it, Mei doesn't read PDFs at all, rather than parsing them in the person's session.
- **One voice model failing doesn't stop the rest downloading.** Each says its own error, and voice starts with what arrived. Installs were already atomic: verified, then renamed into place.
- **A key never goes over plain http to another computer.** https anywhere, or http to this computer only. Chat and model listing both refuse otherwise, and say why.
- **One act at a time drives the pointer and keys,** from bringing its window forward to the end of its lease. If the window can't be brought forward, the act doesn't happen, rather than typing wherever focus is.
- **Noise suppression is primed with 0.1 s of silence after each reset** (found while testing these fixes). Its first output after a reset could leave Kroko writing nothing at all for the whole utterance. In 4 of 30 wake-word runs, "I pause the music" came out as nothing, while the same audio without noise suppression was heard. Primed, all four are heard every time.
- **Purge deletes Mei's data only once no runtime holds the store's lock.** Otherwise it keeps everything and says how to stop the runtime first.

## Consequences

- Someone using a model server on their network over plain http with a key needs https, or no key.
- These remain open:
  - a total budget for the size of a model request (larger work);
  - CI;
  - lifecycle guards for calls that outlive the extension;
  - accessibility and theme items;
  - the installer's version check.
