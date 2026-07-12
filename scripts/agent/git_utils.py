from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def run_git(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if check and result.returncode:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result


def branch(repo: Path) -> str:
    return run_git(repo, ["branch", "--show-current"]).stdout.strip()


def ensure_safe_start(repo: Path) -> None:
    current = branch(repo)
    if current in {"main", "master"} or not current:
        raise GitError(f"Work is forbidden on branch {current or '<detached>'}")
    if changed_paths(repo):
        raise GitError("Worktree must be clean before work starts")


def changed_paths(repo: Path) -> list[str]:
    output = run_git(repo, ["status", "--porcelain=v1", "-z"]).stdout
    paths: list[str] = []
    entries = output.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        path = entry[3:]
        if entry[:2] in {"R ", "C ", "RM", "CM"} and index < len(entries):
            path = entries[index]
            index += 1
        if path and not path.startswith(".agent-work/") and path != ".agent-worktree-owned":
            paths.append(path)
    return sorted(set(paths))


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
