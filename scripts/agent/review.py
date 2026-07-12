from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .weakening import Finding


MAX_REVIEW_INPUT_CHARS = 100_000


@dataclass(frozen=True)
class ReviewResult:
    result: str
    findings: tuple[Finding, ...]

    @property
    def required_findings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.required and f.severity == "high")

    def signature(self) -> str:
        return json.dumps([f.__dict__ for f in self.required_findings], sort_keys=True)


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
        if not all(isinstance(value[k], str) for k in ("category", "file", "description")):
            raise ValueError("Review finding text fields are invalid")
        if not isinstance(value["required"], bool):
            raise ValueError("Review required field must be boolean")
        findings.append(Finding(**value))
    result = ReviewResult(raw["result"], tuple(findings))
    if result.result == "pass" and result.required_findings:
        raise ValueError("Passing review cannot contain required high findings")
    return result


def run_review(repo: Path, feature_dir: Path, review_focus: str = "complete") -> tuple[ReviewResult, str, str]:
    template = (repo / "prompts" / "review-feature.md").read_text(encoding="utf-8")
    base = subprocess.run(["git", "merge-base", "main", "HEAD"], cwd=repo, text=True,
                          capture_output=True, check=False, timeout=30)
    if base.returncode:
        raise RuntimeError(f"Cannot determine review base: {base.stderr[-1000:]}")
    feature_path = str(feature_dir.relative_to(repo))
    patch = subprocess.run(["git", "diff", "--no-ext-diff", base.stdout.strip(), "HEAD",
                            "--", ".", f":(exclude){feature_path}/**"],
                           cwd=repo, text=True, capture_output=True, check=False, timeout=60)
    if patch.returncode:
        raise RuntimeError(f"Cannot create review diff: {patch.stderr[-1000:]}")
    inputs = {
        "spec_text": (feature_dir / "spec.md").read_text(encoding="utf-8"),
        "plan_text": (feature_dir / "plan.md").read_text(encoding="utf-8"),
        "tasks_text": (feature_dir / "tasks.md").read_text(encoding="utf-8"),
        "validation_text": (feature_dir / "validation-log.md").read_text(encoding="utf-8"),
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
    command = ["codex", "exec", "--sandbox", "read-only", "-c", 'approval_policy="never"',
               "-c", 'model_reasoning_effort="low"',
               "--ephemeral", "--cd", str(repo), "--output-schema",
               str(repo / "schemas" / "review-result.schema.json"), "-"]
    try:
        completed = subprocess.run(command, input=prompt, cwd=repo, text=True,
                                   capture_output=True, check=False, timeout=300)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Independent review timed out after 300 seconds") from error
    if completed.returncode:
        raise RuntimeError(f"Review Codex failed: {completed.stderr[-4000:]}")
    return parse_review(completed.stdout), prompt, completed.stderr


def review_with_repairs(run_once, repair, max_attempts: int) -> ReviewResult:
    previous = None
    limit = max(1, min(max_attempts, 5))
    for attempt in range(1, limit + 1):
        result = run_once()
        if not result.required_findings:
            return result
        signature = result.signature()
        if signature == previous:
            raise RuntimeError("Independent review repeated identical required findings")
        previous = signature
        if attempt < limit:
            repair(result.required_findings)
    raise RuntimeError("Independent review repair limit reached")
