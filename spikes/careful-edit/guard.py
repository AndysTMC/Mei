"""Keeping a model to the careful edit: it may tidy, it may not reword.

`marks_only(before, after)`: for a punctuation model. The words come from `before`, untouched; from
`after` only the marks between words and a capital at the start of a word. A model that changed the
letters of a word is not believed for that word.

`words_kept(before, after)`: for a model that writes the whole sentence (T5, an LLM). It lines the words
up and keeps the model's version only where the change is one the careful edit allows: a filler or a
doubled word gone, a sound-alike swapped for its twin, an apostrophe. Everywhere else the words that were
said come back. Neither looks at the reference: this is what would run in Mei.
"""

import difflib
import re

_WIDE = str.maketrans({"，": ",", "。": ".", "？": "?", "！": "!", "、": ",", "；": ";", "：": ":"})
_MARKS = ".?!;:,"  # strongest first
_FILLERS = frozenset("um umm uh uhh er erm hmm mm ah".split())
_TWINS = [
    {"their", "there", "they're"}, {"your", "you're"}, {"its", "it's"}, {"to", "too", "two"},
    {"then", "than"}, {"weather", "whether"}, {"here", "hear"}, {"right", "write"}, {"whose", "who's"},
    {"no", "know"}, {"new", "knew"}, {"by", "buy", "bye"}, {"for", "four"}, {"one", "won"},
    {"lets", "let's"}, {"were", "we're"}, {"break", "brake"}, {"peace", "piece"}, {"week", "weak"},
]


def _key(word: str) -> str:
    return re.sub(r"[^\w']", "", word.lower()).replace("_", "")


def _core(word: str) -> tuple[str, str]:
    m = re.match(r"^(.*?)([.?!;:,]*)$", word)
    return m.group(1), m.group(2)


def marks_only(before: str, after: str) -> str:
    words = before.split()
    out = after.translate(_WIDE)
    stream = [(i, ch.lower()) for i, ch in enumerate(out) if ch.isalnum() or ch == "'"]
    pos, rebuilt = 0, []
    for n, word in enumerate(words):
        core, mark = _core(word)
        key = [ch for ch in core.lower() if ch.isalnum() or ch == "'"]
        span = stream[pos:pos + len(key)]
        if [ch for _, ch in span] != key:
            return before  # the model changed letters: nothing of it is believed
        start, end = (span[0][0], span[-1][0]) if span else (None, None)
        pos += len(key)
        nxt = stream[pos][0] if pos < len(stream) else len(out)
        gap = out[end + 1:nxt] if end is not None else ""
        found = [m for m in _MARKS if m in gap]
        if found:
            mark = found[0]
        if start is not None and out[start].isupper() and core[:1].islower():
            core = core[:1].upper() + core[1:]  # a capital may be added, never taken away
        rebuilt.append(core + mark)
    text = " ".join(rebuilt)
    return text.rstrip(",;:")


def _norm(word: str) -> str:
    return re.sub(r"^[^\w']+|[^\w']+$", "", word.lower())


def _allowed(a: list[str], b: list[str]) -> bool:
    """May the words `a` (said) become `b` (written by the model)?"""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y or x.replace("'", "") == y.replace("'", ""):
            continue
        if not any(x in t and y in t for t in _TWINS):
            return False
    return True


# Said twice on purpose, as the seam's rules have it: "very very", "no no".
_DOUBLED_ON_PURPOSE = frozenset("very really so no yes yeah bye ha that had".split())


def _same_word(said: str, written: str) -> str:
    """The model's token where it only adds a capital or marks around the word; else the word as said."""
    m_said = re.match(r"^(\W*)(.*?)(\W*)$", said)
    m_new = re.match(r"^(\W*)(.*?)(\W*)$", written)
    core, new_core = m_said.group(2), m_new.group(2)
    if new_core != core and not (new_core[:1].isupper() and new_core[:1].lower() == core[:1] and new_core[1:] == core[1:]):
        new_core = core  # "useEffect" stays, "priya" may become "Priya"
    return m_new.group(1) + new_core + m_new.group(3)


def words_kept(before: str, after: str) -> str:
    a_tok, b_tok = before.split(), after.split()
    a, b = [_norm(w) for w in a_tok], [_norm(w) for w in b_tok]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out += [_same_word(x, y) for x, y in zip(a_tok[i1:i2], b_tok[j1:j2])]
        elif op == "delete" and (all(w in _FILLERS for w in a[i1:i2]) or all(
                a[i] not in _DOUBLED_ON_PURPOSE and a[i] in a[max(i - 1, 0):i] + a[i + 1:i + 2]
                for i in range(i1, i2))):
            continue  # a filler or a doubled word dropped
        elif op == "replace" and _allowed(a[i1:i2], b[j1:j2]):
            out += b_tok[j1:j2]
        elif op == "insert" and all(not w for w in b[j1:j2]):
            out += b_tok[j1:j2]  # punctuation alone
        else:
            out += a_tok[i1:i2]  # what was said comes back
    return " ".join(out)


def finish(text: str) -> str:
    """A capital to start and a mark to end, the same way rules+ does it."""
    from rules import _QUESTION

    text = text.strip()
    if text and text[-1] not in ".?!":
        text += "?" if _QUESTION.match(text) else "."
    return text[:1].upper() + text[1:]
