from __future__ import annotations

from dataclasses import dataclass

from .events import Event


REQUIRED_GATES = ("validation", "weakening", "review", "ci")


@dataclass(frozen=True)
class GateReport:
    head_sha: str
    passed: bool
    missing: tuple[str, ...]
    mismatched: tuple[str, ...]


def evaluate_gates(events: list[Event], pr_head_sha: str) -> GateReport:
    latest: dict[str, Event] = {}
    for event in events:
        if event.kind in REQUIRED_GATES:
            latest[event.kind] = event
    missing = tuple(gate for gate in REQUIRED_GATES if gate not in latest or latest[gate].result != "PASS")
    mismatched = tuple(gate for gate, event in latest.items()
                       if gate in REQUIRED_GATES and event.head_sha != pr_head_sha)
    return GateReport(pr_head_sha, not missing and not mismatched, missing, mismatched)


def require_mergeable(events: list[Event], pr_head_sha: str) -> None:
    report = evaluate_gates(events, pr_head_sha)
    if not report.passed:
        raise ValueError(f"HEAD is not fully gated; missing={report.missing}, mismatched={report.mismatched}")
