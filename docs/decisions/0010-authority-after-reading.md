# 0010. A named folder stops vouching for changes once Mei has read a document; authority binds to real targets

Status: accepted
Date: 2026-10-21
Deciders: owner (delegated)
Supersedes: 0008 (in part: the user-anchored row, provenance, and who may change settings)
Superseded-by: —

## Context

Two reviews of Stage 3 reproduced ways around 0008:

- The request "Read the invoice in Downloads and tell me the total. Don't change anything" named Downloads. The invoice told the model to trash another file there, and policy allowed it, because the file was inside a folder the person named. Anchors also came from every message in the conversation, so a folder named in an earlier task still vouched for a new one.
- Provenance and grants judged paths as written. A symlink inside a named folder could lead out of it, and a symlink swapped while an approval card was up redirected the approved write.
- Any program on the session bus could change the setting that lets programs other than the Shell give Mei requests, and then give one.
- Completion checks could read any GSettings key and look at any path.
- A URL like `https://localhost.example.com` counted as a local model.

## Decision

- **After reading, only exact names count.** A task becomes *tainted* when Mei reads content others wrote: a file's text, or a content search. Folder listings don't taint it. Once it is tainted, a local change goes ahead without a card only if the person named that item exactly: its path, or a file by its own name. Being inside a folder they named isn't enough any more. Hands-off's allowance for model-found items stops too. The card says why ("Mei read a document in this task…") and offers "For this task", so a batch needs one card. The invoices slice now takes one card instead of none, which is within the plan's "at most one".
- **This task's words only.** Anchors come from the task's own request and steers, not from earlier tasks in the conversation.
- **Content naming an item outweighs the folder.** If a document names a specific item, that item is untrusted even inside a named folder, and the card says it was suggested by a file.
- **Real targets.** Resources are judged, recorded, and granted by where they really resolve. Path rules resolve their own roots too, for a Downloads that links to another drive. Just before an action runs, its resources are worked out again. If they changed, the action is denied, or asked again with a new card, never carried out under the old approval.
- **Settings can't open the gate.** Only the Shell can turn on `clients.external_input` or delete conversations. The change notice also covers letting programs in and moving a provider's endpoint.
- **Checks are tools.** `setting_equals` reads only the allow-listed settings, and path checks skip denied and sensitive paths.
- **Local means loopback.** An endpoint is local only if its parsed host is `localhost` or a loopback address and its URL has no user part.

## Consequences

`tests/test_security.py` reproduces every case above. The eval suite gains `read_only_injection`: the scripted model obeys the injection, the card stops it, and a careful person denies it.

## Known limits

- A symlink swapped in the milliseconds between the re-check and the write isn't caught. Closing that needs file operations through directory descriptors (`openat` with `O_NOFOLLOW`), which can come with Stage 4's sandbox work.
- File names in a listing can carry instructions but don't taint the task. That is a trade-off against asking on every file task. Listings stay untrusted for provenance.
- The Settings window still can't be told apart from any other `gjs` program, so it can change the approval preset and cloud sharing, with the notice as the safeguard (§13.7).
