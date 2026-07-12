from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def run(repo: Path, quality: dict[str, dict] | None = None) -> list[Check]:
    checks = []
    for tool in ("python3", "git", "make", "codex", "gh"):
        checks.append(Check(tool, "PASS" if shutil.which(tool) else "FAIL",
                            "available" if shutil.which(tool) else "not found"))
    checks.extend((
        _command("git-repository", ["git", "rev-parse", "--git-dir"], repo),
        _command("codex-auth", ["codex", "login", "status"], repo, redact_output=True),
        _command("github-auth", ["gh", "auth", "status"], repo, redact_output=True),
        Check("policy", "PASS" if (repo / ".agent-policy.toml").is_file() else "FAIL", ".agent-policy.toml"),
        Check("ci", "PASS" if (repo / ".github/workflows/ci.yml").is_file() else "FAIL", "workflow"),
        Check("secret-check", "PASS" if (repo / "scripts/check-secrets.sh").is_file() else "FAIL", "script"),
    ))
    for gate, setting in sorted((quality or {}).items()):
        enabled = setting.get("enabled") is True
        reason = setting.get("reason", "")
        if enabled:
            status, detail = "PASS", "enabled"
        elif reason:
            status, detail = "NOT_APPLICABLE", reason
        else:
            status, detail = "FAIL", "disabled without reason"
        checks.append(Check(f"quality:{gate}", status, detail))
    return checks


def readiness(checks: list[Check], auto_merge_enabled: bool = False) -> dict[str, bool]:
    hard_fail = any(check.status == "FAIL" for check in checks)
    names = {check.name: check.status for check in checks}
    return {"local_work": not hard_fail,
            "medium_delivery": not hard_fail and names.get("github-auth") == "PASS",
            "low_risk_auto_merge": not hard_fail and names.get("github-auth") == "PASS" and auto_merge_enabled}


def _command(name: str, command: list[str], repo: Path, redact_output: bool = False) -> Check:
    try:
        result = subprocess.run(command, cwd=repo, text=True, capture_output=True,
                                check=False, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return Check(name, "FAIL", "unavailable")
    detail = "authenticated" if redact_output and result.returncode == 0 else (
        "not authenticated" if redact_output else (result.stdout or result.stderr)[-500:])
    return Check(name, "PASS" if result.returncode == 0 else "FAIL", detail.strip())
