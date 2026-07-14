from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class RunState:
    version: int
    feature: str
    branch: str
    base_commit: str
    head_commit: str
    contract_digest: str
    task: str | None
    attempt: int
    phase: str
    failure_class: str | None
    changed_paths: tuple[str, ...]
    status: str
    worktree: str
    updated_at: str
    recovery_event_sequence: int | None = None
    recovery_diff_digest: str | None = None


def contract_digest(feature_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("spec.md", "plan.md", "tasks.md", "validation.toml"):
        digest.update(name.encode())
        digest.update((feature_dir / name).read_bytes())
    return digest.hexdigest()


def write_state(path: Path, state: RunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_state(path: Path) -> RunState:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["changed_paths"] = tuple(raw["changed_paths"])
    state = RunState(**raw)
    if state.version != 1:
        raise ValueError("Unsupported state version")
    if state.recovery_event_sequence is not None and (
        isinstance(state.recovery_event_sequence, bool)
        or not isinstance(state.recovery_event_sequence, int)
        or state.recovery_event_sequence < 1
    ):
        raise ValueError("Invalid recovery event sequence")
    if state.recovery_diff_digest is not None and not re.fullmatch(
        r"[0-9a-f]{64}", state.recovery_diff_digest
    ):
        raise ValueError("Invalid recovery diff digest")
    return state


def abort(path: Path, updated_at: str) -> RunState:
    state = read_state(path)
    state = replace(state, status="aborted", phase="aborted", updated_at=updated_at)
    write_state(path, state)
    return state


def verify_resume(state: RunState, branch: str, head: str, digest: str, paths: list[str]) -> None:
    mismatches = []
    if state.status not in {"running", "failed"}:
        mismatches.append(f"state is {state.status}")
    if state.branch != branch:
        mismatches.append("branch changed")
    if state.head_commit != head:
        mismatches.append("HEAD changed")
    if state.contract_digest != digest:
        mismatches.append("feature contract changed")
    if tuple(sorted(paths)) != tuple(sorted(state.changed_paths)):
        mismatches.append("changed paths differ")
    if mismatches:
        raise ValueError("Cannot resume: " + ", ".join(mismatches))
