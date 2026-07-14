import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent.policy import RepositoryPolicy
from agent.spec_lint import lint_feature


POLICY = RepositoryPolicy("main", frozenset({"test", "validate"}), 20, 3, 3, 3, 120,
                          False, (), ())
CONTAINER_POLICY = RepositoryPolicy(
    "main",
    frozenset({"test", "validate", "container-build", "container-smoke"}),
    20,
    3,
    3,
    3,
    120,
    False,
    (),
    (),
)


class SpecLintTests(unittest.TestCase):
    def feature(
        self,
        root: Path,
        *,
        cycle=False,
        trace=True,
        validations='unit="test"\nfull="validate"\n',
    ) -> Path:
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
            '[validations]\n' + validations + '[traceability]\n' + trace_text +
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

    def test_version_two_contract_accepts_explicit_container_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            feature = self.feature(
                Path(directory),
                validations=(
                    'unit="test"\n'
                    'container-build="container-build"\n'
                    'container-smoke="container-smoke"\n'
                    'full="validate"\n'
                ),
            )
            self.assertTrue(lint_feature(feature, CONTAINER_POLICY).passed)

    def test_contract_without_container_targets_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            feature = self.feature(Path(directory))
            self.assertTrue(lint_feature(feature, CONTAINER_POLICY).passed)

    def test_spec_lint_rejects_non_exact_container_target(self):
        rejected = (
            "container-build-extra",
            "Container-Build",
            "container-build; command",
        )
        for target in rejected:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                feature = self.feature(
                    Path(directory),
                    validations=f'unit="test"\ncontainer="{target}"\nfull="validate"\n',
                )
                report = lint_feature(feature, CONTAINER_POLICY)
                self.assertFalse(report.passed)
                self.assertTrue(
                    any(
                        "not allowlisted" in error or "Invalid Make target" in error
                        for error in report.errors
                    )
                )
