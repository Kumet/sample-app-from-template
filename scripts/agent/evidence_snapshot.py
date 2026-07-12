from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .events import Event, EventStore
from .validation import CommandResult

EVENT_SCHEMA_VERSION = 1
SNAPSHOT_FORMAT_VERSION = 2
LOG_PATH = "validation-log.md"


@dataclass(frozen=True)
class EvidenceBinding:
    head_sha: str
    log_path: str
    log_blob_sha: str
    validation_contract_digest: str
    snapshot_event_sequence: int
    included_event_sequence: int
    final_validation_event_sequence: int
    validation_result_digest: str

    def identity_fields(self) -> dict:
        return {
            "tracked_snapshot_event_sequence": self.snapshot_event_sequence,
            "validation_log_blob_sha": self.log_blob_sha,
            "validation_contract_digest": self.validation_contract_digest,
            "final_validation_event_sequence": self.final_validation_event_sequence,
            "final_validation_result_digest": self.validation_result_digest,
        }


def contract_digest(feature_dir: Path) -> str:
    return hashlib.sha256((feature_dir / "validation.toml").read_bytes()).hexdigest()


def result_digest(result: CommandResult) -> str:
    payload = {
        "name": result.name,
        "command": list(result.command),
        "returncode": result.returncode,
        "stdout_digest": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_digest": hashlib.sha256(result.stderr.encode()).hexdigest(),
    }
    return _digest(payload)


def git_blob_sha(repo: Path, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"HEAD:{relative_path}"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError(f"Tracked evidence blob is unavailable: {relative_path}")
    return result.stdout.strip()


def record_snapshot(
    store: EventStore,
    *,
    repo: Path,
    feature_dir: Path,
    repository: str,
    branch: str,
    worktree: str,
) -> Event:
    metadata = snapshot_metadata(feature_dir / "validation-log.md")
    head = _head(repo)
    digest = contract_digest(feature_dir)
    if metadata["validation_contract_digest"] != digest:
        raise ValueError("Tracked validation-log contract digest mismatch")
    return store.append(
        feature=feature_dir.name,
        repository=repository,
        branch=branch,
        worktree=worktree,
        phase="evidence",
        kind="tracked-evidence-snapshot",
        result="PASS",
        head_sha=head,
        data={
            "log_path": str(feature_dir.relative_to(repo) / "validation-log.md"),
            "log_blob_sha": git_blob_sha(
                repo, str(feature_dir.relative_to(repo) / "validation-log.md")
            ),
            "included_event_sequence": metadata["included_event_sequence"],
            "validation_contract_digest": digest,
            "snapshot_format_version": SNAPSHOT_FORMAT_VERSION,
        },
    )


def record_final_validation(
    store: EventStore,
    *,
    repo: Path,
    feature_dir: Path,
    repository: str,
    branch: str,
    worktree: str,
    snapshot: Event,
    result: CommandResult,
    started_at: str,
    completed_at: str,
) -> Event:
    data = snapshot.data or {}
    current_head = _head(repo)
    if snapshot.head_sha != current_head:
        raise ValueError("Evidence snapshot HEAD does not match final-validation HEAD")
    return store.append(
        feature=feature_dir.name,
        repository=repository,
        branch=branch,
        worktree=worktree,
        phase="post-evidence",
        kind="final-validation",
        result="PASS" if result.succeeded else "FAIL",
        head_sha=current_head,
        data={
            "evidence_snapshot_event_sequence": snapshot.sequence,
            "log_blob_sha": data.get("log_blob_sha"),
            "validation_contract_digest": data.get("validation_contract_digest"),
            "command_identity": _digest({"command": list(result.command)}),
            "started_at": started_at,
            "completed_at": completed_at,
            "result_digest": result_digest(result),
        },
    )


def require_final_evidence(
    repo: Path, feature_dir: Path, events: list[Event], head_sha: str
) -> EvidenceBinding:
    if _head(repo) != head_sha:
        raise ValueError("Current HEAD differs from requested review HEAD")
    if _changed(repo):
        raise ValueError("Review requires a clean worktree")
    snapshot = next(
        (
            event
            for event in reversed(events)
            if event.kind == "tracked-evidence-snapshot"
            and event.result == "PASS"
            and event.head_sha == head_sha
        ),
        None,
    )
    if snapshot is None:
        raise ValueError("Missing tracked-evidence-snapshot for current HEAD")
    snapshot_data = snapshot.data or {}
    log_path = snapshot_data.get("log_path")
    if not isinstance(log_path, str):
        raise ValueError("Snapshot log path is invalid")
    blob = git_blob_sha(repo, log_path)
    digest = contract_digest(feature_dir)
    if snapshot_data.get("log_blob_sha") != blob:
        raise ValueError("Validation-log blob SHA mismatch")
    if snapshot_data.get("validation_contract_digest") != digest:
        raise ValueError("Validation contract digest mismatch")
    final = next(
        (
            event
            for event in reversed(events)
            if event.kind == "final-validation"
            and event.phase == "post-evidence"
            and event.result == "PASS"
            and event.head_sha == head_sha
        ),
        None,
    )
    if final is None:
        raise ValueError("Missing post-evidence final-validation PASS")
    final_data = final.data or {}
    if final_data.get("evidence_snapshot_event_sequence") != snapshot.sequence:
        raise ValueError("Final-validation snapshot reference mismatch")
    if final_data.get("log_blob_sha") != blob:
        raise ValueError("Final-validation log blob mismatch")
    if final_data.get("validation_contract_digest") != digest:
        raise ValueError("Final-validation contract digest mismatch")
    result_value = final_data.get("result_digest")
    if not isinstance(result_value, str) or len(result_value) != 64:
        raise ValueError("Final-validation result digest is invalid")
    return EvidenceBinding(
        head_sha,
        log_path,
        blob,
        digest,
        snapshot.sequence,
        int(snapshot_data.get("included_event_sequence", 0)),
        final.sequence,
        result_value,
    )


def snapshot_metadata(path: Path) -> dict:
    first = path.read_text(encoding="utf-8").splitlines()[1]
    prefix = "<!-- validation-snapshot:"
    if not first.startswith(prefix) or not first.endswith(" -->"):
        raise ValueError("Validation log snapshot metadata is missing")
    value = json.loads(first[len(prefix) : -4].strip())
    required = {
        "feature",
        "event_schema_version",
        "snapshot_format_version",
        "included_event_sequence",
        "generated_at",
        "validation_contract_digest",
    }
    if (
        set(value) != required
        or value["snapshot_format_version"] != SNAPSHOT_FORMAT_VERSION
    ):
        raise ValueError("Validation log snapshot metadata is invalid")
    return value


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def _head(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("Cannot resolve current HEAD")
    return result.stdout.strip()


def _changed(repo: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    return bool(result.stdout.strip())


def _digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
