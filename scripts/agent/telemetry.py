from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Limits:
    elapsed_seconds: float
    codex_calls: int
    review_calls: int
    ci_repairs: int
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class Usage:
    elapsed_seconds: float = 0
    codex_calls: int = 0
    review_calls: int = 0
    ci_repairs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def consume(self, kind: str, amount: int = 1) -> None:
        if not hasattr(self, kind):
            raise ValueError(f"Unknown budget: {kind}")
        setattr(self, kind, getattr(self, kind) + amount)

    def remaining(self, limits: Limits) -> dict:
        values = {}
        for name in ("elapsed_seconds", "codex_calls", "review_calls", "ci_repairs",
                     "input_tokens", "output_tokens"):
            limit = getattr(limits, name)
            values[name] = None if limit is None else max(0, limit - getattr(self, name))
        return values

    def require_available(self, limits: Limits) -> None:
        exhausted = [name for name, value in self.remaining(limits).items()
                     if value is not None and value <= 0]
        if exhausted:
            raise RuntimeError("Budget exhausted: " + ", ".join(exhausted))


def parse_codex_tokens(output: str) -> int | None:
    match = re.search(r"tokens used\s*\n\s*([0-9,]+)", output, re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else None
