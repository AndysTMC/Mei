# 0029. Voice gets seams (an engine registry, a turn detector, a clean-up chain); Mei asks before it looks at the screen in chat

Status: accepted
Date: 2026-10-26
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

The owner asked for the voice pipeline to be easy to change ("loosely couple… more rapid iterations, more experimenting"), without a rewrite, a framework, or big models. Engines (Smart Turn, Moonshine, KittenTTS, TEN VAD) are to be tried behind the same interfaces, some kept as experimental. The owner also decided:
- **Noise suppression:** always on.
- **The boost list:** app names, words from memory and recent chats, and a list of their own.
- **Dictated words:** tidied, with the raw words kept and one click to restore them.
- **Long answers:** a soft tone when an answer takes more than about a second, then check-ins at 10, 100 and 1,000 s.
- **Talking over Mei:** only recognized words stop it.
- **While dictating:** no blinking cursor.
- **Names:** "Live" for the voice conversation.
- **Replies:** read aloud from each one.
- **The screen:** in chat Mei asks before it looks; in Live it doesn't, with a setting.

Measured on this machine:
- **GTCRN (sherpa-onnx, 0.5 MB):** at 5 dB of fan-like noise, Kroko's word errors went from 13 % to 3 %. Clean speech was unchanged (0 %). It costs about 14 % of one core.
- **Kroko's hotwords** (modified beam search, with or without a BPE vocabulary) made no difference to rare names (5–6 of 9 right either way). They also made decoding 25–70 % slower.
- **Kroko writes its first word about 1.4 s after a voice begins,** whatever the word ("Stop", "Pause the music"):
  - **Waiting for a word before stopping Mei:** Mei stopped about 1.6 s after the person began, against 0.4 s, and Mei's own echo spoiled what was heard meanwhile.
  - **Holding Mei's voice at once and waiting for a word:** 4 runs in 10 heard no word at all through the echo canceller.

## Decision

- **The engine registry** (`voice/engines.py`):
  - **One row per engine**, with its part, label, status (stable, experimental, archived), whether it runs in the cloud, whether it is optional, and the models it needs.
  - **The worker's builders** (`voice/build.py`) are keyed by the same ids. Contract tests check that every engine the settings can name is registered and that every local one has a builder.
  - **What starts voice:** the models needed come from the registry. An optional engine (noise suppression) is offered for download but never blocks voice.
- **The turn detector** (`voice/turns.py`):
  - **Asked once per pause** (and again if the last words arrive during it): how much quiet ends the turn. `WAIT` means no timer.
  - **The default:** the word list of 0028. A model detector (Smart Turn) goes behind the same interface and gets the turn's audio.
- **The clean-up chain** (`voice/cleanup.py`):
  - **Steps:** a recognized utterance goes through a chain of steps. Today these are rules (fillers, stutters, capitals) and the boost list.
  - **The raw words go along:** `voice.partial` finals carry `raw`. After dictation, if the words were tidied, a Restore button puts the words as heard back into the box.
  - **A failing step is skipped.**
- **The boost list is a clean-up step, not a decoder setting.**
  - **What it does:** it puts the person's words back where something close was heard, by sound and spelling, over one to three heard words.
  - **What it leaves alone:** an ordinary word (the system word list) is never replaced on its own, and a span never starts or ends with one. Terms that are ordinary words (Files, Settings) are skipped.
  - **Where the words come from:**
    - installed apps' menu names;
    - capitalised non-dictionary words in active memories and the last 200 messages the person wrote;
    - `voice.boost_words` from Settings.
  - **Freshness:** gathered again when listening starts, at most once a minute.
- **Noise suppression:** GTCRN, streaming, on whatever Mei listens to. Not on the wake word or the barge-in watch, where it would cost cycles while nobody is talking to Mei.
- **Talking over Mei stays as 0024 has it:** a voice for 0.2 s stops it. Only recognized words stopping Mei is not adopted yet, for the measurements above. The way open is to listen as now and, if what was heard has no words (a cough), let Mei go on from the sentence it was saying.
- **While Mei works on a spoken request:**
  - a soft two-note tone after 1 s;
  - then "Still on it." at 10 s, a longer line at 100 s, and another at 1,000 s.
  - These are played outside any reply, so they don't count as Mei speaking.
  - Each new spell of thinking (after a spoken approval, for example) starts the series over.
- **Read aloud:**
  - **The button:** a speaker button in each reply's footer when voice is ready (`VoiceReadAloud`, Shell only).
  - **What is read:** code and tables are left out as in spoken answers.
  - **Stopping:** pressing it while Mei speaks stops it.
- **Seeing the screen:**
  - **The rule:** `desktop.observe` names a `screen` resource.
    - In chat, policy asks, offering once, this task, or always.
    - When the task was asked for in Live (its request was spoken), it doesn't ask.
  - **The setting:** `computer.see_without_asking` makes chat behave like Live. It is in Settings as "Look at the screen without asking".
- **The UI:**
  - **Live:** the voice button reads "Live" and "End Live", and Settings says "Press Live".
  - **Dictation:** shows no caret.
- **The voice controller is split:**
  - spoken replies and approvals → `voice/replies.py`;
  - "stop" and "yes, do it" → `voice/phrases.py`;
  - models and downloads → `voice/catalog.py`;
  - the tone and check-ins → `voice/waiting.py`.

## Consequences

- Adding an engine means a registry row, its model, and a builder. Trying one as experimental hides it from setup.
- The boost list can't fix what it can't match ("and jolly" for "Anjali" stays). It never touches ordinary words, so it can't cause new mistakes in ordinary speech.
- Names of three letters or fewer ("Rao") aren't learned.
- Noise suppression's model is a 0.5 MB download, offered in Settings with the other models. Until it is downloaded, voice runs as before.
- Approvals for the screen use the existing scopes. "In this chat" and "until I log out" come with the approval wording change.
