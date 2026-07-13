from __future__ import annotations

from dataclasses import dataclass

from .review import ReviewIdentity, ReviewResult
from .events import Event, EventStore
from .weakening import Finding


SHARDS = ("spec-scope", "security", "tests", "maintainability")


@dataclass(frozen=True)
class ShardResult:
    shard: str
    head_sha: str
    result: ReviewResult


def split_files(
    patches: dict[str, str], max_chars: int = 50000
) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    size = 0
    for path, patch in patches.items():
        if len(patch) > max_chars:
            raise ValueError(f"Unsplittable review input: {path}")
        if current and size + len(patch) > max_chars:
            chunks.append(current)
            current, size = {}, 0
        current[path], size = patch, size + len(patch)
    if current:
        chunks.append(current)
    return chunks


def aggregate(results: list[ShardResult], head_sha: str) -> ReviewResult:
    seen = set()
    findings: list[Finding] = []
    required = set(SHARDS) | {"integration"}
    for value in results:
        if value.head_sha != head_sha:
            raise ValueError("Review shard SHA mismatch")
        if value.shard in seen:
            raise ValueError("Duplicate review shard")
        seen.add(value.shard)
        findings.extend(value.result.findings)
    missing = required - seen
    if missing:
        raise ValueError("Missing review shards: " + ", ".join(sorted(missing)))
    failed = any(f.required for f in findings)
    return ReviewResult("fail" if failed else "pass", tuple(findings))


def reusable_event(events: list[Event], identity_digest: str) -> Event | None:
    """Return only an exact-identity successful shard event."""
    for event in reversed(events):
        data = event.data or {}
        if (
            event.kind == "review-shard"
            and event.result == "PASS"
            and data.get("identity_digest") == identity_digest
        ):
            return event
    return None


def record_reuse_decision(
    store: EventStore,
    *,
    source: Event,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    shard: str,
    identity_digest: str,
) -> Event:
    """Append the auditable decision that reuses an exact-identity PASS."""
    return store.append(
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        phase="review",
        kind="review-reused",
        result="PASS",
        head_sha=head_sha,
        data={
            "shard": shard,
            "identity_digest": identity_digest,
            "source_sequence": source.sequence,
        },
    )


def result_from_event(event: Event) -> ReviewResult:
    data = event.data or {}
    findings = tuple(Finding(**value) for value in data.get("findings", []))
    return ReviewResult("pass" if event.result == "PASS" else "fail", findings)


def matching_failure_count(
    events: list[Event], identity: ReviewIdentity, signature: str
) -> int:
    return sum(
        1
        for event in events
        if event.kind == "review-shard"
        and event.result != "PASS"
        and (event.data or {}).get("identity_digest") == identity.digest
        and (event.data or {}).get("failure_signature") == signature
    )
