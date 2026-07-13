from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import replace
from pathlib import Path

from . import git_utils
from .events import EventStore
from .state import contract_digest, read_state, write_state


SAFE_GLOB = re.compile(r"^(?:\.?[A-Za-z0-9_-]+/)*(?:[A-Za-z0-9_.-]+|\*|\*\*)$")


def preview(feature_dir: Path, pattern: str, reason: str, events: EventStore) -> dict:
    _validate(pattern, reason)
    history = events.read()
    requested = _pending_request(history, feature_dir.name, pattern)
    if not requested:
        raise ValueError("No matching human-required scope request")
    _check_forbidden(feature_dir, pattern)
    return {"feature": feature_dir.name, "path": pattern, "reason": reason,
            "files": ["spec.md", "validation.toml", "state.json", "events.jsonl"]}


def preview_request(feature_dir: Path, pattern: str, reason: str, events: EventStore,
                    state_path: Path) -> dict:
    _validate(pattern, reason)
    _check_forbidden(feature_dir, pattern)
    state = _request_state(feature_dir, state_path)
    history = events.read()
    if _pending_request(history, feature_dir.name, pattern):
        raise ValueError("Matching human-required scope request already exists")
    return {
        "feature": feature_dir.name,
        "path": pattern,
        "reason": reason,
        "state": {
            "status": state.status,
            "failure_class": state.failure_class,
            "task": state.task,
            "head_sha": state.head_commit,
            "updated_at": state.updated_at,
        },
        "mutation": "append scope-request event",
    }


def request(feature_dir: Path, pattern: str, reason: str, events: EventStore,
            state_path: Path) -> dict:
    result = preview_request(feature_dir, pattern, reason, events, state_path)
    state = read_state(state_path)
    events.append(
        feature=feature_dir.name,
        repository=str(state_path.parents[2]),
        branch=state.branch,
        worktree=state.worktree,
        phase="approval",
        kind="scope-request",
        result="HUMAN_REQUIRED",
        head_sha=state.head_commit,
        detail=reason,
        data={
            "paths": [pattern],
            "task": state.task,
            "state_updated_at": state.updated_at,
        },
    )
    return result


def apply(feature_dir: Path, pattern: str, reason: str, events: EventStore,
          state_path: Path | None = None) -> dict:
    result = preview(feature_dir, pattern, reason, events)
    spec_path = feature_dir / "spec.md"
    spec = spec_path.read_text(encoding="utf-8")
    marker = "### Forbidden changes"
    if marker not in spec:
        raise ValueError("Specification scope section is malformed")
    if f"- `{pattern}`" not in spec:
        spec = spec.replace(marker, f"- `{pattern}`\n\n{marker}")
        spec_path.write_text(spec, encoding="utf-8")
    toml_path = feature_dir / "validation.toml"
    text = toml_path.read_text(encoding="utf-8")
    allowed_match = re.search(r"allowed\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not allowed_match:
        raise ValueError("validation.toml scope.allowed is malformed")
    if f'"{pattern}"' not in allowed_match.group(1):
        content = allowed_match.group(1).rstrip()
        separator = "," if content.strip() else ""
        replacement = f"allowed=[{content}{separator}\"{pattern}\"]"
        text = text[:allowed_match.start()] + replacement + text[allowed_match.end():]
        toml_path.write_text(text, encoding="utf-8")
    if state_path and state_path.exists():
        state = read_state(state_path)
        digest_dir = feature_dir
        changed_paths = state.changed_paths
        worktree = Path(state.worktree)
        worktree_feature = worktree / "specs" / feature_dir.name
        if worktree.resolve() != feature_dir.parents[1].resolve() and worktree_feature.is_dir():
            for name in ("spec.md", "validation.toml"):
                (worktree_feature / name).write_text(
                    (feature_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
                )
            digest_dir = worktree_feature
            changed_paths = tuple(git_utils.changed_paths(worktree))
        write_state(state_path, replace(
            state,
            contract_digest=contract_digest(digest_dir),
            changed_paths=changed_paths,
        ))
    events.append(feature=feature_dir.name, repository="", branch="", worktree="",
                  phase="approval", kind="scope-approved", result="PASS", head_sha="",
                  detail=reason, data={"path": pattern})
    return result


def _validate(pattern: str, reason: str) -> None:
    if not SAFE_GLOB.fullmatch(pattern) or pattern.startswith("/") or ".." in pattern:
        raise ValueError("Unsafe scope glob")
    if pattern in {"**", "*"}:
        raise ValueError("Repository-wide scope expansion is forbidden")
    if not reason.strip():
        raise ValueError("Approval reason is required")


def _event_paths(event) -> tuple[str, ...]:
    if not event.data:
        return ()
    raw_paths = event.data.get("paths")
    if isinstance(raw_paths, list):
        candidates = raw_paths
    elif isinstance(event.data.get("path"), str):
        candidates = [event.data["path"]]
    else:
        return ()
    valid = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        try:
            _validate(candidate, "event path validation")
        except ValueError:
            continue
        valid.append(candidate)
    return tuple(valid)


def _pending_request(history, feature: str, pattern: str) -> bool:
    last_request = max(
        (event.sequence for event in history
         if event.feature == feature and event.kind == "scope-request"
         and event.result in {"FAIL", "HUMAN_REQUIRED"} and pattern in _event_paths(event)),
        default=0,
    )
    last_approval = max(
        (event.sequence for event in history
         if event.feature == feature and event.kind == "scope-approved"
         and event.result == "PASS" and pattern in _event_paths(event)),
        default=0,
    )
    return last_request > last_approval


def _request_state(feature_dir: Path, state_path: Path):
    if not state_path.is_file():
        raise ValueError("Scope request requires an existing failed state")
    state = read_state(state_path)
    if state.feature != feature_dir.name:
        raise ValueError("Scope request state belongs to another feature")
    if state.status != "failed" or state.failure_class != "scope":
        raise ValueError("Scope request requires the current failed scope state")
    return state


def _check_forbidden(feature_dir: Path, pattern: str) -> None:
    with (feature_dir / "validation.toml").open("rb") as handle:
        import tomllib
        config = tomllib.load(handle)
    forbidden = config.get("scope", {}).get("forbidden", [])
    probe = pattern.replace("**", "probe").replace("*", "probe")
    if any(fnmatch.fnmatchcase(probe, item) or fnmatch.fnmatchcase(pattern, item)
           for item in forbidden):
        raise ValueError("Requested scope conflicts with forbidden paths")
