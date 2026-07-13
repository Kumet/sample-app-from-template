from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_git(
    repo: Path, args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if check and result.returncode:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def branch(repo: Path) -> str:
    return run_git(repo, ["branch", "--show-current"]).stdout.strip()


@dataclass(frozen=True)
class SafeStartInspection:
    safe: bool
    branch: str
    detached: bool
    dirty: bool
    dirty_tracked: bool
    dirty_untracked: bool
    unmerged: bool
    operations: tuple[str, ...]
    blocking_reasons: tuple[str, ...]


def inspect_safe_start(
    repo: Path,
    default_branch: str | None = None,
    *,
    allow_ownership_marker: bool = False,
) -> SafeStartInspection:
    current = branch(repo)
    detached = not current
    records = _status_records(
        repo,
        optional_locks=False,
        include_runtime=True,
        allow_ownership_marker=allow_ownership_marker,
    )
    dirty_tracked = any(code != "??" for code, _ in records)
    dirty_untracked = any(code == "??" for code, _ in records)
    unmerged = any("U" in code or code in {"AA", "DD"} for code, _ in records)
    operations = tuple(
        name
        for name, marker in (
            ("merge", "MERGE_HEAD"),
            ("rebase", "rebase-merge"),
            ("rebase", "rebase-apply"),
            ("cherry-pick", "CHERRY_PICK_HEAD"),
        )
        if _git_path(repo, marker).exists()
    )
    operations = tuple(dict.fromkeys(operations))
    protected = {"main", "master"}
    if default_branch:
        protected.add(default_branch)
    reasons = []
    if detached:
        reasons.append("delivery cannot start from detached HEAD")
    elif current in protected:
        reasons.append(f"delivery cannot start from protected branch: {current}")
    if dirty_tracked:
        reasons.append("root repository has dirty tracked files")
    if dirty_untracked:
        reasons.append("root repository has dirty untracked files")
    if unmerged:
        reasons.append("root repository has unmerged paths")
    if operations:
        reasons.append("root repository has an in-progress " + "/".join(operations))
    return SafeStartInspection(
        not reasons,
        current,
        detached,
        dirty_tracked or dirty_untracked,
        dirty_tracked,
        dirty_untracked,
        unmerged,
        operations,
        tuple(reasons),
    )


def ensure_safe_start(
    repo: Path,
    default_branch: str | None = None,
    *,
    allow_ownership_marker: bool = False,
) -> None:
    inspection = inspect_safe_start(
        repo,
        default_branch,
        allow_ownership_marker=allow_ownership_marker,
    )
    if not inspection.safe:
        raise GitError("; ".join(inspection.blocking_reasons))


def changed_paths(repo: Path) -> list[str]:
    return [
        path
        for _, path in _status_records(repo, optional_locks=True, include_runtime=False)
    ]


def changed_paths_read_only(repo: Path) -> list[str]:
    return [
        path
        for _, path in _status_records(
            repo, optional_locks=False, include_runtime=False
        )
    ]


def cleanliness_paths_read_only(
    repo: Path, *, allow_ownership_marker: bool = False
) -> list[str]:
    """Return every dirty path without refreshing the index.

    Runtime paths are included. The ownership marker is excluded only when the
    caller has already verified framework ownership of this linked worktree.
    """
    return [
        path
        for _, path in _status_records(
            repo,
            optional_locks=False,
            include_runtime=True,
            allow_ownership_marker=allow_ownership_marker,
        )
    ]


def _status_records(
    repo: Path,
    *,
    optional_locks: bool,
    include_runtime: bool,
    allow_ownership_marker: bool = False,
) -> list[tuple[str, str]]:
    env = dict(os.environ)
    if not optional_locks:
        env["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise GitError(result.stderr.strip() or "git status failed")
    entries = result.stdout.split("\0")
    records = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        code = entry[:2]
        path = entry[3:]
        if code in {"R ", "C ", "RM", "CM"} and index < len(entries):
            path = entries[index]
            index += 1
        if path and path == ".agent-worktree-owned":
            if allow_ownership_marker or not include_runtime:
                continue
        if path and (include_runtime or not path.startswith(".agent-work/")):
            records.append((code, path))
    return sorted(set(records), key=lambda value: value[1])


def _git_path(repo: Path, name: str) -> Path:
    value = run_git(repo, ["rev-parse", "--git-path", name]).stdout.strip()
    path = Path(value)
    return path if path.is_absolute() else repo / path


def diff_check(repo: Path) -> None:
    result = run_git(repo, ["diff", "--check"], check=False)
    if result.returncode:
        raise GitError(result.stdout.strip() or result.stderr.strip())


def commit(repo: Path, paths: list[str], message: str) -> str:
    if not paths:
        raise GitError("Refusing to create an empty commit")
    run_git(repo, ["add", "--", *paths])
    run_git(repo, ["commit", "-m", message, "--", *paths])
    return run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
