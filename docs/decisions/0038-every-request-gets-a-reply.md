# 0038. Every request gets a reply, in the order things were said; Chrome's tree is woken

Status: accepted
Date: 2026-10-29
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

The owner saw requests with no reply, in the small popup and the large page alike, and messages out of order in voice mode. Their chats show two causes.

- **No reply when the runtime ended a task.** A reply was only ever what the model last said. Endings the runtime imposed left none:
  - stopped for repeating the same step (5 of the owner's tasks on 2026-10-26);
  - stopped at the step limit;
  - stopped by the person, or failed.

  How it ended lived only on the task (`error`). Each consumer read that itself, or didn't:
  - the timeline showed nothing;
  - voice said "Sorry, I couldn't do that." for failures only;
  - the popup's notice showed failures only.

  The next request's model saw two requests in a row, with no word of how the first one ended. What had streamed before a stop or a failure vanished from view.
- **Out of order.** What the person says while a task runs joins that task (§8.1): 16 of the owner's spoken messages did. The timeline hung a task's reply under its first message, and listed the person's later messages on their own after it. So the reply showed before things said earlier. The small popup, whose "latest request" was then one of those messages, showed nothing at all.

The owner also saw Chrome show Mei almost nothing (decision 0035 took a picture instead). The cause: Chromium builds what's inside a window only once a client asks one of its objects for its attributes, as screen readers do. Mei's reader never asked. The session already has accessibility on (`toolkit-accessibility`, `org.a11y.Status.IsEnabled`), so nothing about the person's settings needs changing.

## Decision

- **The runtime replies for any ending the model didn't write,** where every task ends (`repo.finished_event`):
  - failed, stopped, or blocked without the model's outcome: always, after whatever Mei said on the way;
  - the model's own ending (an answer, or `task.finish`): only if it said nothing since the person last spoke.

  The reply is a first-person line for how it ended ("I stopped before finishing.", "I couldn't finish this.", "Stopped."), then why (the task's error). A reply that was streaming is that message, finished with the ending, so voice doesn't say its words twice. The reply is marked `metadata.ended`.
- **Voice and the popup say no more than the reply.** Voice's own "Sorry, I couldn't do that." and the popup's notice for a failed task are gone. An interrupted task keeps its notice: it can still go on.
- **The timeline follows the turns of a task:** its request, then each thing the person added. Each turn is followed by the latest thing Mei said before the person spoke again. That reply's details are the notes and the steps taken in that turn, plus any earlier turn's steps that had no reply of their own. The outcome goes with the last reply. While the task runs, progress shows the steps since the person last spoke.
- **Mei asks each window it reads for its attributes,** and gives a window's first look up to 0.15 s and 0.35 s more while its tree still grows.
- **The object placeholder U+FFFC is dropped from element text.** A web page's text has one for each child object, never words, and Chrome's panels were outlined as rows of them.

## Measured

In the nested Shell (`scripts/e2e-computer.sh`), Google Chrome with a fresh profile opened a local page. Mei looked at the window and pressed its "Mei test button" by name:
- **Before:** the outline was the window's frame alone, and the press had nothing to name.
- **After:** the outline had Chrome's toolbar, the page's heading and its button, and the press changed the page's title. All 14 checks passed.

## Consequences

- Every request and every message added to a task is answered on screen, in voice, and in what later requests show the model.
- Tasks that ended before this keep having no reply: writing one now would need renumbering their conversations' messages.
- A window's first look takes up to 0.5 s longer when its tree keeps growing; 0.15 s when it doesn't.
- The "picture when a window shows ≤2 elements" fallback (0035) stays, for apps with no tree at all.
