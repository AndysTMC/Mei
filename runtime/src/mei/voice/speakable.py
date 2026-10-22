"""A reply, streaming in as text, turned into sentences to speak (§11.3). Markdown is for the screen:
headings, bullets, emphasis, and links are spoken as plain words, and code blocks and tables are
left out, with one "The details are on screen." in their place."""

import re

ON_SCREEN = "The details are on screen."
_ABBREVIATIONS = {"e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "prof", "st", "approx", "no", "fig"}
_BOUNDARY = re.compile(r"[.!?…]+[\"')\]]*\s+")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S*[^\s.,;:!?)\]\"']")  # not the sentence's own full stop
_LIST = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_MARKS = re.compile(r"(\*\*|__|\*|_|~~|`)")


def plain(line: str) -> str:
    """One line of markdown as words to say."""
    heading = bool(_HEADING.match(line))
    item = bool(_LIST.match(line))
    text = _HEADING.sub("", _LIST.sub("", line))
    text = _URL.sub("a link", _LINK.sub(r"\1", text))
    text = _MARKS.sub("", text).strip()
    if (heading or item) and text and text[-1] not in ".!?:;,":
        text += "."  # so items and headings are said as separate phrases
    return text


class Sentences:
    def __init__(self) -> None:
        self._line = ""  # the line still arriving
        self._said = 0  # characters of it already given out as sentences
        self._code = False
        self._left_out = False

    def feed(self, text: str) -> list[str]:
        """More of the reply; returns the sentences now complete."""
        out: list[str] = []
        self._line += text
        while "\n" in self._line:
            line, self._line = self._line.split("\n", 1)
            out += self._finish_line(line)
            self._said = 0
        if not self._code and not self._unspoken(self._line):
            spoken = plain(self._line)
            cut = _last_boundary(spoken)
            if cut > self._said:
                out += _split(spoken[self._said:cut])
                self._said = cut
        return out

    def flush(self) -> list[str]:
        """The reply is complete: whatever is left, and the note about what was left out."""
        out = self._finish_line(self._line)
        self._line, self._said = "", 0
        if self._left_out:
            out.append(ON_SCREEN)
            self._left_out = False
        return out

    def _finish_line(self, line: str) -> list[str]:
        if line.strip().startswith("```"):
            self._code = not self._code
            self._left_out = True
            return []
        if self._code or self._unspoken(line):
            return []
        return _split(plain(line)[self._said:])

    def _unspoken(self, line: str) -> bool:
        if line.lstrip().startswith("|"):  # a table row
            self._left_out = True
            return True
        return False


def _ends(text: str) -> list[int]:
    """Where each complete sentence in `text` ends, skipping abbreviations ("e.g.", "vs.")."""
    ends = []
    for m in _BOUNDARY.finditer(text):
        before = text[:m.start()].split()
        if before and before[-1].lower().rstrip(".") in _ABBREVIATIONS:
            continue
        ends.append(m.end())
    return ends


def _last_boundary(text: str) -> int:
    return (_ends(text) or [0])[-1]


def _split(text: str) -> list[str]:
    cuts = [0, *_ends(text), len(text)]
    pieces = (text[a:b].strip() for a, b in zip(cuts, cuts[1:]))
    return [p for p in pieces if p and any(c.isalnum() for c in p)]
