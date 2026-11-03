"""Tidying what was heard: the clean-up chain seam (decision 0029).

What the recognizer wrote goes through a chain of steps, each one `clean(text) -> text`: fillers and
stutters out, then (as they are added) punctuation, a second pass, grammar that doesn't change the
meaning. The raw words are always kept beside the result, so the person can put them back with one
click. A step that fails is skipped, never fatal: the words are worth more than the polish.
"""

import difflib
import functools
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger("mei.voice")
WORDS = "/usr/share/dict/words"


class Cleanup(Protocol):
    name: str

    def clean(self, text: str) -> str: ...


@dataclass(frozen=True)
class Cleaned:
    raw: str  # as the recognizer wrote it
    text: str  # after the chain

    @property
    def changed(self) -> bool:
        return self.text != self.raw


class Chain:
    def __init__(self, steps: Sequence[Cleanup] = ()) -> None:
        self.steps = tuple(steps)

    def __call__(self, raw: str) -> Cleaned:
        text = raw
        for step in self.steps:
            try:
                text = step.clean(text) or text  # a step never empties what was said
            except Exception:  # noqa: BLE001  a step that breaks: the text as it was
                log.exception("voice clean-up: %s failed", step.name)
        return Cleaned(raw, text)


# Sounds that are never words. "Like" and "you know" are words too often to take out by rule.
_FILLER = re.compile(r"(?:^|(?<=[\s,]))(?:u+[hm]+|e+r+m*|h+m+|m+h*m+)(?:[,.]|(?=\s)|$)\s*", re.I)
# The same one or two words said twice in a row ("I I want", "the the", "can you can you").
_STUTTER = re.compile(r"\b(\w+(?:'\w+)?(?:\s+\w+(?:'\w+)?)?)(?:\s+\1\b)+", re.I)
# What the person meant to say again isn't a stutter: "very very", "no no", "bye bye".
_DOUBLED_ON_PURPOSE = frozenset("very really so no yes yeah bye ha that had".split())
# Keep ambiguous words such as "like", even beside a modal or hesitation: "you might like this"
# and "I like um jazz" both use it as a verb. Only remove the filler sounds above.
# A sentence that opens like a question ends with "?"; any other ends with ".".
_QUESTION = re.compile(r"^(?:hey \w+,? )?(?:can|could|would|will|should|shall|is|are|am|was|were|do|does|did|have|"
                       r"has|had|what|what's|when|where|who|whom|whose|why|how|which)\b", re.I)
_PROPER = {w.lower(): w for w in ("Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March "
                                   "April June July August September October November December Mei").split()}


class Rules:
    """Fillers and stutters out, a capital to start, the days, months and Mei capitalised, and a mark to
    end: plain rules, no model. Ambiguous words stay; raw words are kept by the chain."""

    name = "rules"

    def clean(self, text: str) -> str:
        text = _FILLER.sub("", text)
        text = _STUTTER.sub(lambda m: m.group(0) if m.group(1).lower() in _DOUBLED_ON_PURPOSE else m.group(1), text)
        text = re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s{2,}", " ", text)).strip(" ,")
        if text.isupper():  # some recognizers write in capitals
            text = text.lower()
        text = re.sub(r"\bi\b", "I", text)
        text = re.sub(r"\bi'(m|d|ll|ve)\b", lambda m: f"I'{m.group(1)}", text)
        text = re.sub(r"\b\w+\b", lambda m: _PROPER.get(m.group(0).lower(), m.group(0)), text)
        if text and text[-1] not in ".?!":
            text += "?" if _QUESTION.match(text) else "."
        return text[:1].upper() + text[1:]


# Words too common to be a misheard name, when there's no word list to ask.
_COMMON = frozenset("""a about after all also an and any are as at be because been but by can could do does for from
get go had has have he her here him his how i if in into is it its just know like make me more my no not now of on
one or our out over say see she so some take than that the their them then there these they this time to up us use
very was way we well were what when which who will with would you your open send show call start check play stop
please tomorrow today""".split())


@functools.cache
def _dictionary() -> frozenset[str]:
    """Ordinary words, lower-case (the system's word list; names in it are capitalised and left out)."""
    try:
        return frozenset(w for w in Path(WORDS).read_text(errors="replace").split() if w.islower()) | _COMMON
    except OSError:
        return _COMMON


def _sound(word: str) -> str:
    """A rough key for how a word sounds: consonants mostly, spelled one way ("Kakoro" ~ "Kokoro")."""
    w = re.sub(r"[^a-z]", "", word.lower())
    for a, b in (("ph", "f"), ("ck", "k"), ("qu", "kw"), ("q", "k"), ("x", "ks"), ("z", "s"), ("c(?=[eiy])", "s"),
                 ("c", "k"), ("gh", "g"), ("th", "t"), ("sh", "s"), ("wh", "w"), ("y", "i")):
        w = re.sub(a, b, w)
    head, rest = w[:1], re.sub(r"[aeiou]", "", w[1:])
    return re.sub(r"(.)\1+", r"\1", head + rest)


class Boost:
    """The person's words (app names, names from memory and chats, their own list) put back where the
    recognizer heard something close: by sound and by spelling, over one to three heard words.
    An ordinary word is never replaced on its own, and a span never starts or ends with one ("to
    Kakoro" is "to Kokoro"); terms that are ordinary words (Files, Settings) need no help and get none."""

    name = "boost"
    MIN_SOUND = 0.8
    MIN_SPELLING = 0.6

    def __init__(self, terms: Sequence[str] = ()) -> None:
        words = _dictionary()
        self.terms = [(t, t.lower().replace(" ", ""), _sound(t)) for t in dict.fromkeys(terms)
                      if len(t) >= 4 and any(w.lower() not in words for w in t.split())]

    def clean(self, text: str) -> str:
        if not self.terms:
            return text
        words = list(re.finditer(r"[A-Za-z][A-Za-z']*", text))
        ordinary = _dictionary()
        picks: list[tuple[int, int, str]] = []  # (start word, end word, term)
        taken: set[int] = set()
        for n in (3, 2, 1):
            for i in range(len(words) - n + 1):
                span = range(i, i + n)
                if taken.intersection(span):
                    continue
                heard = [w.group(0) for w in words[i:i + n]]
                joined = "".join(heard).lower()
                exact = next((t for t, letters, _ in self.terms if letters == joined), None)  # "fire fox"
                if exact is None and (heard[0].lower() in ordinary or heard[-1].lower() in ordinary):
                    continue
                best = exact or self._closest(joined, n)
                if best is not None:
                    picks.append((i, i + n, best))
                    taken.update(span)
        for i, j, term in sorted(picks, reverse=True):
            text = text[:words[i].start()] + term + text[words[j - 1].end():]
        return text

    def _closest(self, heard: str, n: int) -> str | None:
        best, best_score = None, 0.0
        for term, letters, sound in self.terms:
            if heard == letters:
                return term
            if n > 1 and term.count(" ") + 1 > n:
                continue
            if abs(len(heard) - len(letters)) > 0.4 * len(letters):
                continue
            spelling = difflib.SequenceMatcher(None, heard, letters).ratio()
            heard_sound = _sound(heard)
            sounds = difflib.SequenceMatcher(None, heard_sound, sound).ratio()
            if sounds >= self.MIN_SOUND and spelling >= self.MIN_SPELLING and spelling + sounds > best_score:
                best, best_score = term, spelling + sounds
        return best


def default_chain(boost: Sequence[str] = ()) -> Chain:
    return Chain([Rules(), Boost(boost)])
