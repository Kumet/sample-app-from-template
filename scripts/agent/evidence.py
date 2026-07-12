from __future__ import annotations

import re


PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s]+"),
    re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b"),
)


def redact(text: str, limit: int = 12000) -> str:
    value = text[-limit:]
    for pattern in PATTERNS:
        if pattern.groups:
            value = pattern.sub(r"\1[REDACTED]", value)
        else:
            value = pattern.sub("[REDACTED]", value)
    return value
