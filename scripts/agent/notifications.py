from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .evidence import redact


@dataclass(frozen=True)
class Notification:
    version: int
    event: str
    feature: str
    status: str
    reason: str
    head_sha: str
    url: str = ""


def payload(event: str, feature: str, status: str, reason: str, head_sha: str, url: str = "") -> Notification:
    allowed = {"human-required", "failed", "completed", "pr-created", "ci-failed", "merged"}
    if event not in allowed:
        raise ValueError("Unsupported notification event")
    return Notification(1, event, feature, status, redact(reason, 2000), head_sha, url)


def write_outbox(directory: Path, notification: Notification) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{notification.feature}-{notification.event}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(notification), indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path


def stdout_json(notification: Notification) -> str:
    return json.dumps(asdict(notification), sort_keys=True)


def github_comment(notification: Notification, repo: Path, pr_number: int, runner=subprocess.run) -> None:
    body = stdout_json(notification)
    result = runner(["gh", "pr", "comment", str(pr_number), "--body", body], cwd=repo,
                    text=True, capture_output=True, check=False, timeout=60)
    if result.returncode:
        raise RuntimeError("GitHub notification failed")
