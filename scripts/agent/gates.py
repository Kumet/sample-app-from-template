from __future__ import annotations

from dataclasses import dataclass

from .events import Event

REQUIRED_GATES = ("validation", "weakening", "review", "ci")
REQUIRED_REVIEW_SHARDS = (
    "spec-scope",
    "security",
    "tests",
    "maintainability",
    "integration",
)


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
    missing = tuple(
        gate
        for gate in REQUIRED_GATES
        if gate not in latest or latest[gate].result != "PASS"
    )
    mismatched = tuple(
        gate
        for gate, event in latest.items()
        if gate in REQUIRED_GATES and event.head_sha != pr_head_sha
    )
    return GateReport(pr_head_sha, not missing and not mismatched, missing, mismatched)


def require_mergeable(events: list[Event], pr_head_sha: str) -> None:
    report = evaluate_gates(events, pr_head_sha)
    if not report.passed:
        raise ValueError(
            f"HEAD is not fully gated; missing={report.missing}, "
            f"mismatched={report.mismatched}"
        )


def require_exact_validation(events: list[Event], head_sha: str) -> Event:
    for event in reversed(events):
        if (
            event.kind == "validation"
            and event.result == "PASS"
            and event.head_sha == head_sha
        ):
            return event
    raise ValueError(f"No validation PASS event for current HEAD {head_sha}")


def require_pre_push(events: list[Event], head_sha: str) -> None:
    require_exact_validation(events, head_sha)
    weakening = next(
        (
            event
            for event in reversed(events)
            if event.kind == "weakening" and event.head_sha == head_sha
        ),
        None,
    )
    if weakening is None or weakening.result != "PASS":
        raise ValueError("No weakening PASS event for current HEAD")
    passed = {
        (event.data or {}).get("shard")
        for event in events
        if event.kind == "review-shard"
        and event.result == "PASS"
        and event.head_sha == head_sha
    }
    missing = set(REQUIRED_REVIEW_SHARDS) - passed
    if missing:
        raise ValueError(
            "Missing exact-HEAD review shards: " + ", ".join(sorted(missing))
        )
