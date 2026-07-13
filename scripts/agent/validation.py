from __future__ import annotations

import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import git_utils
from .parser import WorkConfig


class ScopeViolation(ValueError):
    """A scope failure whose paths remain machine-readable through wrapping."""

    def __init__(self, category: str, paths: list[str]):
        if category not in {"forbidden", "outside"}:
            raise ValueError("Unknown scope violation category")
        normalized = tuple(_normalize_changed_path(path) for path in paths)
        self.category = category
        self.paths = normalized
        label = "Forbidden files changed" if category == "forbidden" else "Out-of-scope files changed"
        super().__init__(label + ": " + ", ".join(normalized))


@dataclass(frozen=True)
class CommandResult:
    name: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0

    def signature(self) -> str:
        tail = (self.stderr or self.stdout)[-4000:]
        return f"{self.name}:{self.returncode}:{tail}"


def run_named(repo: Path, config: WorkConfig, name: str) -> CommandResult:
    command = config.commands[name]
    try:
        result = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False, timeout=1800)
    except FileNotFoundError as error:
        return CommandResult(name, command, 127, "", str(error))
    except subprocess.TimeoutExpired as error:
        return CommandResult(name, command, 124, error.stdout or "", error.stderr or "Validation timed out")
    return CommandResult(name, command, result.returncode, result.stdout, result.stderr)


def validate_scope(paths: list[str], config: WorkConfig) -> None:
    forbidden = [path for path in paths if _matches_any(path, config.forbidden)]
    if forbidden:
        raise ScopeViolation("forbidden", forbidden)
    outside = [path for path in paths if not _matches_any(path, config.allowed)]
    if outside:
        raise ScopeViolation("outside", outside)


def validate_task(repo: Path, config: WorkConfig, names: tuple[str, ...]) -> list[CommandResult]:
    paths = git_utils.changed_paths(repo)
    if not paths:
        raise ValueError("Codex produced no repository changes")
    validate_scope(paths, config)
    git_utils.diff_check(repo)
    results = [run_named(repo, config, name) for name in names]
    secret_command = (str(repo / "scripts" / "check-secrets.sh"),)
    try:
        secret = subprocess.run(
            secret_command, cwd=repo, text=True, capture_output=True, check=False, timeout=300
        )
        results.append(
            CommandResult("secret-check", secret_command, secret.returncode, secret.stdout, secret.stderr)
        )
    except FileNotFoundError as error:
        results.append(CommandResult("secret-check", secret_command, 127, "", str(error)))
    except subprocess.TimeoutExpired as error:
        results.append(CommandResult("secret-check", secret_command, 124, error.stdout or "", "Secret check timed out"))
    failed = [result for result in results if not result.succeeded]
    if failed:
        detail = "\n".join(
            f"{result.name} exited {result.returncode}: {(result.stderr or result.stdout)[-4000:]}"
            for result in failed
        )
        raise ValidationFailure(detail, results)
    return results


class ValidationFailure(RuntimeError):
    def __init__(self, message: str, results: list[CommandResult]):
        super().__init__(message)
        self.results = results


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _normalize_changed_path(path: str) -> str:
    if not isinstance(path, str) or not path or path.startswith("/"):
        raise ValueError("Invalid repository-relative changed path")
    if "\\" in path or any(ord(character) < 32 or ord(character) == 127 for character in path):
        raise ValueError("Invalid repository-relative changed path")
    parts = path.rstrip("/").split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid repository-relative changed path")
    return "/".join(parts)
