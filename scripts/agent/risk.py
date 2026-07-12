from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .policy import RepositoryPolicy
from .weakening import Finding


LEVEL = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class RiskAssessment:
    declared: str
    effective: str
    reasons: tuple[str, ...]


def assess(declared: str, paths: list[str], findings: list[Finding], policy: RepositoryPolicy,
           domains: tuple[str, ...] = ()) -> RiskAssessment:
    if declared not in LEVEL:
        raise ValueError("risk must be low, medium, or high")
    effective = declared
    reasons = [f"declared:{declared}"]
    high_domains = {"authentication", "authorization", "billing", "migration", "deployment",
                    "security", "production", "personal-data"}
    medium_domains = {"ci-cd", "dependencies", "infrastructure"}
    if set(domains) & high_domains:
        effective = "high"
        reasons.append("high-risk-domain:" + ",".join(sorted(set(domains) & high_domains)))
    elif set(domains) & medium_domains and LEVEL[effective] < 1:
        effective = "medium"
        reasons.append("medium-risk-domain:" + ",".join(sorted(set(domains) & medium_domains)))
    for path in paths:
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in policy.high_risk_paths):
            effective = "high"
            reasons.append(f"high-risk-path:{path}")
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in policy.medium_risk_paths) and LEVEL[effective] < 1:
            effective = "medium"
            reasons.append(f"medium-risk-path:{path}")
    if any(f.severity == "high" for f in findings):
        effective = "high"
        reasons.append("high-review-finding")
    elif any(f.severity == "medium" for f in findings) and LEVEL[effective] < 1:
        effective = "medium"
        reasons.append("medium-review-finding")
    return RiskAssessment(declared, effective, tuple(reasons))


def merge_allowed(assessment: RiskAssessment, feature_auto_merge: bool, policy: RepositoryPolicy,
                  checks_passed: bool, review_passed: bool, weakening: list[Finding]) -> bool:
    return all((assessment.effective == "low", feature_auto_merge,
                policy.auto_merge_low_risk, checks_passed, review_passed,
                not any(f.required for f in weakening)))
