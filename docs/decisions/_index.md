| ID | Title | Status | Date | Supersedes |
|---|---|---|---|---|
| 0001 | Keep a GSettings copy of API keys stored in libsecret | superseded by 0005 | 2026-08-22 | — |
| 0002 | Run the agent in a separate Python user service; the extension is UI only | accepted | 2026-10-20 | — |
| 0003 | Talk between Shell and runtime over the session bus with dbus-fast | accepted | 2026-10-20 | — |
| 0004 | Install per user with a script; the extension activates at the next login | accepted | 2026-10-20 | — |
| 0005 | Keep API keys only in the keyring; the runtime reads them there | accepted | 2026-10-20 | 0001 |
| 0006 | API keys cross the bus encrypted, go only to configured endpoints, and never come back in errors | accepted | 2026-10-21 | — |
| 0007 | The agent loop keeps a durable action ledger; waiting is a state, and recovery is a table | accepted | 2026-10-21 | — |
| 0008 | Authority lives outside the model: a policy engine with presets over a fixed floor | superseded in part by 0010 | 2026-10-21 | — |
| 0009 | Outcomes are checked by the runtime; badges claim only what checks established | accepted | 2026-10-21 | — |
| 0010 | A named folder stops vouching for changes once Mei has read a document; authority binds to real targets | accepted; first known limit closed by 0014 | 2026-10-21 | 0008 (in part) |
| 0011 | Commands run in a per-conversation jail; a writable folder counts as possible data loss; host commands ask every time | accepted | 2026-10-21 | — |
| 0012 | A memory is kept by whose words carry it; recall is data, and the person's own memories may name places | accepted | 2026-10-21 | — |
| 0013 | The Shell notifies while attached and the runtime when it isn't; an attached selection is untrusted content | accepted | 2026-10-21 | — |
| 0014 | File changes go through the folders policy judged, held open; a link can't redirect them after the check | accepted; first two known limits closed by 0015 | 2026-10-22 | 0010 (in part: a known limit) |
| 0015 | Reads and the command sandbox use the folders policy judged, held open, too | accepted; first three known limits closed by 0016 | 2026-10-22 | 0014 (in part: two known limits) |
| 0016 | Checks, probes, and app launches use what was judged; a secret appearing during a command stops it | accepted | 2026-10-22 | 0015 (in part: three known limits) |
| 0017 | Voice: one interface per part with local and cloud backends; device by measurement; PipeWire's own protocol | accepted | 2026-10-22 | — (revises ADR-7 in the architecture) |
| 0018 | Voice as built: push to talk first, cloud speech falls back to this computer, no echo cancellation yet | accepted; GPU part superseded by 0019, echo cancellation by 0024 | 2026-10-22 | — (builds on 0017; narrows §11.4–11.5) |
| 0019 | The GPU on demand: woken when used, let go when idle, with the CPU covering meanwhile | accepted | 2026-10-23 | 0018 (in part: the GPU) |
| 0020 | The conversation is requests and replies; what Mei waits for is the input; details on demand | accepted | 2026-10-23 | — (narrows §18.2) |
| 0022 | Computer use as measured: AT-SPI first; one RemoteDesktop session for pixels and input; the desktop worker behind a filtered bus | accepted | 2026-10-23 | — (revises ADR-8 in the architecture) |
| 0023 | Computer use as built: Mei makes way before input, a stop from the Shell ends the task, and pictures reach models that see | accepted | 2026-10-23 | — (builds on 0022; narrows §10.3) |
| 0024 | Echo cancellation for barge-in: PipeWire's canceller, private, only while Mei talks through speakers | accepted | 2026-10-23 | 0018 (in part: no echo cancellation; revises §11.4) |
| 0025 | "Hey Mei" pauses while another app records | accepted | 2026-10-23 | — |
| 0026 | Listening ends when the person ends it; an 8 s pause before sending; the shortcut keeps the popup closed | accepted | 2026-10-24 | 0018 (in part: how listening ends) |
| 0027 | Files and text dropped on Mei are taken by a window of its own; dropped files count as named by the person | accepted | 2026-10-24 | — |
| 0028 | Enter ends listening; the pause adapts to how finished a sentence sounds; a drop goes with what's said | accepted | 2026-10-25 | 0026 (in part: the 8 s pause) |
| 0029 | Voice seams (engine registry, turn detector, clean-up chain), noise suppression, a tone while Mei works, asking before looking at the screen in chat | accepted | 2026-10-26 | — |
| 0030 | Read aloud stands on its own; the voice worker says its version; Stop reaches speech not yet playing | accepted | 2026-10-28 | 0029 (in part: how Read aloud plays) |
| 0031 | Authority checks are conjunctive and fail closed; content with no source stays local; the Shell is its bus name | accepted | 2026-10-28 | — |
| 0032 | A reply the model cut short says so | accepted | 2026-10-28 | — |
| 0033 | Fixes from the October reviews: pipes, questions, drafts, cards, PDFs, downloads, keys, the pointer, purge; noise suppression primed | accepted | 2026-10-28 | — |
| 0034 | The popup grows into a large page: what Mei is doing, and attachments, read-only; the runtime draws PDF pages | accepted | 2026-10-26 | — (builds on 0023) |
| 0035 | Fixes from the owner's own chats; graded eval tasks; Hey Mei sees the screen without asking | accepted | 2026-10-28 | 0024 (in part: talking over Mei through speakers without the canceller) |
| 0036 | Mei can look at the whole screen, not only inside one window | accepted | 2026-10-29 | — |
| 0037 | A request fits what the model can take | accepted | 2026-10-29 | — |
