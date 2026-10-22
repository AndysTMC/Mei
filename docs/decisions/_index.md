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
| 0015 | Reads and the command sandbox use the folders policy judged, held open, too | accepted | 2026-10-22 | 0014 (in part: two known limits) |
