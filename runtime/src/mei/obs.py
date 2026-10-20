"""Logging: JSON lines on stderr (journald under systemd), with secrets redacted centrally."""

import collections
import json
import logging
import re
import sys
import time

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s\"']+"), r"\1[redacted]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"), r"\1[redacted]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+"), r"\1[redacted]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "[redacted]"),
    (re.compile(r"(?i)([?&](?:api_?key|key|token|access_token)=)[^&\s]+"), r"\1[redacted]"),
]


def redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"t": round(time.time(), 3), "level": record.levelname.lower(), "logger": record.name,
                 "msg": redact(record.getMessage())}
        for key in ("task_id", "conversation_id", "turn_id", "client"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


class RecentLogs(logging.Handler):
    """The last N log entries, already redacted, for the popup's log view (GetLogs)."""

    def __init__(self, size: int = 1000) -> None:
        super().__init__()
        self._entries: collections.deque[dict] = collections.deque(maxlen=size)
        self._next = 1

    def emit(self, record: logging.LogRecord) -> None:
        self._entries.append({"id": self._next, "t": round(record.created, 3), "level": record.levelname.lower(),
                              "logger": record.name, "msg": redact(record.getMessage())})
        self._next += 1

    def after(self, last_id: int) -> list[dict]:
        return [e for e in self._entries if e["id"] > last_id]

    def clear(self) -> None:
        self._entries.clear()


RECENT = RecentLogs()


def setup_logging(level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler, RECENT]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
