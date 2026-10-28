# 0032. A reply the model cut short says so

Status: accepted
Date: 2026-10-28
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Every provider adapter treated any stop reason as a normal end. A reply cut off at the model's length limit, or stopped by its safety filter, was stored and shown as a complete answer.

- **OpenAI-style:** `finish_reason` `length` or `content_filter`.
- **Anthropic:** `stop_reason` `max_tokens` or `refusal`.
- **Gemini:** `finishReason` `MAX_TOKENS`, or `SAFETY` and its relatives.
- **Ollama:** `done_reason` `length`.

A stream that ends with no end marker at all was already reported as cut off (`IncompleteResponse`).

## Decision

- **`Done` carries `cut`:** `""`, `"length"` or `"filtered"`, mapped from each provider's own reasons.
- **The reply is kept as it came,** and its metadata records `cut`.
- **The popup shows a line under it:** "Cut short: the model reached its length limit." or "Stopped by the model's safety filter."
- **Nothing retries by itself.** The text so far is the person's to keep, and asking again is their choice.

## Consequences

- A long answer that stops mid-sentence is no longer mistaken for the whole answer.
- Tool calls cut short still fail as invalid arguments, as before.
