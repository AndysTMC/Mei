# 0028. Enter ends listening; the pause adapts to how finished a sentence sounds; a drop goes with what's said

Status: accepted
Date: 2026-10-25
Deciders: owner
Supersedes: 0026 (in part: the 8 s pause)
Superseded-by: —

## Context

The owner used 0026's build and reported:
- **Ending dictation sent the words to Mei.** They dictated "Hey, are you there?" and pressed Enter. Mei answered it, and a few seconds later the same words showed up in the box again. Ending dictation cleared the "dictating" mark before the last words arrived, so those words went to Mei as a spoken request.
- **Enter with the mic on sent the message.** It also closed the small popup, which then reopened with the answer. The owner expects Enter to turn the mic off.
- **The box shrank.** Text dictated while the popup was closed made the box nearly zero high when it reopened, until clicked. Its height had been measured while it was hidden.
- **Editing during dictation makes little sense.** It fights the words arriving.
- **A file dropped during a conversation wasn't seen.** What's said goes to Mei from the runtime, and the attachment only travelled with typed messages.
- **8 seconds is too long.** The owner asked for what popular voice assistants do. OpenAI's realtime voice waits about half a second of silence by default; newer assistants decide the turn by whether the sentence sounds finished.

## Decision

- **Ending dictation keeps its last words dictation.** Mei stops listening for more, but the words still being heard go into the box, never to Mei.
- **Enter while the mic is on stops it.** The words stay in the box to edit, and a second Enter sends. During a conversation with the popup open, Enter ends the conversation; focus sits on the voice button, since the box is hidden then.
- **While the mic writes, the box is read-only and a little dimmer.** It scrolls to the latest words. When the mic stops, the box is yours to edit.
- **The box is measured again when shown.** It is never measured while hidden.
- **The pause adapts.**
  - **Default:** 0.8 s of quiet sends what was said.
  - **Unfinished sentences:** after words a sentence doesn't end on ("and", "um", "the", "because"…), or a single word, Mei waits at least 2.5 s.
  - **Settings:** they still choose the base, from 0.3 to 10 s in steps of 0.1. A longer base is never shortened.
  - **Pressing again** sends at once, as before.
  - **Migration 6:** a stored 8 s, which was 0026's default for one day, becomes 0.8 s; any other stored value is kept.
- **A drop during a conversation goes with what's said next.** The extension hands the attachment to the runtime (`VoiceAttach`, the Shell only). It goes with the next spoken request, and the chip clears when that request starts. A request that fails to go keeps it for the next.

## Consequences

- Dictation never sends anything by itself, and nothing dictated reaches Mei until the person sends it.
- Replies come about 0.8 s after a finished sentence, and about 2.5 s after one left hanging.
- The word list is English. Other languages get the plain base pause until they have theirs.
- Recognized words aren't corrected yet. Cleaning up misheard words (by the model, or by biasing the recognizer toward the person's words) is open.
