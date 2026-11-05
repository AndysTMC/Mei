# 0042. What a model on this computer wrote stays off cloud models

Status: accepted
Date: 2026-11-05
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

The privacy choices (§13.5) keep file contents and local-only memories off cloud models, and they are applied to each tool result and action summary when a request is built. Nothing marked what a local model *wrote*. A review reproduced the gap: with "Share files with cloud models" set to Never, a local model read a private file and said what was in it. After a switch to a cloud model, that value reached it in two ways: as the earlier reply when the conversation went on, and as an episode in the system prompt of a new conversation. History search and a memory the local model inferred were two more ways in. The original observation was withheld, but what had been derived from it was not.

Tracking where each piece of text came from, and carrying that through replies, episodes and memories, is the full fix. It is a larger change to the stored data. This decision is the interim rule until then.

## Decision

- **A cloud model never gets what a local model wrote.** When a request goes to a cloud model:
  - an earlier reply from a task a local model ran is replaced by a note that it was kept on this computer;
  - an episode from such a task isn't recalled;
  - a memory such a task inferred isn't recalled, and isn't shown through the memory tools;
  - a history search result that quotes such a reply is withheld, like a file Mei may not share.
- **The person's own words still go,** in the conversation and in memories they stated or kept (0041). A cloud model can see what was asked, not what the local model answered.
- **Whose model ran a task** is read from the provider the task recorded. A task whose provider can't be read counts as local.
- **History search results from before this change** can't say whose replies they quote, so they stay off cloud models.
- **Nothing the person sees changes.** Their history stays whole. Only the copy sent to the model is filtered, and nothing is deleted or compacted.

## Consequences

`tests/test_agent_loop.py` reproduces the switch: a local model reads a private file and says its value; then, on a cloud model, the same conversation, a new one, a history search and an inferred memory all leave the value out, while the person's earlier question is still sent. Reverting any one of those paths makes the test fail.

After a switch to a cloud model, it sees that earlier answers exist, not what they said. A person who wants an earlier local answer used should paste it in or say it again.

## Known limits

- A memory whose task is gone (deleted with its conversation) can't be traced, and is recalled as before.
- Text a local model wrote into a file is that file's content, and the file rules decide whether it goes.
- This applies whatever the file-sharing setting is, "Always" included: a local reply can also hold local-only memories, which never go.
