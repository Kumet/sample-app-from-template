from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import evidence_snapshot
from .events import Event
from . import review

REQUIRED_GATES = ("final-validation-accepted", "weakening", "review", "ci")
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
            event.phase == "post-evidence"
            and event.kind == "final-validation-accepted"
            and event.result == "PASS"
            and event.head_sha == head_sha
        ):
            return event
    raise ValueError(f"No final-validation-accepted PASS for current HEAD {head_sha}")


def require_pre_push(
    repo: Path, feature_dir: Path, events: list[Event], head_sha: str
) -> None:
    evidence_snapshot.require_final_evidence(repo, feature_dir, events, head_sha)
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
    aggregates = {}
    latest_review_event = {}
    for event in events:
        data = event.data or {}
        shard = data.get("shard")
        if (
            event.kind == "review-shard"
            and event.head_sha == head_sha
            and shard in REQUIRED_REVIEW_SHARDS
        ):
            latest_review_event[shard] = event
        if (
            event.kind == "review-shard"
            and event.head_sha == head_sha
            and data.get("aggregate") is True
        ):
            aggregates[shard] = event
    passed = set()
    for shard, aggregate in aggregates.items():
        identities = (aggregate.data or {}).get("chunk_identities") or []
        if (
            aggregate.result == "PASS"
            and latest_review_event.get(shard) is aggregate
            and identities
            and _valid_aggregate_gate(events, aggregate, head_sha)
        ):
            passed.add(shard)
    missing = set(REQUIRED_REVIEW_SHARDS) - passed
    if missing:
        raise ValueError(
            "Missing exact-HEAD review shards: " + ", ".join(sorted(missing))
        )
    integration = aggregates["integration"]
    latest_file_sequence = max(
        aggregate.sequence
        for shard, aggregate in aggregates.items()
        if shard != "integration"
    )
    if integration.sequence <= latest_file_sequence:
        raise ValueError(
            "Integration review predates the latest required file-shard review"
        )


def _valid_aggregate_gate(
    events: list[Event], aggregate: Event, head_sha: str
) -> bool:
    if aggregate.head_sha != head_sha:
        return False
    data = aggregate.data or {}
    identities = data.get("chunk_identities")
    if (
        not isinstance(identities, list)
        or not identities
        or not all(isinstance(value, str) and value for value in identities)
        or len(set(identities)) != len(identities)
    ):
        return False
    canonical_fields = {
        "gate_verdict",
        "schema_valid",
        "chunk_event_sequences",
        "findings",
        "required_findings",
        "non_required_findings",
        "aggregate_digest",
    }
    present = canonical_fields.intersection(data)
    if not present:
        # Preserve compatibility with old identity-bound PASS aggregates.
        return all(
            _valid_identity_gate(events, aggregate, head_sha, digest)
            for digest in identities
        )
    if present != canonical_fields:
        return False
    sequences = data.get("chunk_event_sequences")
    if (
        data.get("schema_valid") is not True
        or data.get("gate_verdict") != "PASS"
        or not isinstance(sequences, list)
        or len(sequences) != len(identities)
        or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in sequences
        )
        or len(set(sequences)) != len(sequences)
    ):
        return False
    results = []
    for digest, sequence in zip(identities, sequences, strict=True):
        value = _valid_identity_gate(
            events, aggregate, head_sha, digest, sequence=sequence
        )
        if value is None:
            return False
        results.append(value)
    try:
        aggregate_result, expected = review.aggregate_evidence_fields(
            tuple(results), tuple(identities), tuple(sequences)
        )
    except (TypeError, ValueError):
        return False
    if aggregate_result.result.upper() != aggregate.result:
        return False
    return all(data.get(key) == value for key, value in expected.items())


def _valid_identity_gate(
    events: list[Event],
    aggregate: Event,
    head_sha: str,
    digest: str,
    *,
    sequence: int | None = None,
):
    candidates = (
        [event for event in events if event.sequence == sequence]
        if sequence is not None
        else list(reversed(events[: aggregate.sequence - 1]))
    )
    for event in candidates:
        data = event.data or {}
        if (
            event.kind != "review-shard"
            or data.get("aggregate") is True
            or event.sequence >= aggregate.sequence
            or event.head_sha != head_sha
            or event.feature != aggregate.feature
            or event.repository != aggregate.repository
            or event.branch != aggregate.branch
            or event.worktree != aggregate.worktree
            or data.get("shard") != (aggregate.data or {}).get("shard")
            or data.get("identity_digest") != digest
        ):
            continue
        try:
            result = review.result_from_chunk_event(event, digest)
        except (TypeError, ValueError):
            continue
        if result.gate_passed:
            return result
    return None
