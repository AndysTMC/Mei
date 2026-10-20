"""Logging: JSON lines on stderr (journald under systemd), with secrets redacted centrally."""

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


def setup_logging(level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
