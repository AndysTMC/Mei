# 0037. A request fits what the model can take

Status: accepted
Date: 2026-10-29
Deciders: owner
Supersedes: —
Superseded-by: —

## Context

Each model call sent the whole conversation and every result of the current task. Each result was capped (50,000 characters), but the total wasn't. A long conversation, or a task that read several large files, went past the model's context:
- **Cloud models:** an error.
- **Local ones (Ollama):** the start silently cut, the system prompt with it.

The architecture (§8.3) had planned a token budget and left it for later.

## Decision

- **A request is fitted to a budget in characters,** about four to a token, tool definitions included: 400,000 for cloud models (they take 128k tokens and more), 64,000 for models on this computer.
- **The system prompt and the person's request stay whole.**
- **Earlier turns of the conversation go first,** oldest first, in whole exchanges. The model is told how many were left out.
- **Then the current task's older tool results are shortened** to 2,000 characters, with a note to run the tool again for the rest. Its three newest results are never shortened.

## Consequences

- **Long conversations keep working:** they lose their oldest turns from the model's view, not from the person's history.
- **The budgets are estimates.** A model with less context than its kind's budget can still overflow. A per-model context size (§17) is the way to make them exact.
- **Ollama:** its own context size (`num_ctx`) is left at Ollama's default here.
