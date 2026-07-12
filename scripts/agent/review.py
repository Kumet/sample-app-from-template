from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from .weakening import Finding


MAX_REVIEW_INPUT_CHARS = 100_000
REVIEW_TIMEOUT_SECONDS = 600
REVIEW_SCHEMA_VERSION = "1"
REVIEW_PROMPT_VERSION = "1"
MODEL_SETTINGS = (
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
        return tuple(f for f in self.findings if f.required and f.severity == "high")

    def signature(self) -> str:
        return json.dumps([f.__dict__ for f in self.required_findings], sort_keys=True)


@dataclass(frozen=True)
class ReviewIdentity:
    feature: str
    head_sha: str
    shard: str
    schema_version: str
    prompt_version: str
    model_settings: tuple[str, ...]
    command: tuple[str, ...]
    reviewed_files: tuple[str, ...]
    input_digest: str

    def payload(self) -> dict:
        return {
            "feature": self.feature,
            "head_sha": self.head_sha,
            "shard": self.shard,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "model_settings": list(self.model_settings),
            "command": list(self.command),
            "reviewed_files": list(self.reviewed_files),
            "input_digest": self.input_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True)
class PreparedReview:
    identity: ReviewIdentity
    prompt: str
    command: tuple[str, ...]


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
    repo: Path, feature_dir: Path, review_focus: str = "complete"
) -> PreparedReview:
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
    patch = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            base.stdout.strip(),
            "HEAD",
            "--",
            ".",
            f":(exclude){feature_path}/**",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if patch.returncode:
        raise RuntimeError(f"Cannot create review diff: {patch.stderr[-1000:]}")
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
        "diff_text": patch.stdout,
    }
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
        **inputs,
    )
    command = (
        "codex",
        "exec",
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
    reviewed_files = tuple(
        sorted(
            set(changed.stdout.splitlines())
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
        feature_dir.name,
        head.stdout.strip(),
        review_focus,
        REVIEW_SCHEMA_VERSION,
        REVIEW_PROMPT_VERSION,
        MODEL_SETTINGS,
        command,
        reviewed_files,
        hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )
    return PreparedReview(identity, prompt, command)


def run_review(
    repo: Path, feature_dir: Path, review_focus: str = "complete"
) -> tuple[ReviewResult, str, str]:
    prepared = prepare_review(repo, feature_dir, review_focus)
    result, stderr = run_prepared(repo, prepared)
    return result, prepared.prompt, stderr


def run_prepared(repo: Path, prepared: PreparedReview) -> tuple[ReviewResult, str]:
    try:
        completed = subprocess.run(
            prepared.command,
            input=prepared.prompt,
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=REVIEW_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"Independent review timed out after {REVIEW_TIMEOUT_SECONDS} seconds"
        ) from error
    if completed.returncode:
        raise RuntimeError(f"Review Codex failed: {completed.stderr[-4000:]}")
    return parse_review(completed.stdout), completed.stderr


def bind_context(prepared: PreparedReview, context: dict) -> PreparedReview:
    combined = hashlib.sha256(
        (prepared.identity.input_digest + _digest(context)).encode("utf-8")
    ).hexdigest()
    return replace(prepared, identity=replace(prepared.identity, input_digest=combined))


def _digest(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
