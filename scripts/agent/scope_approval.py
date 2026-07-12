from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import replace
from pathlib import Path

from .events import EventStore
from .state import contract_digest, read_state, write_state


SAFE_GLOB = re.compile(r"^(?:\.?[A-Za-z0-9_-]+/)*(?:[A-Za-z0-9_.-]+|\*|\*\*)$")


def preview(feature_dir: Path, pattern: str, reason: str, events: EventStore) -> dict:
    _validate(pattern, reason)
    history = events.read()
    requested = any(e.kind == "scope-request" and e.result in {"FAIL", "HUMAN_REQUIRED"} and
                    e.data and e.data.get("path") == pattern for e in history)
    if not requested:
        raise ValueError("No matching human-required scope request")
    with (feature_dir / "validation.toml").open("rb") as handle:
        import tomllib
        config = tomllib.load(handle)
    forbidden = config.get("scope", {}).get("forbidden", [])
    if any(fnmatch.fnmatchcase(pattern.replace("**", "probe"), item) for item in forbidden):
        raise ValueError("Requested scope conflicts with forbidden paths")
    return {"feature": feature_dir.name, "path": pattern, "reason": reason,
            "files": ["spec.md", "validation.toml", "state.json", "events.jsonl"]}


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
        write_state(state_path, replace(state, contract_digest=contract_digest(feature_dir)))
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
