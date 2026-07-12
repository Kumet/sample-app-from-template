from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .parser import Task


@dataclass(frozen=True)
class CodexResult:
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float = 0
    tokens_used: int | None = None


def render_prompt(repo: Path, feature_dir: Path, task: Task, repair: str | None = None) -> str:
    template_name = "fix-validation.md" if repair else "implement-task.md"
    template = (repo / "prompts" / template_name).read_text(encoding="utf-8")
    return template.format(
        spec_path=feature_dir.relative_to(repo) / "spec.md",
        plan_path=feature_dir.relative_to(repo) / "plan.md",
        tasks_path=feature_dir.relative_to(repo) / "tasks.md",
        task_id=task.task_id,
        task_title=task.title,
        requirements=", ".join(task.requirements) or "See specification",
        validations=", ".join(task.validations),
        failure=(repair or "")[-8000:],
    )


def run(repo: Path, prompt: str) -> CodexResult:
    command = [
        "codex", "exec", "--sandbox", "workspace-write",
        "-c", 'approval_policy="never"', "--ephemeral", "--cd", str(repo), "-",
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, input=prompt, cwd=repo, text=True, capture_output=True, check=False,
            timeout=1800,
        )
    except FileNotFoundError as error:
        return CodexResult(127, "", str(error), time.monotonic() - started)
    except subprocess.TimeoutExpired as error:
        return CodexResult(124, error.stdout or "", error.stderr or "Codex timed out", time.monotonic() - started)
    from .telemetry import parse_codex_tokens
    return CodexResult(result.returncode, result.stdout, result.stderr,
                       time.monotonic() - started, parse_codex_tokens(result.stderr + result.stdout))
