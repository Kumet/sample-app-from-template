from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .ci_tracking import WorkflowRun, require_log_sha, select_run


Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PullRequest:
    number: int
    url: str
    state: str


def default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=300)


class GitHubDelivery:
    def __init__(self, repo: Path, runner: Runner = default_runner, default_branch: str = "main"):
        self.repo = repo
        self.runner = runner
        self.default_branch = default_branch

    def ensure_tools(self) -> None:
        self._run(["gh", "auth", "status"])

    def push(self, branch: str) -> None:
        if branch in {"main", "master", self.default_branch}:
            raise ValueError("Direct default-branch push is forbidden")
        self._run(["git", "push", "-u", "origin", branch])

    def find_pr(self, branch: str) -> PullRequest | None:
        result = self.runner(["gh", "pr", "list", "--head", branch, "--state", "open",
                              "--json", "number,url,state", "--limit", "1"], self.repo)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        values = json.loads(result.stdout or "[]")
        return PullRequest(**values[0]) if values else None

    def ensure_pr(self, branch: str, title: str, body_file: Path) -> PullRequest:
        existing = self.find_pr(branch)
        if existing:
            self._run(["gh", "pr", "edit", str(existing.number), "--title", title, "--body-file", str(body_file)])
            return existing
        result = self._run(["gh", "pr", "create", "--base", self.default_branch, "--head", branch,
                            "--title", title, "--body-file", str(body_file)])
        url = result.stdout.strip()
        number = int(url.rstrip("/").split("/")[-1])
        return PullRequest(number, url, "OPEN")

    def checks(self, number: int) -> bool:
        return self.check_state(number) == "passed"

    def check_state(self, number: int) -> str:
        result = self.runner(["gh", "pr", "checks", str(number), "--json", "state"], self.repo)
        try:
            values = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            if result.returncode:
                return "failed"
            raise
        states = {str(v.get("state", "")).upper() for v in values}
        if not states:
            return "pending"
        if states <= {"SUCCESS", "SKIPPED"}:
            return "passed"
        if states & {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING"}:
            return "pending"
        return "failed"

    def failed_logs(self, number: int) -> str:
        return self.failed_logs_for_sha(self.pr_head_sha(number))

    def pr_head_sha(self, number: int) -> str:
        result = self._run(["gh", "pr", "view", str(number), "--json", "headRefOid"])
        value = json.loads(result.stdout)
        sha = value.get("headRefOid")
        if not isinstance(sha, str) or not sha:
            raise RuntimeError("PR head SHA is unavailable")
        return sha

    def workflow_run_for_sha(self, head_sha: str) -> WorkflowRun:
        result = self._run(["gh", "run", "list", "--commit", head_sha,
                            "--json", "databaseId,headSha,status,conclusion", "--limit", "20"])
        raw = json.loads(result.stdout or "[]")
        runs = [WorkflowRun(int(item["databaseId"]), item["headSha"], item["status"], item.get("conclusion"))
                for item in raw]
        return select_run(runs, head_sha)

    def failed_logs_for_sha(self, head_sha: str) -> str:
        run = self.workflow_run_for_sha(head_sha)
        require_log_sha(run, head_sha)
        result = self._run(["gh", "run", "view", str(run.run_id), "--log-failed"])
        return (result.stdout + result.stderr)[-12000:]

    def merge(self, number: int) -> None:
        self._run(["gh", "pr", "merge", str(number), "--merge", "--delete-branch"])

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        result = self.runner(command, self.repo)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "Command failed: " + " ".join(command[:3]))
        return result


def checks_with_repairs(github: GitHubDelivery, number: int, repair, max_attempts: int,
                        sleep=time.sleep, max_polls: int = 60) -> bool:
    previous = None
    limit = max(1, min(max_attempts, 5))
    for attempt in range(1, limit + 1):
        state = github.check_state(number)
        polls = 0
        while state == "pending" and polls < max_polls:
            sleep(5)
            polls += 1
            state = github.check_state(number)
        if state == "passed":
            return True
        if state == "pending":
            raise RuntimeError("CI check monitoring timed out")
        failure = github.failed_logs(number)
        signature = failure[-4000:]
        if signature == previous:
            raise RuntimeError("CI repeated an identical failure")
        previous = signature
        if attempt < limit:
            repair(failure)
    return False
