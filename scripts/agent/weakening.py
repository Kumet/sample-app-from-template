from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    file: str
    description: str
    required: bool


SKIP_RE = re.compile(r"^\+.*(?:@(?:unittest\.)?skip|pytest\.mark\.skip|\.skip\(|xdescribe\(|xit\()", re.I)
ASSERT_RE = re.compile(r"^-.*(?:assert|expect\(|should\.)", re.I)
COVERAGE_RE = re.compile(r"^[+-].*(?:coverage|threshold|minimum).*[0-9]+", re.I)
CI_WEAK_RE = re.compile(r"^\+.*(?:continue-on-error:\s*true|if:\s*false|allow_failure:\s*true)", re.I)


def inspect_patch(patch: str) -> list[Finding]:
    findings: list[Finding] = []
    current = ""
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("deleted file mode") and _is_test(current):
            findings.append(Finding("high", "test-deletion", current, "Test file deleted", True))
        elif SKIP_RE.search(line):
            findings.append(Finding("high", "test-skip", current, "Test skip/disable marker added", True))
        elif ASSERT_RE.search(line) and _is_test(current):
            findings.append(Finding("medium", "assertion-removal", current, "Assertion removed", False))
        elif COVERAGE_RE.search(line) and line.startswith("-"):
            findings.append(Finding("medium", "coverage-change", current, "Coverage threshold changed", False))
        elif CI_WEAK_RE.search(line):
            findings.append(Finding("high", "ci-weakening", current, "CI failure condition weakened", True))
    return findings


def _is_test(path: str) -> bool:
    lower = path.lower()
    return "test" in lower or lower.startswith("spec/") or "/spec/" in lower
