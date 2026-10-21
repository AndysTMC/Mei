"""Deciding what a `memory.save` becomes (§17.4). Pure, so the rules are tested on their own.

A saved memory is replayed into every future prompt, so a poisoned one is a long-lived injection.
The rules therefore go by where the words came from, not by what the model says:

- the person's own words in this task carry it → active, *user-stated*;
- the task read content others wrote and the person's words don't carry it → *pending review*;
- otherwise it's the model's inference → active and labelled *inferred* when automatic saving is
  on, pending review when it's off (unless the person asked Mei to remember).

Anything that looks like a secret is refused outright.
"""

import re
from dataclasses import dataclass
from typing import Literal

from mei.obs import redact
from mei.store.memory import words

SUPPORTED = 0.6  # share of the memory's content words the person must have written themselves
MAX_CHARS = 500
_ASKED = re.compile(r"\b(remember|don'?t forget|do not forget|keep in mind|note that|from now on)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Verdict:
    status: Literal["active", "pending_review", "refused"]
    provenance: Literal["user_stated", "inferred", "untrusted"]
    reason: str


def judge(text: str, user_texts: list[str], *, tainted: bool, auto_save: bool) -> Verdict:
    if not text.strip() or len(text) > MAX_CHARS:
        return Verdict("refused", "inferred", f"a memory is one fact, up to {MAX_CHARS} characters")
    if redact(text) != text:
        return Verdict("refused", "inferred", "it looks like a secret (a key or token); Mei never stores those")
    if support(text, user_texts) >= SUPPORTED:
        return Verdict("active", "user_stated", "the person said it")
    if tainted:
        return Verdict("pending_review", "untrusted", "it may have come from something Mei read, so the person "
                                                      "reviews it first")
    if auto_save or any(_ASKED.search(t) for t in user_texts):
        return Verdict("active", "inferred", "inferred from the conversation")
    return Verdict("pending_review", "inferred", "automatic saving is off, so the person reviews it first")


def support(text: str, user_texts: list[str]) -> float:
    """How much of the memory is in the person's own words: the share of its content words they wrote."""
    mine = set(words(text))
    if not mine:
        return 0.0
    theirs = {w for t in user_texts for w in words(t)}
    return len(mine & theirs) / len(mine)
