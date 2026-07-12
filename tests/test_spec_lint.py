import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent.policy import RepositoryPolicy
from agent.spec_lint import lint_feature


POLICY = RepositoryPolicy("main", frozenset({"test", "validate"}), 20, 3, 3, 3, 120,
                          False, (), ())


class SpecLintTests(unittest.TestCase):
    def feature(self, root: Path, *, cycle=False, trace=True) -> Path:
        feature = root / "specs" / "012-test"
        feature.mkdir(parents=True)
        (feature / "spec.md").write_text(
            "# Feature\n\n## Status\n\nApproved\n\n## Requirements\n\n- FR-101: behavior\n"
            "\n## Acceptance criteria\n\n- [ ] AC-101: verifiable\n", encoding="utf-8")
        (feature / "plan.md").write_text("# Plan\n", encoding="utf-8")
        (feature / "validation-log.md").write_text("# Log\n", encoding="utf-8")
        (feature / "tasks.md").write_text(
            "- [ ] T101: implement\n  - Requirements: FR-101\n  - Validation: unit\n"
            + ("- [ ] T102: second\n  - Requirements: FR-101\n  - Validation: unit\n" if cycle else ""),
            encoding="utf-8")
        trace_text = 'FR-101=["AC-101","T101"]\n' if trace else ""
        deps = 'T101=["T102"]\nT102=["T101"]\n' if cycle else ""
        (feature / "validation.toml").write_text(
            'version=2\nrisk="low"\nauto_merge=false\nmax_tasks=20\nmax_attempts_per_task=3\n'
            'max_final_validation_attempts=3\nmax_review_attempts=3\nmax_ci_attempts=3\n'
            '[validations]\nunit="test"\nfull="validate"\n[traceability]\n' + trace_text +
            '[dependencies]\n' + deps + '[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
            encoding="utf-8")
        return feature

    def test_valid_contract_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(lint_feature(self.feature(Path(directory)), POLICY).passed)

    def test_missing_traceability_and_cycle_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            report = lint_feature(self.feature(Path(directory), cycle=True, trace=False), POLICY)
            self.assertFalse(report.passed)
            self.assertTrue(any("cycle" in error for error in report.errors))
            self.assertTrue(any("traceability" in error.lower() for error in report.errors))
