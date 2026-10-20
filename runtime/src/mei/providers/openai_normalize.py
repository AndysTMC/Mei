"""Normalize OpenAI-compatible stream chunks into answer text and reasoning.

Port of src/providers/openaiResponse.ts (streaming path). Providers disagree on where reasoning
goes: `reasoning_content`/`reasoning`/`thinking` fields, `reasoning_details`, typed content parts,
or `<think>`-style tags inside the answer (split across chunks). This keeps reasoning out of the
answer in all of those shapes.
"""

import re

REASONING_TAG_NAMES = ("think", "thinking", "reasoning", "thought", "reasoning_scratchpad")
OPEN_TAGS = tuple(f"<{n}>" for n in REASONING_TAG_NAMES)
CLOSE_TAGS = tuple(f"</{n}>" for n in REASONING_TAG_NAMES)
ALL_TAGS = OPEN_TAGS + CLOSE_TAGS
MAX_TAG_LENGTH = max(len(t) for t in ALL_TAGS)
_ORPHAN_CLOSE = re.compile(r"</(?:" + "|".join(REASONING_TAG_NAMES) + r")>[ \t\r\n]*", re.IGNORECASE)


class StreamNormalizer:
    def __init__(self) -> None:
        self._embedded = _EmbeddedReasoningStream()
        self._thinking = ""

    def consume(self, chunk: object) -> tuple[str, str]:
        """Returns (answer_delta, thinking_delta) for one parsed chunk."""
        choice = _first_choice(chunk)
        if choice is None:
            return "", ""
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else None
        content, typed_thinking = _typed_content(delta.get("content") if delta else None)
        legacy = choice.get("text") if isinstance(choice.get("text"), str) else ""
        embedded_text, embedded_thinking = self._embedded.feed(content or legacy)
        raw = "\n\n".join(_unique([*_structured_reasoning(delta, True), *typed_thinking, embedded_thinking], True))
        thinking = separate_glued_reasoning_blocks(self._thinking, raw)
        self._thinking += thinking
        return embedded_text, thinking

    def flush(self) -> tuple[str, str]:
        text, thinking = self._embedded.flush()
        thinking = separate_glued_reasoning_blocks(self._thinking, thinking)
        self._thinking += thinking
        return text, thinking


def separate_glued_reasoning_blocks(previous: str, delta: str) -> str:
    """Some providers stream `**Title**body**Next**body` summaries with no break between blocks."""
    if not previous or not delta or not delta.startswith("**") or previous[-1].isspace():
        return delta
    if "**" not in delta[2:]:
        return delta
    return "\n\n" + delta


def _first_choice(root: object) -> dict | None:
    if not isinstance(root, dict) or not isinstance(root.get("choices"), list) or not root["choices"]:
        return None
    first = root["choices"][0]
    return first if isinstance(first, dict) else None


def _typed_content(value: object) -> tuple[str, list[str]]:
    if isinstance(value, str):
        return value, []
    if not isinstance(value, list):
        return "", []
    content = ""
    thinking: list[str] = []
    for part in value:
        if not isinstance(part, dict):
            continue
        kind = part.get("type", "").lower() if isinstance(part.get("type"), str) else ""
        if "thinking" in kind or "reasoning" in kind:
            text = _first_string(part, ("thinking", "reasoning", "summary", "text", "content"))
            if text:
                thinking.append(text)
            continue
        content += _first_string(part, ("text", "content", "output_text"))
    return content, thinking


def _structured_reasoning(message: dict | None, preserve_whitespace: bool = False) -> list[str]:
    if not message:
        return []
    parts: list[str] = []
    for key in ("reasoning", "reasoning_content", "thinking"):
        value = message.get(key)
        if isinstance(value, str) and (value if preserve_whitespace else value.strip()):
            parts.append(value)
    details = message.get("reasoning_details")
    if isinstance(details, list):
        for detail in details:
            text = _first_string(detail, ("summary", "thinking", "content", "text")) if isinstance(detail, dict) else ""
            if text:
                parts.append(text)
    return _unique(parts, preserve_whitespace)


def _first_string(record: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _unique(parts: list[str], preserve_whitespace: bool = False) -> list[str]:
    out: list[str] = []
    for part in parts:
        if not part or (not preserve_whitespace and not part.strip()) or part in out:
            continue
        out.append(part)
    return out


def _strip_orphan_close_tags(text: str) -> str:
    return _ORPHAN_CLOSE.sub("", text) if "</" in text else text


def _max_partial_tag_suffix(buffer: str, tags: tuple[str, ...]) -> int:
    lower = buffer.lower()
    for length in range(min(len(lower), MAX_TAG_LENGTH - 1), 0, -1):
        suffix = lower[-length:]
        if any(len(tag) > length and tag.startswith(suffix) for tag in tags):
            return length
    return 0


class _EmbeddedReasoningStream:
    """Splits `<think>…</think>` (and friends) out of streamed answer text.

    An opening tag only counts at the start of a line, so prose that mentions `<think>` stays
    visible; a complete pair counts anywhere. Partial tags at a chunk boundary are held back.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside: str | None = None
        self._at_line_boundary = True

    def feed(self, text: str) -> tuple[str, str]:
        if not text:
            return "", ""
        buffer = self._buffer + text
        self._buffer = ""
        content = ""
        thinking = ""
        while buffer:
            if self._inside:
                close = f"</{self._inside}>"
                idx = buffer.lower().find(close)
                if idx < 0:
                    held = _max_partial_tag_suffix(buffer, (close,))
                    thinking += buffer[:-held] if held else buffer
                    self._buffer = buffer[-held:] if held else ""
                    return content, thinking
                thinking += buffer[:idx]
                buffer = buffer[idx + len(close):]
                self._inside = None
                continue
            pair = _closed_pair(buffer)
            opening = _boundary_open(buffer, self._at_line_boundary)
            if pair and (not opening or pair[0] <= opening[0]):
                preceding = _strip_orphan_close_tags(buffer[: pair[0]])
                content += preceding
                self._update_boundary(preceding)
                thinking += pair[2]
                buffer = buffer[pair[1]:]
                continue
            if opening:
                preceding = _strip_orphan_close_tags(buffer[: opening[0]])
                content += preceding
                self._update_boundary(preceding)
                self._inside = opening[2]
                buffer = buffer[opening[0] + opening[1]:]
                continue
            held = _max_partial_tag_suffix(buffer, ALL_TAGS)
            visible = _strip_orphan_close_tags(buffer[:-held] if held else buffer)
            content += visible
            self._update_boundary(visible)
            self._buffer = buffer[-held:] if held else ""
            return content, thinking
        return content, thinking

    def flush(self) -> tuple[str, str]:
        tail = "" if self._inside else _strip_orphan_close_tags(self._buffer)
        self._buffer = ""
        self._inside = None
        self._at_line_boundary = True
        return tail, ""

    def _update_boundary(self, text: str) -> None:
        if not text:
            return
        last = text.rfind("\n")
        if last >= 0:
            self._at_line_boundary = not text[last + 1:].strip()
        elif text.strip():
            self._at_line_boundary = False


def _closed_pair(buffer: str) -> tuple[int, int, str] | None:
    lower = buffer.lower()
    best = None
    for name in REASONING_TAG_NAMES:
        open_tag, close_tag = f"<{name}>", f"</{name}>"
        start = lower.find(open_tag)
        if start < 0:
            continue
        close = lower.find(close_tag, start + len(open_tag))
        if close < 0:
            continue
        pair = (start, close + len(close_tag), buffer[start + len(open_tag): close])
        if best is None or pair[0] < best[0]:
            best = pair
    return best


def _boundary_open(buffer: str, at_line_boundary: bool) -> tuple[int, int, str] | None:
    lower = buffer.lower()
    best = None
    for name in REASONING_TAG_NAMES:
        tag = f"<{name}>"
        search = 0
        while search < len(buffer):
            start = lower.find(tag, search)
            if start < 0:
                break
            preceding = buffer[:start]
            last = preceding.rfind("\n")
            boundary = (not preceding[last + 1:].strip()) if last >= 0 else (at_line_boundary and not preceding.strip())
            if boundary:
                if best is None or start < best[0]:
                    best = (start, len(tag), name)
                break
            search = start + 1
    return best
