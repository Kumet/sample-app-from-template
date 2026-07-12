from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowRun:
    run_id: int
    head_sha: str
    status: str
    conclusion: str | None


def select_run(runs: list[WorkflowRun], pr_head_sha: str) -> WorkflowRun:
    matches = [run for run in runs if run.head_sha == pr_head_sha]
    if not matches:
        raise ValueError("No workflow run belongs to PR HEAD")
    return max(matches, key=lambda run: run.run_id)


def normalize_status(run: WorkflowRun) -> str:
    if run.status in {"queued", "in_progress", "waiting", "pending"}:
        return "pending"
    conclusion = (run.conclusion or "").lower()
    if conclusion in {"success", "skipped"}:
        return "passed"
    if conclusion in {"cancelled", "timed_out", "failure", "action_required"}:
        return conclusion
    return "unknown"


def require_log_sha(run: WorkflowRun, expected_sha: str) -> None:
    if run.head_sha != expected_sha:
        raise ValueError("Refusing logs from unrelated workflow SHA")
