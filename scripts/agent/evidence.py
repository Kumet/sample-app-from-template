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


def safe_error_detail(error: BaseException, limit: int = 4000) -> str:
    raw = f"{type(error).__name__}: {error}"
    safe_controls = "".join(
        character if character in "\n\t" or ord(character) >= 32 else "?"
        for character in raw
    )
    compact = " ".join(safe_controls.split())
    return redact(compact, limit)


def redact_value(value, limit: int = 4000):
    if isinstance(value, str):
        return redact(" ".join(value.split()), limit)
    if isinstance(value, dict):
        return {str(key): redact_value(item, limit) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(item, limit) for item in value]
    return value
