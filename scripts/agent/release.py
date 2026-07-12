from __future__ import annotations

import re
from pathlib import Path

from . import git_utils


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def check(repo: Path, *, require_main: bool = True, require_clean: bool = True) -> list[str]:
    errors = []
    version = (repo / "VERSION").read_text(encoding="utf-8").strip() if (repo / "VERSION").is_file() else ""
    if not VERSION_RE.fullmatch(version):
        errors.append("VERSION is not semantic version")
    if version and version not in (repo / "CHANGELOG.md").read_text(encoding="utf-8"):
        errors.append("CHANGELOG does not contain VERSION")
    for path in ("docs/migration-v1.md", "docs/compatibility.md", "docs/release-checklist.md"):
        if not (repo / path).is_file():
            errors.append(f"Missing release artifact: {path}")
    if require_main and git_utils.branch(repo) != "main":
        errors.append("Release check requires main branch")
    if require_clean and git_utils.changed_paths(repo):
        errors.append("Release check requires clean worktree")
    if require_main:
        local = git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
        remote = git_utils.run_git(repo, ["rev-parse", "origin/main"], check=False)
        if remote.returncode or remote.stdout.strip() != local:
            errors.append("main is not synchronized with origin/main")
    return errors
