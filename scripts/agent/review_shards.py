from __future__ import annotations

from dataclasses import dataclass

from .review import ReviewResult
from .weakening import Finding


SHARDS = ("spec-scope", "security", "tests", "maintainability")


@dataclass(frozen=True)
class ShardResult:
    shard: str
    head_sha: str
    result: ReviewResult


def split_files(patches: dict[str, str], max_chars: int = 50000) -> list[dict[str, str]]:
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
    failed = any(f.required and f.severity == "high" for f in findings)
    return ReviewResult("fail" if failed else "pass", tuple(findings))
