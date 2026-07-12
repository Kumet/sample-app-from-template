from __future__ import annotations

import tomllib
from pathlib import Path


def preview(feature_dir: Path, allowed_targets: set[str]) -> dict:
    path = feature_dir / "validation.toml"
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    if raw.get("version") != 1:
        raise ValueError("Only version 1 contracts can be migrated")
    converted = {}
    blocked = {}
    for name, command in raw.get("commands", {}).items():
        if (isinstance(command, list) and len(command) == 2 and command[0] == "make"
                and command[1] in allowed_targets):
            converted[name] = command[1]
        else:
            blocked[name] = command
    return {"feature": feature_dir.name, "converted": converted, "blocked": blocked,
            "safe": not blocked}


def render_v2(feature_dir: Path, allowed_targets: set[str]) -> str:
    report = preview(feature_dir, allowed_targets)
    if not report["safe"]:
        raise ValueError("Unknown executables require human migration: " + ", ".join(report["blocked"]))
    with (feature_dir / "validation.toml").open("rb") as handle:
        raw = tomllib.load(handle)
    lines = ["version = 2", 'risk = "medium"', "auto_merge = false",
             "risk_domains = []", f"max_tasks = {raw['max_tasks']}",
             f"max_attempts_per_task = {raw['max_attempts_per_task']}",
             f"max_final_validation_attempts = {raw['max_final_validation_attempts']}",
             "max_review_attempts = 3", "max_ci_attempts = 3", "", "[validations]"]
    lines.extend(f'{name} = "{target}"' for name, target in report["converted"].items())
    lines.extend(("", "[traceability]", "", "[dependencies]", "", "[scope]",
                  "allowed = " + repr(raw["scope"]["allowed"]).replace("'", '"'),
                  "forbidden = " + repr(raw["scope"]["forbidden"]).replace("'", '"')))
    return "\n".join(lines) + "\n"
