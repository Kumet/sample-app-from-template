from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .parser import ContractError


TARGET_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass(frozen=True)
class RepositoryPolicy:
    default_branch: str
    allowed_make_targets: frozenset[str]
    max_tasks: int
    max_attempts_per_task: int
    max_review_attempts: int
    max_ci_attempts: int
    max_elapsed_minutes: int
    auto_merge_low_risk: bool
    high_risk_paths: tuple[str, ...]
    medium_risk_paths: tuple[str, ...]
    allow_legacy_contracts: bool = False
    queue_concurrency: int = 1
    max_codex_calls: int = 20
    max_review_calls: int = 8
    quality: dict | None = None


def load_policy(repo: Path) -> RepositoryPolicy:
    path = repo / ".agent-policy.toml"
    if not path.is_file():
        raise ContractError("Missing repository policy: .agent-policy.toml")
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if raw.get("version") != 1:
        raise ContractError("Repository policy version must be 1")
    targets = raw.get("allowed_make_targets")
    if not isinstance(targets, list) or not targets or not all(
        isinstance(v, str) and TARGET_RE.fullmatch(v) for v in targets
    ):
        raise ContractError("allowed_make_targets must contain safe Make target names")
    risk = raw.get("risk_paths", {})
    return RepositoryPolicy(
        default_branch=_text(raw, "default_branch"),
        allowed_make_targets=frozenset(targets),
        max_tasks=_integer(raw, "max_tasks", 1, 100),
        max_attempts_per_task=_integer(raw, "max_attempts_per_task", 1, 5),
        max_review_attempts=_integer(raw, "max_review_attempts", 1, 5),
        max_ci_attempts=_integer(raw, "max_ci_attempts", 1, 5),
        max_elapsed_minutes=_integer(raw, "max_elapsed_minutes", 1, 1440),
        auto_merge_low_risk=raw.get("auto_merge_low_risk") is True,
        high_risk_paths=_patterns(risk, "high"),
        medium_risk_paths=_patterns(risk, "medium"),
        allow_legacy_contracts=raw.get("allow_legacy_contracts") is True,
        queue_concurrency=_integer(raw, "queue_concurrency", 1, 8),
        max_codex_calls=_integer(raw, "max_codex_calls", 1, 100),
        max_review_calls=_integer(raw, "max_review_calls", 1, 100),
        quality=raw.get("quality", {}),
    )


def validation_commands(mapping: object, policy: RepositoryPolicy) -> dict[str, tuple[str, ...]]:
    if not isinstance(mapping, dict) or not mapping:
        raise ContractError("validations must be a non-empty table")
    commands = {}
    for name, target in mapping.items():
        if not isinstance(name, str) or not TARGET_RE.fullmatch(name):
            raise ContractError(f"Invalid validation name: {name!r}")
        if not isinstance(target, str) or not TARGET_RE.fullmatch(target):
            raise ContractError(f"Invalid Make target: {target!r}")
        if target not in policy.allowed_make_targets:
            raise ContractError(f"Make target is not allowlisted: {target}")
        commands[name] = ("make", target)
    return commands


def _text(raw: dict, name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be text")
    return value


def _integer(raw: dict, name: str, low: int, high: int) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ContractError(f"{name} must be between {low} and {high}")
    return value


def _patterns(raw: object, name: str) -> tuple[str, ...]:
    if not isinstance(raw, dict):
        raise ContractError("risk_paths must be a table")
    value = raw.get(name, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ContractError(f"risk_paths.{name} must be a string array")
    return tuple(value)
