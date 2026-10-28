# 0035. Fixes from the owner's own chats; graded eval tasks; Hey Mei sees the screen without asking

Status: accepted
Date: 2026-10-28
Deciders: owner
Supersedes: 0024 (in part: talking over Mei through speakers without the canceller)
Superseded-by: —

## Context

The owner reported that in Live, Mei "wouldn't finish saying the response and cuts mid and starts listening", and that asked to look at the screen, it said it couldn't. They asked for every chat to be gone through, not only those two, and for Mei to be tested in every way possible, with a collection of tasks from easy to extremely hard.

All 24 conversations and 114 tasks (Oct 24–28, all on Gemini Flash Lite) were read. What they showed:

- **Mei heard itself.** Talking over Mei was on, echo cancellation off, and the output the laptop's speakers. Mei's own first words stopped it mid-reply and came back as the person's request: "No worries at all!" was heard as "No worry.", "Sounds good!" as "Sounds", and so on, four times in a row. 0024 allowed that combination although it said it only works with earphones.
- **"I can't see your screen."** The system prompt never said Mei can look at the screen. Models answered from `windows_list`, or not at all.
- **Five tasks stopped with "kept repeating the same step".**
  - **The repeat guard:** it refused a third look at the same window even when the clicks between had worked and changed it.
  - **Chrome:** it shows assistive tools one element, the window frame. Every look at a web page returned nothing to act on, and the model then tried to click by position on snapshots taken without a picture, which is refused.
- **Plain-text plan steps** (`["find it", …]`) were refused twice.
- **Memory recall matched words only.** "Do you know what I like?" got "nothing saved" while "I love Android" was saved.
- **X11 tools.** Models reached for `xdotool` and `wmctrl`, which fail on Wayland.
- **Log noise.** The Shell-only check logged "refused" when Settings edited a memory (it only labels the edit), so the log looked like the Shell was being refused.

## Decision

- **Talking over Mei through speakers needs the echo canceller.** Without it (and not into earphones), the barge-in watch doesn't run, and voice says why once. That is where the failure came from: the watch was listening where it couldn't tell the two voices apart. Matching what was heard against Mei's own sentence was tried and dropped: it hid the symptom, and could drop a real interruption.
- **The prompt tells the model it can see the screen** when the desktop tools are offered:
  - look with `desktop_observe` before answering about the screen;
  - use `picture=true` for what controls don't show;
  - look again after acting;
  - X11 tools don't work here.
- **A window with two elements or fewer is also pictured.** The picture is what there is to see. This is the interim measure for Chrome; the cause is that Chromium builds its accessibility tree only when it detects an assistive technology. Making it do so is a change to the whole desktop, left to the owner.
- **The repeat guard counts the same call only since something else last succeeded.**
- **Plan steps and criteria may be plain text.** The tool's schema still shows only the object form, since not every provider takes `anyOf`.
- **Recall fills its free places with what matters most.** Recall matched words only, so a question about the person in general matched nothing, however many memories there were. Now the places left after word matches (up to eight in all) go to the pinned, then most used, then most recent memories. Only the ones the request matched count as the person's words for policy, as before (§17.5); a test guards that.
- **Requests made with "Hey Mei" look at the screen without asking, as Live does.** The owner confirmed this.
- **Spoken "stop" and "yes, do it" stay exact matches after the clean-up step.** A fuzzy "yes" could approve something unasked.
- **The evals have levels:**
  - easy, medium, hard, very hard, extremely hard (`--level`), with a per-level line in the report;
  - nine new tasks from the chats: memory recall, the screen (typed and spoken), a note from the screen, sorting, the three largest files, a cleanup with an injection, and remembered places with an injection.
  - The world can show a window: a fake desktop with controls and text, never a fake picture.

## Consequences

- Scripted run: 28/28. Gemini Flash Lite (the owner's model): 27/27 before the spoken screen task was added, and 3/3 on that task alone.
- The two memory tasks fail on the code before this change and pass after.
- The screen tasks pass on both the old and the new code in the eval. The eval doesn't reproduce the conversation history and Chrome's empty tree from the real chats; the prompt and the picture fallback address those directly.
- Through laptop speakers with the canceller off, talking over Mei is now off: turn the canceller on, or use earphones.
- Notifications are drawn by the Shell, not an app window, so Mei can't see them yet. A whole-screen look is open.
