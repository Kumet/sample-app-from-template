from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from . import evidence_snapshot
from .evidence import redact, redact_value
from .weakening import Finding

MAX_REVIEW_INPUT_CHARS = 100_000
REVIEW_TIMEOUT_SECONDS = 600
REVIEW_SCHEMA_VERSION = "1"
REVIEW_PROMPT_VERSION = "4"
REVIEW_MODEL = "gpt-5.4-mini"
REVIEW_IDENTITY_SCHEMA_VERSION = "4"
REVIEW_IDENTITY_FIELDS = (
    "identity_schema_version",
    "feature",
    "head_sha",
    "shard",
    "review_schema_version",
    "prompt_version",
    "reviewer_model",
    "reviewer_command_identity",
    "review_settings",
    "reviewed_files",
    "spec_digest",
    "plan_digest",
    "tasks_digest",
    "validation_contract_digest",
    "diff_input_digest",
    "runtime_evidence_digest",
    "tracked_snapshot_event_sequence",
    "validation_log_blob_sha",
    "final_validation_attempt_event_sequence",
    "final_validation_accepted_event_sequence",
    "final_validation_result_digest",
)
MODEL_SETTINGS = (
    f"model={REVIEW_MODEL}",
    "approval_policy=never",
    "model_reasoning_effort=low",
    "sandbox=read-only",
)


@dataclass(frozen=True)
class ReviewResult:
    result: str
    findings: tuple[Finding, ...]

    @property
    def required_findings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.required)

    def signature(self) -> str:
        return json.dumps([f.__dict__ for f in self.required_findings], sort_keys=True)


@dataclass(frozen=True)
class ReviewIdentity:
    identity_schema_version: str
    feature: str
    head_sha: str
    shard: str
    review_schema_version: str
    prompt_version: str
    reviewer_model: str
    reviewer_command_identity: str
    review_settings: tuple[str, ...]
    reviewed_files: tuple[str, ...]
    spec_digest: str
    plan_digest: str
    tasks_digest: str
    validation_contract_digest: str
    diff_input_digest: str
    runtime_evidence_digest: str
    tracked_snapshot_event_sequence: int
    validation_log_blob_sha: str
    final_validation_attempt_event_sequence: int
    final_validation_accepted_event_sequence: int
    final_validation_result_digest: str

    def __post_init__(self):
        if self.identity_schema_version != REVIEW_IDENTITY_SCHEMA_VERSION:
            raise ValueError("Unknown review identity schema version")
        object.__setattr__(self, "reviewed_files", tuple(sorted(self.reviewed_files)))
        if not all(
            isinstance(value, str) and value
            for key, value in self.payload().items()
            if key
            not in {
                "review_settings",
                "reviewed_files",
                "tracked_snapshot_event_sequence",
                "final_validation_attempt_event_sequence",
                "final_validation_accepted_event_sequence",
            }
        ):
            raise ValueError("Review identity text fields must be non-empty strings")
        if not all(isinstance(value, str) for value in self.review_settings):
            raise ValueError("Review settings must be strings")
        if not all(isinstance(value, str) for value in self.reviewed_files):
            raise ValueError("Reviewed files must be strings")
        if (
            self.tracked_snapshot_event_sequence < 1
            or self.final_validation_attempt_event_sequence < 1
            or self.final_validation_accepted_event_sequence < 1
        ):
            raise ValueError("Review evidence sequences must be positive integers")

    def payload(self) -> dict:
        return {
            "identity_schema_version": self.identity_schema_version,
            "feature": self.feature,
            "head_sha": self.head_sha,
            "shard": self.shard,
            "review_schema_version": self.review_schema_version,
            "prompt_version": self.prompt_version,
            "reviewer_model": self.reviewer_model,
            "reviewer_command_identity": self.reviewer_command_identity,
            "review_settings": list(self.review_settings),
            "reviewed_files": list(self.reviewed_files),
            "spec_digest": self.spec_digest,
            "plan_digest": self.plan_digest,
            "tasks_digest": self.tasks_digest,
            "validation_contract_digest": self.validation_contract_digest,
            "diff_input_digest": self.diff_input_digest,
            "runtime_evidence_digest": self.runtime_evidence_digest,
            "tracked_snapshot_event_sequence": self.tracked_snapshot_event_sequence,
            "validation_log_blob_sha": self.validation_log_blob_sha,
            "final_validation_attempt_event_sequence": (
                self.final_validation_attempt_event_sequence
            ),
            "final_validation_accepted_event_sequence": (
                self.final_validation_accepted_event_sequence
            ),
            "final_validation_result_digest": self.final_validation_result_digest,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> ReviewIdentity:
        if set(payload) != set(REVIEW_IDENTITY_FIELDS):
            raise ValueError("Review identity fields are incomplete or unknown")
        values = dict(payload)
        if not isinstance(values["review_settings"], (list, tuple)) or not isinstance(
            values["reviewed_files"], (list, tuple)
        ):
            raise ValueError("Review identity list fields have invalid types")
        values["review_settings"] = tuple(values["review_settings"])
        values["reviewed_files"] = tuple(values["reviewed_files"])
        return cls(**values)

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True)
class PreparedReview:
    identity: ReviewIdentity
    prompt: str
    command: tuple[str, ...]


class ReviewTimeout(RuntimeError):
    def __init__(self, diagnostic: dict):
        self.diagnostic = diagnostic
        super().__init__(
            f"Independent review shard {diagnostic['shard']} timed out after "
            f"{diagnostic['configured_timeout']} seconds"
        )


def parse_review(text: str) -> ReviewResult:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid review JSON: {error}") from error
    if not isinstance(raw, dict) or raw.get("result") not in {"pass", "fail"}:
        raise ValueError("Review result must be pass or fail")
    values = raw.get("findings")
    if not isinstance(values, list):
        raise ValueError("Review findings must be an array")
    findings = []
    required_keys = {"severity", "category", "file", "description", "required"}
    for value in values:
        if not isinstance(value, dict) or set(value) != required_keys:
            raise ValueError("Review finding has invalid fields")
        if value["severity"] not in {"low", "medium", "high"}:
            raise ValueError("Review finding has invalid severity")
        if not all(
            isinstance(value[k], str) for k in ("category", "file", "description")
        ):
            raise ValueError("Review finding text fields are invalid")
        if not isinstance(value["required"], bool):
            raise ValueError("Review required field must be boolean")
        findings.append(Finding(**value))
    result = ReviewResult(raw["result"], tuple(findings))
    if result.result == "pass" and result.required_findings:
        raise ValueError("Passing review cannot contain required high findings")
    return result


def prepare_review(
    repo: Path,
    feature_dir: Path,
    review_focus: str = "complete",
    review_paths: tuple[str, ...] | None = None,
    runtime_evidence_text: str = "[]",
    evidence_fields: dict | None = None,
) -> PreparedReview:
    if evidence_fields is None:
        raise ValueError("Review requires validated evidence identity fields")
    template = (repo / "prompts" / "review-feature.md").read_text(encoding="utf-8")
    base = subprocess.run(
        ["git", "merge-base", "main", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if base.returncode:
        raise RuntimeError(f"Cannot determine review base: {base.stderr[-1000:]}")
    feature_path = str(feature_dir.relative_to(repo))
    pathspec = (
        list(review_paths)
        if review_paths is not None
        else [".", f":(exclude){feature_path}/**"]
    )
    if review_paths == ():
        patch_text = ""
    else:
        patch = subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                base.stdout.strip(),
                "HEAD",
                "--",
                *pathspec,
            ],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if patch.returncode:
            raise RuntimeError(f"Cannot create review diff: {patch.stderr[-1000:]}")
        patch_text = patch.stdout
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if head.returncode:
        raise RuntimeError(f"Cannot determine review HEAD: {head.stderr[-1000:]}")
    changed = subprocess.run(
        ["git", "diff", "--name-only", base.stdout.strip(), "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if changed.returncode:
        raise RuntimeError(f"Cannot determine reviewed files: {changed.stderr[-1000:]}")
    inputs = {
        "spec_text": (feature_dir / "spec.md").read_text(encoding="utf-8"),
        "plan_text": (feature_dir / "plan.md").read_text(encoding="utf-8"),
        "tasks_text": (feature_dir / "tasks.md").read_text(encoding="utf-8"),
        "validation_text": (feature_dir / "validation-log.md").read_text(
            encoding="utf-8"
        ),
        "validation_contract_text": (feature_dir / "validation.toml").read_text(
            encoding="utf-8"
        ),
        "runtime_evidence_text": runtime_evidence_text,
        "diff_text": patch_text,
    }
    inputs["evidence_semantics_text"] = render_evidence_semantics(
        inputs["validation_text"],
        inputs["validation_contract_text"],
        runtime_evidence_text,
        evidence_fields,
        head.stdout.strip(),
    )
    input_size = sum(len(value) for value in inputs.values())
    if input_size > MAX_REVIEW_INPUT_CHARS:
        raise RuntimeError(
            f"Independent review input exceeds {MAX_REVIEW_INPUT_CHARS} characters; "
            "refusing to review truncated content"
        )
    prompt = template.format(
        spec_path=feature_dir.relative_to(repo) / "spec.md",
        plan_path=feature_dir.relative_to(repo) / "plan.md",
        tasks_path=feature_dir.relative_to(repo) / "tasks.md",
        review_focus=review_focus,
        review_guidance=_review_guidance(review_focus),
        **inputs,
    )
    command = (
        "codex",
        "exec",
        "--model",
        REVIEW_MODEL,
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "-c",
        'model_reasoning_effort="low"',
        "--ephemeral",
        "--cd",
        str(repo),
        "--output-schema",
        str(repo / "schemas" / "review-result.schema.json"),
        "-",
    )
    changed_files = (
        review_paths if review_paths is not None else tuple(changed.stdout.splitlines())
    )
    reviewed_files = tuple(
        sorted(
            set(changed_files)
            | {
                str(feature_dir.relative_to(repo) / name)
                for name in (
                    "spec.md",
                    "plan.md",
                    "tasks.md",
                    "validation.toml",
                    "validation-log.md",
                )
            }
            | {"prompts/review-feature.md", "schemas/review-result.schema.json"}
        )
    )
    identity = ReviewIdentity(
        REVIEW_IDENTITY_SCHEMA_VERSION,
        feature_dir.name,
        head.stdout.strip(),
        review_focus,
        REVIEW_SCHEMA_VERSION,
        REVIEW_PROMPT_VERSION,
        REVIEW_MODEL,
        _digest({"command": list(command)}),
        MODEL_SETTINGS,
        reviewed_files,
        hashlib.sha256(inputs["spec_text"].encode()).hexdigest(),
        hashlib.sha256(inputs["plan_text"].encode()).hexdigest(),
        hashlib.sha256(inputs["tasks_text"].encode()).hexdigest(),
        hashlib.sha256(inputs["validation_contract_text"].encode()).hexdigest(),
        hashlib.sha256(
            prompt.encode("utf-8")
            + (repo / "schemas" / "review-result.schema.json").read_bytes()
        ).hexdigest(),
        hashlib.sha256(runtime_evidence_text.encode("utf-8")).hexdigest(),
        int(evidence_fields["tracked_snapshot_event_sequence"]),
        str(evidence_fields["validation_log_blob_sha"]),
        int(evidence_fields["final_validation_attempt_event_sequence"]),
        int(evidence_fields["final_validation_accepted_event_sequence"]),
        str(evidence_fields["final_validation_result_digest"]),
    )
    return PreparedReview(identity, prompt, command)


def render_evidence_semantics(
    validation_text: str,
    validation_contract_text: str,
    runtime_evidence_text: str,
    evidence_fields: dict,
    head_sha: str,
) -> str:
    """Render the mechanically checked tracked/runtime evidence interpretation."""
    rules = {
        "tracked_log_role": "pre-final snapshot through included_event_sequence",
        "post_evidence_storage": "append-only runtime evidence outside tracked log",
        "post_watermark_absence_from_log_is_stale": False,
        "gate_authority": "final-validation-accepted/PASS only",
        "stale_finding_requires_actual_mismatch": [
            "included_event_sequence",
            "validation_log_blob_sha",
            "validation_contract_digest",
            "exact_head_sha",
            "snapshot_event_sequence",
            "attempt_event_sequence",
            "result_digest",
        ],
    }
    try:
        events = json.loads(runtime_evidence_text)
    except json.JSONDecodeError as error:
        raise ValueError("Runtime review evidence is invalid JSON") from error
    if not isinstance(events, list) or not all(
        isinstance(item, dict) for item in events
    ):
        raise ValueError("Runtime review evidence must be an event array")
    lifecycle_kinds = {
        "tracked-evidence-snapshot",
        "final-validation-attempt",
        "final-validation-accepted",
    }
    if not any(item.get("kind") in lifecycle_kinds for item in events):
        raise ValueError("Runtime review evidence lifecycle is incomplete")
    sequences = [item.get("sequence") for item in events]
    if not all(
        isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1
        for sequence in sequences
    ):
        raise ValueError("Runtime review evidence sequence is invalid")
    if len(set(sequences)) != len(sequences):
        raise ValueError("Runtime review evidence sequence is duplicated")
    snapshot_sequence = int(evidence_fields["tracked_snapshot_event_sequence"])
    attempt_sequence = int(evidence_fields["final_validation_attempt_event_sequence"])
    accepted_sequence = int(evidence_fields["final_validation_accepted_event_sequence"])
    by_sequence = {item.get("sequence"): item for item in events}
    try:
        snapshot = by_sequence[snapshot_sequence]
        attempt = by_sequence[attempt_sequence]
        accepted = by_sequence[accepted_sequence]
    except KeyError as error:
        raise ValueError("Runtime review evidence lifecycle is incomplete") from error
    metadata = evidence_snapshot.snapshot_metadata_text(validation_text)
    snapshot_data = snapshot.get("data") or {}
    attempt_data = attempt.get("data") or {}
    accepted_data = accepted.get("data") or {}
    log_blob = str(evidence_fields["validation_log_blob_sha"])
    result_digest = str(evidence_fields["final_validation_result_digest"])
    contract_digest = hashlib.sha256(validation_contract_text.encode()).hexdigest()

    checks = (
        (snapshot.get("kind"), "tracked-evidence-snapshot", "snapshot kind"),
        (attempt.get("kind"), "final-validation-attempt", "attempt kind"),
        (accepted.get("kind"), "final-validation-accepted", "accepted kind"),
        (snapshot.get("sequence"), snapshot_sequence, "snapshot sequence"),
        (attempt.get("sequence"), attempt_sequence, "attempt sequence"),
        (accepted.get("sequence"), accepted_sequence, "accepted sequence"),
        (snapshot.get("result"), "PASS", "snapshot result"),
        (attempt.get("result"), "PASS", "attempt result"),
        (accepted.get("result"), "PASS", "accepted result"),
        (snapshot.get("head_sha"), head_sha, "snapshot HEAD"),
        (attempt.get("head_sha"), head_sha, "attempt HEAD"),
        (accepted.get("head_sha"), head_sha, "accepted HEAD"),
        (
            snapshot_data.get("included_event_sequence"),
            metadata.get("included_event_sequence"),
            "snapshot watermark",
        ),
        (snapshot_data.get("log_blob_sha"), log_blob, "snapshot log blob"),
        (
            snapshot_data.get("validation_contract_digest"),
            contract_digest,
            "snapshot contract digest",
        ),
        (
            metadata.get("validation_contract_digest"),
            contract_digest,
            "validation-log contract digest",
        ),
        (
            attempt_data.get("snapshot_event_sequence"),
            snapshot_sequence,
            "attempt snapshot reference",
        ),
        (attempt_data.get("exact_head_sha"), head_sha, "attempt exact HEAD"),
        (attempt_data.get("validation_log_blob_sha"), log_blob, "attempt log blob"),
        (
            attempt_data.get("validation_contract_digest"),
            contract_digest,
            "attempt contract digest",
        ),
        (attempt_data.get("result_digest"), result_digest, "attempt result digest"),
        (
            accepted_data.get("snapshot_event_sequence"),
            snapshot_sequence,
            "accepted snapshot reference",
        ),
        (
            accepted_data.get("attempt_event_sequence"),
            attempt_sequence,
            "accepted attempt reference",
        ),
        (accepted_data.get("exact_head_sha"), head_sha, "accepted exact HEAD"),
        (accepted_data.get("validation_log_blob_sha"), log_blob, "accepted log blob"),
        (
            accepted_data.get("validation_contract_digest"),
            contract_digest,
            "accepted contract digest",
        ),
        (accepted_data.get("result_digest"), result_digest, "accepted result digest"),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise ValueError(f"Review evidence {label} mismatch")
    return json.dumps(
        {
            "model": "tracked-pre-final-plus-runtime-v1",
            "status": "mechanically-verified",
            "validation_log_watermark": metadata["included_event_sequence"],
            "tracked_snapshot_event_sequence": snapshot_sequence,
            "final_validation_attempt_event_sequence": attempt_sequence,
            "final_validation_accepted_event_sequence": accepted_sequence,
            "validation_log_blob_sha": log_blob,
            "exact_head_sha": head_sha,
            "validation_result_digest": result_digest,
            **rules,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _review_guidance(focus: str) -> str:
    name = focus.split(" ", 1)[0]
    guidance = {
        "spec-scope": (
            "Check only specification compliance, approved scope, traceability, "
            "and whether the supplied evidence is attributable to this HEAD. "
            "Low-confidence test-weakening review candidates belong only to the "
            "tests shard and are not findings for this shard. "
            "This read-only shard intentionally receives the complete approved "
            "feature diff; overlap with focused shards is not an execution or "
            "data-authorization boundary."
        ),
        "security": (
            "Check only security, privacy, secret exposure, process isolation, "
            "redaction, and fail-closed approval behavior. Do not report a "
            "low-confidence test-weakening review candidate solely because it "
            "appears in runtime evidence."
        ),
        "tests": (
            "Check only test strength, missing required cases, test weakening, "
            "and whether assertions prove the stated behavior. Weakening review "
            "candidates are hypotheses: corroborate them against the current diff "
            "and report only a concrete loss of verification strength."
        ),
        "maintainability": (
            "Check only maintainability, bounded complexity, diagnostics, "
            "documentation, and operational recovery behavior. Low-confidence "
            "test-weakening review candidates belong only to the tests shard."
        ),
        "integration": (
            "Check only cross-file integration, ordering, identity/SHA consistency, "
            "and end-to-end gate composition. You may verify weakening evidence "
            "composition and attribution, but a review candidate alone is not an "
            "established weakening finding."
        ),
    }
    return guidance.get(name, "Check only the named review focus.")


def prepare_reviews(
    repo: Path,
    feature_dir: Path,
    review_focus: str = "complete",
    runtime_evidence_text: str = "[]",
    evidence_fields: dict | None = None,
) -> tuple[PreparedReview, ...]:
    fixed_input_chars = sum(
        len((feature_dir / name).read_text(encoding="utf-8"))
        for name in (
            "spec.md",
            "plan.md",
            "tasks.md",
            "validation.toml",
            "validation-log.md",
        )
    )
    fixed_input_chars += len(runtime_evidence_text)
    fixed_input_chars += len(
        (repo / "prompts" / "review-feature.md").read_text(encoding="utf-8")
    )
    fixed_input_chars += (repo / "schemas" / "review-result.schema.json").stat().st_size
    max_patch_chars = MAX_REVIEW_INPUT_CHARS - fixed_input_chars - 8_000
    if max_patch_chars < 10_000:
        raise RuntimeError("Fixed independent review input exceeds size policy")
    base = subprocess.run(
        ["git", "merge-base", "main", "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if base.returncode:
        raise RuntimeError(f"Cannot determine review base: {base.stderr[-1000:]}")
    changed = subprocess.run(
        ["git", "diff", "--name-only", base.stdout.strip(), "HEAD"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    feature_prefix = str(feature_dir.relative_to(repo)) + "/"
    paths = [
        path
        for path in changed.stdout.splitlines()
        if not path.startswith(feature_prefix)
    ]
    paths = _paths_for_focus(paths, review_focus)
    chunks: list[tuple[str, ...]] = []
    current: list[str] = []
    size = 0
    for path in paths:
        item = subprocess.run(
            ["git", "diff", "--no-ext-diff", base.stdout.strip(), "HEAD", "--", path],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if item.returncode:
            raise RuntimeError(
                f"Cannot create review diff for {path}: {item.stderr[-1000:]}"
            )
        if len(item.stdout) > max_patch_chars:
            raise RuntimeError(f"Unsplittable review input exceeds policy: {path}")
        if current and size + len(item.stdout) > max_patch_chars:
            chunks.append(tuple(current))
            current, size = [], 0
        current.append(path)
        size += len(item.stdout)
    if current or not chunks:
        chunks.append(tuple(current))
    total = len(chunks)
    return tuple(
        prepare_review(
            repo,
            feature_dir,
            f"{review_focus} [{index}/{total}]",
            chunk,
            runtime_evidence_text,
            evidence_fields,
        )
        for index, chunk in enumerate(chunks, 1)
    )


def render_runtime_evidence(events, head_sha: str) -> str:
    data_allowlist = {
        "validation": {"command_identity", "result_digest"},
        "weakening": {
            "mechanical_verdict",
            "blocking_findings",
            "review_candidates",
            "final_validation_accepted_event_sequence",
            "command_identity",
        },
        "tracked-evidence-snapshot": {
            "log_path",
            "log_blob_sha",
            "included_event_sequence",
            "validation_contract_digest",
            "snapshot_format_version",
        },
        "final-validation-attempt": {
            "snapshot_event_sequence",
            "exact_head_sha",
            "validation_log_path",
            "validation_log_blob_sha",
            "validation_contract_digest",
            "command_identity",
            "started_at",
            "completed_at",
            "result_digest",
        },
        "final-validation-accepted": {
            "attempt_event_sequence",
            "snapshot_event_sequence",
            "exact_head_sha",
            "validation_log_path",
            "validation_log_blob_sha",
            "validation_contract_digest",
            "command_identity",
            "started_at",
            "completed_at",
            "result_digest",
        },
    }
    weakening_event, weakening_data = _authoritative_weakening_event(
        events, head_sha
    )
    allowed = []
    for event in events:
        if event.head_sha != head_sha or event.kind not in data_allowlist:
            continue
        if event.kind == "weakening" and event is not weakening_event:
            continue
        source = weakening_data if event.kind == "weakening" else (event.data or {})
        projected = {
            key: source[key] for key in data_allowlist[event.kind] if key in source
        }
        if "command_identity" in projected and not re.fullmatch(
            r"[0-9a-f]{64}", str(projected["command_identity"])
        ):
            projected.pop("command_identity")
        allowed.append(
            {
                "sequence": event.sequence,
                "kind": event.kind,
                "result": event.result,
                "head_sha": event.head_sha,
                "data": redact_value(projected),
            }
        )
    return json.dumps(allowed, sort_keys=True, separators=(",", ":"))


def _authoritative_weakening_event(events, head_sha: str):
    candidates = [
        event
        for event in events
        if event.kind == "weakening" and event.head_sha == head_sha
    ]
    if not candidates:
        return None, {}
    normalized = []
    for event in candidates:
        if event.result != "PASS":
            raise ValueError("Current-HEAD weakening evidence did not pass")
        normalized.append((event, _normalize_weakening_data(event.data)))
    canonical_payloads = {
        json.dumps(
            {
                key: value
                for key, value in data.items()
                if key
                not in {
                    "final_validation_accepted_event_sequence",
                    "command_identity",
                }
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for _, data in normalized
    }
    if len(canonical_payloads) != 1:
        raise ValueError("Current-HEAD weakening evidence is contradictory")
    return normalized[-1]


def _require_accepted_validation_event(
    events,
    head_sha: str,
    *,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    final_validation_accepted_event_sequence: int,
):
    if (
        not isinstance(final_validation_accepted_event_sequence, int)
        or isinstance(final_validation_accepted_event_sequence, bool)
        or final_validation_accepted_event_sequence < 1
    ):
        raise ValueError("Final-validation acceptance sequence is invalid")
    accepted = next(
        (
            event
            for event in events
            if event.sequence == final_validation_accepted_event_sequence
        ),
        None,
    )
    if accepted is None:
        raise ValueError("Missing final-validation-accepted PASS for current HEAD")
    accepted_data = accepted.data or {}
    command_identity = accepted_data.get("command_identity")
    if (
        accepted.kind != "final-validation-accepted"
        or accepted.phase != "post-evidence"
        or accepted.result != "PASS"
        or accepted.head_sha != head_sha
        or accepted.feature != feature
        or accepted.repository != repository
        or accepted.branch != branch
        or accepted.worktree != worktree
        or accepted_data.get("exact_head_sha") != head_sha
        or not isinstance(command_identity, str)
        or re.fullmatch(r"[0-9a-f]{64}", command_identity) is None
    ):
        raise ValueError("Final-validation acceptance identity mismatched")
    return accepted, command_identity


def require_authoritative_weakening_event(
    events,
    head_sha: str,
    *,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    final_validation_accepted_event_sequence: int,
):
    accepted, command_identity = _require_accepted_validation_event(
        events,
        head_sha,
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        final_validation_accepted_event_sequence=(
            final_validation_accepted_event_sequence
        ),
    )
    current_head_events = [
        event
        for event in events
        if event.kind == "weakening" and event.head_sha == head_sha
    ]
    if not current_head_events:
        raise ValueError("No canonical weakening PASS for current HEAD")
    canonical_fields = {
        "mechanical_verdict",
        "blocking_findings",
        "review_candidates",
        "final_validation_accepted_event_sequence",
        "command_identity",
    }
    for event in current_head_events:
        if (
            event.feature != feature
            or event.repository != repository
            or event.branch != branch
            or event.worktree != worktree
            or event.phase != "delivery"
        ):
            raise ValueError("Current-HEAD weakening evidence identity mismatched")
        if not isinstance(event.data, dict) or set(event.data) != canonical_fields:
            raise ValueError("Current-HEAD weakening evidence is not canonical")
        bound_acceptance, bound_command_identity = (
            _require_accepted_validation_event(
                events,
                head_sha,
                feature=feature,
                repository=repository,
                branch=branch,
                worktree=worktree,
                final_validation_accepted_event_sequence=event.data[
                    "final_validation_accepted_event_sequence"
                ],
            )
        )
        if (
            event.sequence <= bound_acceptance.sequence
            or event.data["command_identity"] != bound_command_identity
        ):
            raise ValueError("Current-HEAD weakening evidence run identity mismatched")
    matching = [
        event
        for event in current_head_events
        if event.data["final_validation_accepted_event_sequence"]
        == accepted.sequence
        and event.data["command_identity"] == command_identity
    ]
    if not matching:
        raise ValueError("Current-HEAD weakening evidence run identity mismatched")
    event, data = _authoritative_weakening_event(matching, head_sha)
    if event is None or data["mechanical_verdict"] != "PASS":
        raise ValueError("No canonical weakening PASS for current HEAD")
    return event


def _normalize_weakening_data(data: dict | None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Weakening evidence data is invalid")
    canonical = {"mechanical_verdict", "blocking_findings", "review_candidates"}
    if canonical.issubset(data):
        blocking = data["blocking_findings"]
        review_candidates = data["review_candidates"]
        verdict = data["mechanical_verdict"]
    elif set(data) == {"findings"}:
        findings = data["findings"]
        if not isinstance(findings, list):
            raise ValueError("Legacy weakening findings are invalid")
        blocking = [item for item in findings if _finding_required(item) is True]
        review_candidates = [
            item for item in findings if _finding_required(item) is False
        ]
        verdict = "FAIL" if blocking else "PASS"
    else:
        raise ValueError("Weakening evidence fields are incomplete or unknown")
    if verdict != "PASS":
        raise ValueError("Current-HEAD weakening evidence verdict did not pass")
    if not isinstance(blocking, list) or not isinstance(review_candidates, list):
        raise ValueError("Weakening evidence finding lists are invalid")
    for item in blocking:
        if _finding_required(item) is not True:
            raise ValueError("Blocking weakening finding is not required")
    for item in review_candidates:
        if _finding_required(item) is not False:
            raise ValueError("Weakening review candidate is marked required")
    if blocking:
        raise ValueError("Passing weakening evidence contains blocking findings")
    normalized = {
        "mechanical_verdict": "PASS",
        "blocking_findings": blocking,
        "review_candidates": review_candidates,
    }
    binding_fields = {
        "final_validation_accepted_event_sequence",
        "command_identity",
    }
    if binding_fields.issubset(data):
        normalized.update({field: data[field] for field in binding_fields})
    return normalized


def _finding_required(value: object) -> bool:
    required_keys = {"severity", "category", "file", "description", "required"}
    if not isinstance(value, dict) or set(value) != required_keys:
        raise ValueError("Weakening evidence finding has invalid fields")
    if value["severity"] not in {"low", "medium", "high"}:
        raise ValueError("Weakening evidence finding has invalid severity")
    if not all(
        isinstance(value[key], str)
        for key in ("category", "file", "description")
    ) or not isinstance(value["required"], bool):
        raise ValueError("Weakening evidence finding has invalid values")
    return value["required"]


def _paths_for_focus(paths: list[str], focus: str) -> list[str]:
    tests = [path for path in paths if path.startswith("tests/")]
    security_names = {
        "scripts/agent/review.py",
        "scripts/agent/delivery.py",
        "scripts/agent/gates.py",
        "scripts/agent/events.py",
    }
    security = [path for path in paths if path in security_names]
    maintainability_names = {
        "scripts/agent/work.py",
        "scripts/agent/review_shards.py",
        "README.md",
        "docs/ai-operation.md",
    }
    maintainability = [path for path in paths if path in maintainability_names]
    assigned = set(tests + security + maintainability)
    if focus == "tests":
        return tests
    if focus == "security":
        return security
    if focus == "maintainability":
        return maintainability
    if focus == "spec-scope":
        # Specification compliance and scope review requires the complete diff,
        # including files also assigned to focused review shards.
        return paths
    return [path for path in paths if path.startswith("scripts/agent/")]


def run_review(
    repo: Path,
    feature_dir: Path,
    review_focus: str = "complete",
    runtime_evidence_text: str = "[]",
    evidence_fields: dict | None = None,
) -> tuple[ReviewResult, str, str]:
    prepared = prepare_review(
        repo,
        feature_dir,
        review_focus,
        runtime_evidence_text=runtime_evidence_text,
        evidence_fields=evidence_fields,
    )
    result, stderr = run_prepared(repo, prepared)
    return result, prepared.prompt, stderr


def run_prepared(
    repo: Path,
    prepared: PreparedReview,
    *,
    timeout_seconds: float = REVIEW_TIMEOUT_SECONDS,
    attempt: int = 1,
) -> tuple[ReviewResult, str]:
    if timeout_seconds > REVIEW_TIMEOUT_SECONDS:
        raise ValueError("Review timeout exceeds the 600-second maximum")
    completed = run_process_group(
        prepared.command,
        prepared.prompt,
        repo,
        timeout_seconds,
        {
            "shard": prepared.identity.shard,
            "head_sha": prepared.identity.head_sha,
            "attempt": attempt,
            "input_digest": prepared.identity.diff_input_digest,
        },
    )
    if completed.returncode:
        raise RuntimeError(
            "Review Codex failed: "
            f"stdout={_safe_stream_tail(completed.stdout)}; "
            f"stderr={_safe_stream_tail(completed.stderr)}"
        )
    return parse_review(completed.stdout), completed.stderr


def run_process_group(
    command: tuple[str, ...],
    input_text: str,
    cwd: Path,
    timeout_seconds: float,
    identity: dict,
    *,
    term_grace_seconds: float = 2.0,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    tracker = _DescendantTracker(process.pid)
    tracker.start()
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
        tracker.stop()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as error:
        process_group = process.pid
        descendants = tracker.stop()
        stdout = _output_text(error.output)
        stderr = _output_text(error.stderr)
        termination = "term"
        _signal_process_group(process_group, signal.SIGTERM)
        _signal_processes(descendants, signal.SIGTERM)
        try:
            tail_out, tail_err = process.communicate(timeout=term_grace_seconds)
        except subprocess.TimeoutExpired:
            tail_out, tail_err = "", ""
        if not _wait_for_targets_exit(process_group, descendants, term_grace_seconds):
            termination = "kill"
            _signal_process_group(process_group, signal.SIGKILL)
            _signal_processes(descendants, signal.SIGKILL)
            _wait_for_targets_exit(process_group, descendants, term_grace_seconds)
        _reap_without_pipe_wait(process, term_grace_seconds)
        surviving_pids = [
            pid for pid, started in descendants.items() if _same_process(pid, started)
        ]
        group_survived = _process_group_exists(process_group)
        group_terminated = not group_survived and not surviving_pids
        diagnostic = {
            **identity,
            "configured_timeout": timeout_seconds,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command_id": Path(command[0]).name + " " + command[1],
            "prompt_chars": len(input_text),
            "prompt_bytes": len(input_text.encode("utf-8")),
            "stdout_tail": _safe_stream_tail(stdout + _output_text(tail_out)),
            "stderr_tail": _safe_stream_tail(stderr + _output_text(tail_err)),
            "process_status": "timeout",
            "pid": process.pid,
            "root_pid": process.pid,
            "process_group_id": process_group,
            "termination": termination,
            "process_group_terminated": group_terminated,
            "tracked_descendant_pids": sorted(descendants),
            "observed_descendant_pids": sorted(descendants),
            "term_targets": {
                "process_group_id": process_group,
                "pids": sorted(descendants),
            },
            "kill_targets": {
                "process_group_id": process_group if termination == "kill" else None,
                "pids": sorted(descendants) if termination == "kill" else [],
            },
            "termination_confirmed": group_terminated,
            "known_survivors": (
                ([f"pgid:{process_group}"] if group_survived else [])
                + [f"pid:{pid}" for pid in surviving_pids]
            ),
        }
        raise ReviewTimeout(diagnostic) from None


def _process_group_exists(process_group: int) -> bool:
    result = subprocess.run(
        ["ps", "-axo", "pgid=,stat="],
        text=True,
        capture_output=True,
        check=False,
        timeout=2,
    )
    for line in result.stdout.splitlines():
        values = line.split(maxsplit=1)
        if (
            len(values) == 2
            and values[0].isdigit()
            and int(values[0]) == process_group
            and not values[1].startswith("Z")
        ):
            return True
    return False


def _signal_process_group(process_group: int, signal_value: signal.Signals) -> None:
    try:
        os.killpg(process_group, signal_value)
    except (ProcessLookupError, PermissionError):
        return


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_processes(processes: dict[int, str], signal_value: signal.Signals) -> None:
    for pid in sorted(processes, reverse=True):
        if not _same_process(pid, processes[pid]):
            continue
        try:
            os.kill(pid, signal_value)
        except (ProcessLookupError, PermissionError):
            continue


def _wait_for_process_group_exit(process_group: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while _process_group_exists(process_group):
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    return True


def _wait_for_targets_exit(
    process_group: int, descendants: dict[int, str], timeout_seconds: float
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while _process_group_exists(process_group) or any(
        _same_process(pid, started) for pid, started in descendants.items()
    ):
        if time.monotonic() >= deadline:
            return False
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    return True


class _DescendantTracker:
    """Best-effort PID tracking that retains children even after re-parenting."""

    def __init__(self, root_pid: int):
        self.root_pid = root_pid
        self.seen: dict[int, str] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._sample()
        self._thread.start()

    def stop(self) -> dict[int, str]:
        self._sample()
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._sample()
        return dict(self.seen)

    def _run(self) -> None:
        while not self._stop.wait(0.01):
            self._sample()

    def _sample(self) -> None:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,lstart="],
            text=True,
            capture_output=True,
            check=False,
            timeout=2,
        )
        if result.returncode:
            return
        parents: dict[int, tuple[int, str]] = {}
        for line in result.stdout.splitlines():
            values = line.split(maxsplit=2)
            if len(values) == 3 and values[0].isdigit() and values[1].isdigit():
                parents[int(values[0])] = (int(values[1]), values[2].strip())
        roots = {self.root_pid, *self.seen.keys()}
        changed = True
        while changed:
            changed = False
            for pid, (parent, started) in parents.items():
                if pid != self.root_pid and parent in roots and pid not in self.seen:
                    self.seen[pid] = started
                    roots.add(pid)
                    changed = True


def _process_start(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        text=True,
        capture_output=True,
        check=False,
        timeout=2,
    )
    value = result.stdout.strip()
    return value or None


def _same_process(pid: int, started: str) -> bool:
    if _process_start(pid) != started:
        return False
    result = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        text=True,
        capture_output=True,
        check=False,
        timeout=2,
    )
    status = result.stdout.strip()
    return bool(status) and not status.startswith("Z")


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _safe_stream_tail(value: str, limit: int = 2000) -> str:
    safe_controls = "".join(
        character if character in "\n\t" or ord(character) >= 32 else "?"
        for character in value
    )
    return redact(safe_controls, limit)


def _reap_without_pipe_wait(
    process: subprocess.Popen[str], timeout_seconds: float
) -> None:
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


def bind_context(prepared: PreparedReview, context: dict) -> PreparedReview:
    combined = hashlib.sha256(
        (prepared.identity.diff_input_digest + _digest(context)).encode("utf-8")
    ).hexdigest()
    return replace(
        prepared, identity=replace(prepared.identity, diff_input_digest=combined)
    )


def _digest(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def identity_set_digest(digests: list[str]) -> str:
    return _digest({"review_identity_digests": sorted(digests)})


def review_with_repairs(run_once, repair, max_attempts: int) -> ReviewResult:
    previous = None
    limit = max(1, min(max_attempts, 5))
    for attempt in range(1, limit + 1):
        result = run_once()
        if not result.required_findings:
            return result
        signature = result.signature()
        if signature == previous:
            raise RuntimeError(
                "Independent review repeated identical required findings"
            )
        previous = signature
        if attempt < limit:
            repair(result.required_findings)
    raise RuntimeError("Independent review repair limit reached")
