from __future__ import annotations

import os
import re
import stat
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
    expected_root = repo.resolve() / ".agent-worktrees"
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("Refusing an unsafe worktree container")
    if root.resolve() != expected_root:
        raise ValueError("Refusing a worktree container outside the repository")
    if path.resolve() == repo.resolve():
        raise ValueError("Refusing to create an ownership marker at repository root")
    if path.exists():
        raise ValueError(f"Worktree path already exists: {path}")
    root.mkdir(exist_ok=True)
    git_utils.run_git(repo, ["worktree", "add", "-b", branch, str(path), base_branch])
    write_ownership_marker(repo, path, feature)
    return Worktree(path, branch)


def write_ownership_marker(repo: Path, path: Path, feature: str) -> None:
    if not is_registered_isolated(repo, path):
        raise ValueError("Refusing to mark an unregistered isolated worktree")
    marker = path / ".agent-worktree-owned"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(marker, flags, 0o600)
    except OSError as error:
        raise ValueError("Refusing to replace an existing ownership marker") from error
    try:
        os.write(descriptor, (feature + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def is_registered_isolated(repo: Path, path: Path) -> bool:
    root = repo / ".agent-worktrees"
    if (
        root.is_symlink()
        or root.resolve() != repo.resolve() / ".agent-worktrees"
        or path.is_symlink()
        or path.parent.resolve() != root.resolve()
    ):
        return False
    registered = {
        Path(line.removeprefix("worktree ")).resolve()
        for line in git_utils.run_git(
            repo, ["worktree", "list", "--porcelain"]
        ).stdout.splitlines()
        if line.startswith("worktree ")
    }
    return path.resolve() != repo.resolve() and path.resolve() in registered


def read_ownership_marker(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError("Ownership marker is not a private regular file")
        value = os.read(descriptor, 129)
        if len(value) > 128:
            raise ValueError("Ownership marker is too large")
        feature = value.decode("utf-8").strip()
        if not SAFE_RE.fullmatch(feature):
            raise ValueError("Ownership marker has an invalid feature")
        return feature
    finally:
        os.close(descriptor)


def owns_registered_worktree(repo: Path, path: Path, feature: str) -> bool:
    """Return whether a registered isolated worktree has the expected marker."""
    if not is_registered_isolated(repo, path):
        return False
    try:
        return read_ownership_marker(path / ".agent-worktree-owned") == feature
    except (OSError, UnicodeError, ValueError):
        return False


def owns_current_worktree(path: Path, feature: str) -> bool:
    """Verify that path is a framework-owned linked worktree for feature."""
    repository = current_repository_root(path)
    return repository is not None and owns_registered_worktree(
        repository, path, feature
    )


def current_repository_root(path: Path) -> Path | None:
    """Return the main repository root for a normal or linked worktree."""
    try:
        value = git_utils.run_git(path, ["rev-parse", "--git-common-dir"]).stdout.strip()
        common = Path(value)
        if not common.is_absolute():
            common = path / common
        common = common.resolve()
        if common.name != ".git":
            return None
        return common.parent
    except (OSError, RuntimeError):
        return None


def is_current_registered_isolated(path: Path) -> bool:
    """Return whether path itself is a registered managed linked worktree."""
    repository = current_repository_root(path)
    return repository is not None and is_registered_isolated(repository, path)


def remove_after_success(repo: Path, worktree: Worktree) -> None:
    marker = worktree.path / ".agent-worktree-owned"
    if not worktree.owned:
        raise ValueError("Refusing to remove a non-framework worktree")
    marker_text = read_ownership_marker(marker) + "\n"
    if git_utils.changed_paths(worktree.path):
        raise ValueError("Refusing to remove a dirty worktree")
    marker.unlink()
    try:
        git_utils.run_git(repo, ["worktree", "remove", str(worktree.path)])
    except Exception:
        if worktree.path.exists():
            marker.write_text(marker_text, encoding="utf-8")
        raise
