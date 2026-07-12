from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryPolicy:
    failure_class: str
    strategy: str
    max_attempts: int
    retryable: bool


UNSAFE = {"scope", "secret", "contract", "high-risk"}


def classify(name: str, returncode: int, output: str) -> str:
    text = output.lower()
    if "secret" in text or "credential" in text:
        return "secret"
    if "out-of-scope" in text or "forbidden files" in text:
        return "scope"
    if "timed out" in text or returncode == 124:
        return "timeout"
    if "no module named" in text or "command not found" in text or returncode == 127:
        return "dependency"
    if "syntaxerror" in text or "compile" in name:
        return "compile"
    if "typecheck" in name or "mypy" in text or "tsc" in text:
        return "typecheck"
    if "lint" in name:
        return "lint"
    if "integration" in name:
        return "integration-test"
    if "test" in name or "assert" in text or "failed" in text:
        return "unit-test"
    if "codex" in name:
        return "codex"
    if "github" in name or "git " in text:
        return "git-github"
    return "unknown"


def policy_for(failure_class: str, configured_limit: int) -> RecoveryPolicy:
    limit = max(1, min(configured_limit, 5))
    if failure_class in UNSAFE:
        return RecoveryPolicy(failure_class, "human-review", 0, False)
    if failure_class == "dependency":
        return RecoveryPolicy(failure_class, "run-allowlisted-setup-once", min(2, limit), True)
    if failure_class in {"timeout", "flaky"}:
        return RecoveryPolicy(failure_class, "rerun-without-change", min(2, limit), True)
    return RecoveryPolicy(failure_class, "codex-repair", limit, True)
