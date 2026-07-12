from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class Budget:
    max_seconds: float
    started: float = 0.0

    def __post_init__(self):
        if not self.started:
            self.started = time.monotonic()

    def check(self) -> None:
        if time.monotonic() - self.started > self.max_seconds:
            raise RuntimeError("Autonomous elapsed-time budget exhausted")

    def remaining(self, cap: float) -> float:
        self.check()
        return max(1.0, min(cap, self.max_seconds - (time.monotonic() - self.started)))
