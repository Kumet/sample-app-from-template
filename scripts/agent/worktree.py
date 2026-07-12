from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import git_utils


SAFE_RE = re.compile(r"^[0-9]{3,}-[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    owned: bool = True


def create(repo: Path, feature: str, base_branch: str) -> Worktree:
    if not SAFE_RE.fullmatch(feature):
        raise ValueError("Unsafe worktree feature identifier")
    root = repo / ".agent-worktrees"
    path = root / feature
    branch = f"agent/{feature}"
    if path.exists():
        raise ValueError(f"Worktree path already exists: {path}")
    root.mkdir(exist_ok=True)
    git_utils.run_git(repo, ["worktree", "add", "-b", branch, str(path), base_branch])
    marker = path / ".agent-worktree-owned"
    marker.write_text(feature + "\n", encoding="utf-8")
    return Worktree(path, branch)


def remove_after_success(repo: Path, worktree: Worktree) -> None:
    marker = worktree.path / ".agent-worktree-owned"
    if not worktree.owned or not marker.is_file():
        raise ValueError("Refusing to remove a non-framework worktree")
    if git_utils.changed_paths(worktree.path):
        raise ValueError("Refusing to remove a dirty worktree")
    marker_text = marker.read_text(encoding="utf-8")
    marker.unlink()
    try:
        git_utils.run_git(repo, ["worktree", "remove", str(worktree.path)])
    except Exception:
        if worktree.path.exists():
            marker.write_text(marker_text, encoding="utf-8")
        raise
