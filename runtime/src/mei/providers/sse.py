"""Incremental Server-Sent Events decoder for byte chunks.

Handles LF, CRLF, and bare CR line endings, multi-line `data:` fields, comments, and UTF-8 code
points split across chunks (the same cases src/utils/streamParsers.ts covers).
"""

import codecs
from dataclasses import dataclass


@dataclass(frozen=True)
class SseEvent:
    data: str
    event: str = "message"


class SseDecoder:
    def __init__(self) -> None:
        self._utf8 = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buf = ""
        self._pending_cr = False
        self._data: list[str] = []
        self._event = ""

    def feed(self, chunk: bytes) -> list[SseEvent]:
        return self._lines(self._utf8.decode(chunk))

    def close(self) -> list[SseEvent]:
        out = self._lines(self._utf8.decode(b"", final=True))
        if self._buf:
            out += self._line(self._buf)
            self._buf = ""
        out += self._dispatch()
        return out

    def _lines(self, text: str) -> list[SseEvent]:
        out: list[SseEvent] = []
        if not text:
            return out  # the UTF-8 decoder is holding a partial code point
        if self._pending_cr and text.startswith("\n"):
            text = text[1:]  # second half of a CRLF split across chunks
        self._pending_cr = False
        start = 0
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in "\r\n":
                out += self._line(self._buf + text[start:i])
                self._buf = ""
                if ch == "\r":
                    if i + 1 < len(text):
                        if text[i + 1] == "\n":
                            i += 1
                    else:
                        self._pending_cr = True
                start = i + 1
            i += 1
        self._buf += text[start:]
        return out

    def _line(self, line: str) -> list[SseEvent]:
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return []
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "data":
            self._data.append(value)
        elif name == "event":
            self._event = value
        return []

    def _dispatch(self) -> list[SseEvent]:
        if not self._data:
            self._event = ""
            return []
        event = SseEvent(data="\n".join(self._data), event=self._event or "message")
        self._data = []
        self._event = ""
        return [event]
