from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .evidence import redact
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
    pathspec = (
        list(review_paths)
        if review_paths is not None
        else [".", f":(exclude){feature_path}/**"]
    )
    patch = subprocess.run(
        ["git", "diff", "--no-ext-diff", base.stdout.strip(), "HEAD", "--", *pathspec],
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
        "validation_contract_text": (feature_dir / "validation.toml").read_text(
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
        feature_dir.name,
        head.stdout.strip(),
        review_focus,
        REVIEW_SCHEMA_VERSION,
        REVIEW_PROMPT_VERSION,
        MODEL_SETTINGS,
        command,
        reviewed_files,
        hashlib.sha256(
            prompt.encode("utf-8")
            + (repo / "schemas" / "review-result.schema.json").read_bytes()
        ).hexdigest(),
    )
    return PreparedReview(identity, prompt, command)


def prepare_reviews(
    repo: Path, feature_dir: Path, review_focus: str = "complete"
) -> tuple[PreparedReview, ...]:
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
    max_patch_chars = 70_000
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
        prepare_review(repo, feature_dir, f"{review_focus} [{index}/{total}]", chunk)
        for index, chunk in enumerate(chunks, 1)
    )


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
        return [path for path in paths if path not in assigned]
    return [path for path in paths if path.startswith("scripts/agent/")]


def run_review(
    repo: Path, feature_dir: Path, review_focus: str = "complete"
) -> tuple[ReviewResult, str, str]:
    prepared = prepare_review(repo, feature_dir, review_focus)
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
            "input_digest": prepared.identity.input_digest,
        },
    )
    if completed.returncode:
        raise RuntimeError(f"Review Codex failed: {completed.stderr[-4000:]}")
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
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout_seconds)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as error:
        stdout = error.output or ""
        stderr = error.stderr or ""
        termination = "term"
        os.killpg(process.pid, signal.SIGTERM)
        try:
            tail_out, tail_err = process.communicate(timeout=term_grace_seconds)
        except subprocess.TimeoutExpired:
            termination = "kill"
            os.killpg(process.pid, signal.SIGKILL)
            tail_out, tail_err = process.communicate()
        diagnostic = {
            **identity,
            "configured_timeout": timeout_seconds,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command_id": Path(command[0]).name + " " + command[1],
            "prompt_chars": len(input_text),
            "prompt_bytes": len(input_text.encode("utf-8")),
            "stdout_tail": redact((stdout + (tail_out or ""))[-2000:]),
            "stderr_tail": redact((stderr + (tail_err or ""))[-2000:]),
            "process_status": "timeout",
            "pid": process.pid,
            "termination": termination,
            "process_group_terminated": process.poll() is not None,
        }
        raise ReviewTimeout(diagnostic) from error


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
