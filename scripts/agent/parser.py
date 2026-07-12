from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path


FEATURE_RE = re.compile(r"^[0-9]{3,}(?:-[a-z0-9][a-z0-9-]*)?$")
TASK_RE = re.compile(r"^- \[([ xX])\] (T[0-9]{3,}):\s+(.+)$")
FIELD_RE = re.compile(r"^  - ([A-Za-z][A-Za-z-]*):\s*(.*)$")


class ContractError(ValueError):
    """The external feature contract is invalid."""


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    completed: bool
    requirements: tuple[str, ...]
    validations: tuple[str, ...]
    line_index: int


@dataclass(frozen=True)
class WorkConfig:
    version: int
    max_tasks: int
    max_attempts_per_task: int
    max_final_validation_attempts: int
    commands: dict[str, tuple[str, ...]]
    allowed: tuple[str, ...]
    forbidden: tuple[str, ...]
    risk: str = "medium"
    auto_merge: bool = False
    max_review_attempts: int = 3
    max_ci_attempts: int = 3
    risk_domains: tuple[str, ...] = ()


def resolve_feature(repo: Path, feature: str) -> Path:
    if not FEATURE_RE.fullmatch(feature):
        raise ContractError(f"Invalid FEATURE value: {feature!r}")
    specs = repo / "specs"
    if "-" in feature:
        matches = [specs / feature] if (specs / feature).is_dir() else []
    else:
        matches = sorted(path for path in specs.glob(f"{feature}-*") if path.is_dir())
    if not matches:
        raise ContractError(f"Feature not found: {feature}")
    if len(matches) != 1:
        raise ContractError(f"Feature is ambiguous: {feature}")
    return matches[0]


def load_config(feature_dir: Path, repository_policy=None) -> WorkConfig:
    required = ("spec.md", "plan.md", "tasks.md", "validation.toml", "validation-log.md")
    missing = [name for name in required if not (feature_dir / name).is_file()]
    if missing:
        raise ContractError("Missing required artifacts: " + ", ".join(missing))
    with (feature_dir / "validation.toml").open("rb") as handle:
        raw = tomllib.load(handle)
    version = raw.get("version")
    if version not in {1, 2}:
        raise ContractError("validation.toml version must be 1 or 2")
    commands: dict[str, tuple[str, ...]] = {}
    if version == 1:
        if repository_policy is not None and not repository_policy.allow_legacy_contracts:
            raise ContractError("Version 1 contracts are disabled; run migrate-contract")
        for name, command in raw.get("commands", {}).items():
            if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
                raise ContractError(f"Invalid validation name: {name!r}")
            if not isinstance(command, list) or not command or not all(
                isinstance(arg, str) and arg for arg in command
            ):
                raise ContractError(f"Validation {name!r} must be a non-empty string array")
            commands[name] = tuple(command)
    else:
        if repository_policy is None:
            raise ContractError("Repository policy is required for version 2")
        from .policy import validation_commands
        commands = validation_commands(raw.get("validations"), repository_policy)
    scope = raw.get("scope", {})
    allowed = _string_list(scope.get("allowed"), "scope.allowed")
    forbidden = _string_list(scope.get("forbidden"), "scope.forbidden")
    return WorkConfig(
        version=version,
        max_tasks=_bounded_int(raw, "max_tasks", 1, 100),
        max_attempts_per_task=_bounded_int(raw, "max_attempts_per_task", 1, 5),
        max_final_validation_attempts=_bounded_int(
            raw, "max_final_validation_attempts", 1, 5
        ),
        commands=commands,
        allowed=allowed,
        forbidden=forbidden,
        risk=raw.get("risk", "medium"),
        auto_merge=raw.get("auto_merge") is True,
        max_review_attempts=_bounded_int(raw, "max_review_attempts", 1, 5) if version == 2 else 3,
        max_ci_attempts=_bounded_int(raw, "max_ci_attempts", 1, 5) if version == 2 else 3,
        risk_domains=_optional_string_list(raw.get("risk_domains", []), "risk_domains") if version == 2 else (),
    )


def parse_tasks(path: Path, known_validations: set[str]) -> list[Task]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tasks: list[Task] = []
    current: dict[str, object] | None = None
    for index, line in enumerate(lines):
        match = TASK_RE.fullmatch(line)
        if match:
            if current:
                tasks.append(_make_task(current, known_validations))
            current = {
                "task_id": match.group(2),
                "title": match.group(3).strip(),
                "completed": match.group(1).lower() == "x",
                "line_index": index,
                "requirements": (),
                "validations": (),
            }
            continue
        field = FIELD_RE.fullmatch(line)
        if field and current:
            values = tuple(value.strip() for value in field.group(2).split(",") if value.strip())
            key = field.group(1).lower()
            if key == "requirements":
                current["requirements"] = values
            elif key == "validation":
                current["validations"] = values
    if current:
        tasks.append(_make_task(current, known_validations))
    if not tasks:
        raise ContractError("tasks.md contains no tasks")
    ids = [task.task_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ContractError("tasks.md contains duplicate task IDs")
    return tasks


def mark_complete(path: Path, task: Task) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    expected = f"- [ ] {task.task_id}:"
    if task.line_index >= len(lines) or not lines[task.line_index].startswith(expected):
        raise ContractError(f"Task state changed unexpectedly: {task.task_id}")
    lines[task.line_index] = lines[task.line_index].replace("- [ ]", "- [x]", 1)
    path.write_text("".join(lines), encoding="utf-8")


def _make_task(values: dict[str, object], known: set[str]) -> Task:
    validations = tuple(values["validations"])
    if not validations:
        raise ContractError(f"{values['task_id']} has no Validation field")
    unknown = sorted(set(validations) - known)
    if unknown:
        raise ContractError(f"{values['task_id']} uses unknown validations: {', '.join(unknown)}")
    return Task(**values)  # type: ignore[arg-type]


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
        raise ContractError(f"{name} must be a non-empty string array")
    return tuple(value)


def _optional_string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ContractError(f"{name} must be a string array")
    return tuple(value)


def _bounded_int(raw: dict[str, object], name: str, minimum: int, maximum: int) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ContractError(f"{name} must be between {minimum} and {maximum}")
    return value
