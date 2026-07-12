from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .parser import ContractError, parse_tasks
from .policy import RepositoryPolicy, validation_commands


ID_RE = re.compile(r"\b((?:FR|REQ|AC)-[0-9]+)\b")
SUBJECTIVE = ("user-friendly", "intuitive", "beautiful", "自然", "使いやす", "適切")


@dataclass(frozen=True)
class LintReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


def lint_feature(feature_dir: Path, policy: RepositoryPolicy) -> LintReport:
    errors: list[str] = []
    warnings: list[str] = []
    required = ("spec.md", "plan.md", "tasks.md", "validation.toml", "validation-log.md")
    missing = [name for name in required if not (feature_dir / name).is_file()]
    if missing:
        return LintReport(("Missing artifacts: " + ", ".join(missing),), ())
    spec = (feature_dir / "spec.md").read_text(encoding="utf-8")
    if not re.search(r"## Status\s+\n+Approved|## Status\s+\n+Implemented", spec):
        errors.append("Specification status must be Approved or Implemented")
    with (feature_dir / "validation.toml").open("rb") as handle:
        raw = tomllib.load(handle)
    if raw.get("version") != 2:
        errors.append("Autonomous delivery requires validation.toml version 2")
        return LintReport(tuple(errors), tuple(warnings))
    try:
        commands = validation_commands(raw.get("validations"), policy)
        tasks = parse_tasks(feature_dir / "tasks.md", set(commands))
    except ContractError as error:
        errors.append(str(error))
        return LintReport(tuple(errors), tuple(warnings))
    task_ids = {task.task_id for task in tasks}
    requirement_ids = set(re.findall(r"^- ((?:FR|REQ)-[0-9]+):", spec, re.MULTILINE))
    acceptance_ids = set(re.findall(r"^- \[[ xX]\] (AC-[0-9]+):", spec, re.MULTILINE))
    trace = raw.get("traceability")
    if not isinstance(trace, dict) or not trace:
        errors.append("traceability table is required")
    else:
        referenced_tasks: set[str] = set()
        for requirement, links in trace.items():
            if not re.fullmatch(r"(?:FR|REQ)-[0-9]+", requirement):
                errors.append(f"Invalid traceability requirement: {requirement}")
                continue
            if not isinstance(links, list):
                errors.append(f"Traceability links must be an array: {requirement}")
                continue
            acs = [v for v in links if isinstance(v, str) and v.startswith("AC-")]
            linked_tasks = [v for v in links if isinstance(v, str) and v.startswith("T")]
            if not acs or not linked_tasks:
                errors.append(f"{requirement} must map to acceptance criteria and tasks")
            unknown_acs = sorted(set(acs) - acceptance_ids)
            if unknown_acs:
                errors.append(f"{requirement} references unknown acceptance criteria: {', '.join(unknown_acs)}")
            referenced_tasks.update(linked_tasks)
        missing_requirements = sorted(requirement_ids - set(trace))
        if missing_requirements:
            errors.append("Requirements missing traceability: " + ", ".join(missing_requirements))
        missing_tasks = sorted(task_ids - referenced_tasks)
        if missing_tasks:
            errors.append("Tasks missing traceability: " + ", ".join(missing_tasks))
    dependencies = raw.get("dependencies", {})
    if not isinstance(dependencies, dict):
        errors.append("dependencies must be a table")
    else:
        graph: dict[str, list[str]] = {}
        for task_id, values in dependencies.items():
            if task_id not in task_ids or not isinstance(values, list) or not all(v in task_ids for v in values):
                errors.append(f"Invalid dependencies for {task_id}")
            else:
                graph[task_id] = values
        if _has_cycle(graph):
            errors.append("Task dependencies contain a cycle")
    for line in spec.splitlines():
        if line.lstrip().startswith("- [ ]") and any(word in line.lower() for word in SUBJECTIVE):
            warnings.append("Subjective acceptance criterion: " + line.strip())
    if len(tasks) > min(policy.max_tasks, int(raw.get("max_tasks", policy.max_tasks))):
        errors.append("Task count exceeds configured limit")
    return LintReport(tuple(errors), tuple(warnings))


def require_lint(feature_dir: Path, policy: RepositoryPolicy) -> LintReport:
    report = lint_feature(feature_dir, policy)
    if not report.passed:
        raise ContractError("Spec lint failed: " + "; ".join(report.errors))
    return report


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(child) for child in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False
    return any(visit(node) for node in graph)
