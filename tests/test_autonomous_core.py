import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unittest import mock

from agent import adapters, delivery, recovery, review, weakening
from agent.budget import Budget
from agent.events import Event, EventStore
from agent.evidence import redact
from agent.policy import RepositoryPolicy, load_policy, validation_commands
from agent.review import ReviewResult, parse_review, review_with_repairs
from agent.review_shards import (
    matching_failure_count,
    record_reuse_decision,
    reusable_event,
)
from agent.risk import assess, merge_allowed
from agent.state import RunState, abort, read_state, verify_resume, write_state

POLICY = RepositoryPolicy(
    "main",
    frozenset({"test", "validate"}),
    20,
    3,
    3,
    3,
    120,
    True,
    ("auth/**",),
    (".github/**",),
)

EVIDENCE_FIELDS = {
    "tracked_snapshot_event_sequence": 10,
    "validation_log_blob_sha": "b" * 40,
    "final_validation_attempt_event_sequence": 11,
    "final_validation_accepted_event_sequence": 12,
    "final_validation_result_digest": "f" * 64,
}


def review_evidence_fixture(contract: str, head: str, body: str = ""):
    contract_digest = hashlib.sha256(contract.encode()).hexdigest()
    metadata = {
        "feature": "test-feature",
        "event_schema_version": 1,
        "snapshot_format_version": 2,
        "included_event_sequence": 9,
        "generated_at": "2026-07-13T00:00:00+00:00",
        "validation_contract_digest": contract_digest,
    }
    validation = (
        "# Validation log\n<!-- validation-snapshot: "
        + json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        + " -->\n"
        + body
    )
    runtime = json.dumps(
        [
            {
                "sequence": 10,
                "kind": "tracked-evidence-snapshot",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "included_event_sequence": 9,
                    "log_blob_sha": EVIDENCE_FIELDS["validation_log_blob_sha"],
                    "validation_contract_digest": contract_digest,
                },
            },
            {
                "sequence": 11,
                "kind": "final-validation-attempt",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "snapshot_event_sequence": 10,
                    "exact_head_sha": head,
                    "validation_log_blob_sha": EVIDENCE_FIELDS[
                        "validation_log_blob_sha"
                    ],
                    "validation_contract_digest": contract_digest,
                    "result_digest": EVIDENCE_FIELDS[
                        "final_validation_result_digest"
                    ],
                },
            },
            {
                "sequence": 12,
                "kind": "final-validation-accepted",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "snapshot_event_sequence": 10,
                    "attempt_event_sequence": 11,
                    "exact_head_sha": head,
                    "validation_log_blob_sha": EVIDENCE_FIELDS[
                        "validation_log_blob_sha"
                    ],
                    "validation_contract_digest": contract_digest,
                    "result_digest": EVIDENCE_FIELDS[
                        "final_validation_result_digest"
                    ],
                },
            },
        ],
        separators=(",", ":"),
    )
    return validation, runtime


def review_identity(**changes):
    values = {
        "identity_schema_version": review.REVIEW_IDENTITY_SCHEMA_VERSION,
        "feature": "007-x",
        "head_sha": "abc",
        "shard": "security",
        "review_schema_version": review.REVIEW_SCHEMA_VERSION,
        "prompt_version": review.REVIEW_PROMPT_VERSION,
        "reviewer_model": review.REVIEW_MODEL,
        "reviewer_command_identity": "c" * 64,
        "review_settings": review.MODEL_SETTINGS,
        "reviewed_files": ("a.py",),
        "spec_digest": "1" * 64,
        "plan_digest": "2" * 64,
        "tasks_digest": "3" * 64,
        "validation_contract_digest": "4" * 64,
        "diff_input_digest": "5" * 64,
        "runtime_evidence_digest": "7" * 64,
        "tracked_snapshot_event_sequence": 10,
        "validation_log_blob_sha": "b" * 40,
        "final_validation_attempt_event_sequence": 11,
        "final_validation_accepted_event_sequence": 12,
        "final_validation_result_digest": "6" * 64,
    }
    values.update(changes)
    return review.ReviewIdentity(**values)


class AutonomousCoreTests(unittest.TestCase):
    def _policy_text(self, review_value="8", *, include_review=True):
        review = f"max_review_calls = {review_value}\n" if include_review else ""
        return (
            "version = 1\n"
            'default_branch = "main"\n'
            'allowed_make_targets = ["test", "validate"]\n'
            "max_tasks = 20\n"
            "max_attempts_per_task = 3\n"
            "max_review_attempts = 1\n"
            "max_ci_attempts = 2\n"
            "max_elapsed_minutes = 60\n"
            "auto_merge_low_risk = false\n"
            "allow_legacy_contracts = false\n"
            "queue_concurrency = 1\n"
            "max_codex_calls = 99\n"
            + review
            + "[risk_paths]\n"
            'high = ["auth/**"]\n'
            'medium = [".github/**"]\n'
        )

    def test_policy_loads_independent_bounded_review_call_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = repo / ".agent-policy.toml"
            for expected in (1, 8, 100):
                with self.subTest(max_review_calls=expected):
                    path.write_text(
                        self._policy_text(str(expected)), encoding="utf-8"
                    )
                    policy = load_policy(repo)
                    self.assertEqual(policy.max_review_calls, expected)
                    self.assertEqual(policy.max_review_attempts, 1)
                    self.assertEqual(policy.max_codex_calls, 99)

    def test_policy_rejects_missing_or_invalid_review_call_budget(self):
        invalid = {
            "missing": (None, False),
            "boolean-true": ("true", True),
            "boolean-false": ("false", True),
            "string": ('"8"', True),
            "zero": ("0", True),
            "negative": ("-1", True),
            "above-limit": ("101", True),
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = repo / ".agent-policy.toml"
            for label, (value, include) in invalid.items():
                with self.subTest(label=label):
                    path.write_text(
                        self._policy_text(value or "8", include_review=include),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(ValueError, "max_review_calls"):
                        load_policy(repo)

    def test_allowlist_builds_only_make_commands(self):
        self.assertEqual(
            validation_commands({"unit": "test"}, POLICY), {"unit": ("make", "test")}
        )
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            validation_commands({"bad": "deploy"}, POLICY)
        with self.assertRaises(ValueError):
            validation_commands({"bad": "test;rm"}, POLICY)

    def test_repository_policy_allows_exact_container_validation_targets(self):
        policy = load_policy(Path(__file__).resolve().parents[1])
        self.assertTrue(
            {
                "setup",
                "lint",
                "typecheck",
                "test",
                "build",
                "integration-test",
                "validate",
                "container-build",
                "container-smoke",
            }.issubset(policy.allowed_make_targets)
        )
        self.assertEqual(
            validation_commands(
                {
                    "container-build": "container-build",
                    "container-smoke": "container-smoke",
                },
                policy,
            ),
            {
                "container-build": ("make", "container-build"),
                "container-smoke": ("make", "container-smoke"),
            },
        )

    def test_container_target_allowlist_rejects_non_exact_and_unsafe_names(self):
        policy = load_policy(Path(__file__).resolve().parents[1])
        rejected = (
            "container-build-extra",
            "Container-Build",
            "container",
            "container-build; command",
            "container-build smoke",
            "container-build --flag",
        )
        for target in rejected:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    validation_commands({"container": target}, policy)

    def test_non_container_validation_commands_are_unchanged(self):
        policy = load_policy(Path(__file__).resolve().parents[1])
        mapping = {
            "setup": "setup",
            "lint": "lint",
            "typecheck": "typecheck",
            "unit": "test",
            "build": "build",
            "integration": "integration-test",
            "full": "validate",
        }
        self.assertEqual(
            validation_commands(mapping, policy),
            {name: ("make", target) for name, target in mapping.items()},
        )

    def test_ordinary_validate_target_does_not_depend_on_container_targets(self):
        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(
            encoding="utf-8"
        )
        validate_rule = next(
            line for line in makefile.splitlines() if line.startswith("validate:")
        )
        self.assertEqual(validate_rule, "validate: quality-check secrets ci")
        self.assertNotIn("container-build", validate_rule)
        self.assertNotIn("container-smoke", validate_rule)

    def test_state_round_trip_resume_and_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = RunState(
                1,
                "012-test",
                "feature/test",
                "a",
                "b",
                "digest",
                "T001",
                1,
                "validate",
                "unit-test",
                ("src/a.py",),
                "failed",
                directory,
                "now",
            )
            write_state(path, state)
            self.assertEqual(read_state(path), state)
            verify_resume(state, "feature/test", "b", "digest", ["src/a.py"])
            with self.assertRaisesRegex(ValueError, "HEAD changed"):
                verify_resume(state, "feature/test", "c", "digest", ["src/a.py"])
            self.assertEqual(abort(path, "later").status, "aborted")
            self.assertTrue(path.exists())

    def test_failure_classification_and_unsafe_policy(self):
        self.assertEqual(
            recovery.classify("unit", 1, "AssertionError: failed"), "unit-test"
        )
        self.assertEqual(
            recovery.classify("command", 127, "command not found"), "dependency"
        )
        self.assertFalse(recovery.policy_for("secret", 5).retryable)
        self.assertEqual(recovery.policy_for("timeout", 5).max_attempts, 2)

    def test_weakening_detection(self):
        patch = "+++ b/tests/test_a.py\n+@unittest.skip('later')\n-    assert value\n"
        inspection = weakening.inspect_patch(patch)
        skip_finding = next(
            f for f in inspection.blocking_findings if f.category == "test-skip"
        )
        self.assertTrue(skip_finding.required)
        self.assertTrue(
            any(
                f.category == "assertion-removal"
                for f in inspection.review_candidates
            )
        )

    def test_review_schema_validation(self):
        passed = parse_review('{"result":"pass","findings":[]}')
        self.assertEqual(passed.result, "pass")
        failed = parse_review(
            json.dumps(
                {
                    "result": "fail",
                    "findings": [
                        {
                            "severity": "high",
                            "category": "spec",
                            "file": "a.py",
                            "description": "missing behavior",
                            "required": True,
                        }
                    ],
                }
            )
        )
        self.assertEqual(len(failed.required_findings), 1)
        with self.assertRaises(ValueError):
            parse_review('{"result":"unknown","findings":[]}')

    def test_review_repairs_then_passes_and_repeated_findings_stop(self):
        finding = weakening.Finding("high", "spec", "a.py", "fix", True)
        results = iter((ReviewResult("fail", (finding,)), ReviewResult("pass", ())))
        repairs = []
        self.assertEqual(
            review_with_repairs(lambda: next(results), repairs.extend, 3).result, "pass"
        )
        self.assertEqual(len(repairs), 1)
        with self.assertRaisesRegex(RuntimeError, "identical"):
            review_with_repairs(
                lambda: ReviewResult("fail", (finding,)), lambda _: None, 3
            )
        calls = []

        def distinct_failure():
            calls.append(len(calls) + 1)
            value = weakening.Finding("high", "spec", "a.py", f"fix-{calls[-1]}", True)
            return ReviewResult("fail", (value,))

        bounded_repairs = []
        with self.assertRaisesRegex(RuntimeError, "repair limit"):
            review_with_repairs(distinct_failure, bounded_repairs.extend, 2)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(bounded_repairs), 1)

    def test_review_prompt_embeds_complete_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            feature = repo / "specs" / "012-test"
            feature.mkdir(parents=True)
            (repo / "prompts").mkdir()
            (repo / "schemas").mkdir()
            (repo / "schemas" / "review-result.schema.json").write_text(
                "{}", encoding="utf-8"
            )
            template = (
                Path(__file__).resolve().parents[1] / "prompts" / "review-feature.md"
            )
            (repo / "prompts" / "review-feature.md").write_text(
                template.read_text(encoding="utf-8"), encoding="utf-8"
            )
            for name in ("spec.md", "plan.md", "tasks.md"):
                content = f"{name}-start\n" + "a" * 13_000 + f"\n{name}-end"
                (feature / name).write_text(content, encoding="utf-8")
            contract = "version=2\n"
            validation, runtime = review_evidence_fixture(
                contract,
                "abc",
                "validation-log.md-start\n"
                + "a" * 13_000
                + "\nvalidation-log.md-end",
            )
            (feature / "validation-log.md").write_text(validation, encoding="utf-8")
            (feature / "validation.toml").write_text(contract, encoding="utf-8")
            completed = subprocess.CompletedProcess(
                [], 0, '{"result":"pass","findings":[]}', ""
            )
            merge = subprocess.CompletedProcess([], 0, "abc\n", "")
            diff_text = "diff-start\n" + "d" * 21_000 + "\ndiff-end"
            diff = subprocess.CompletedProcess([], 0, diff_text, "")
            head = subprocess.CompletedProcess([], 0, "abc\n", "")
            changed = subprocess.CompletedProcess([], 0, "src/a.py\n", "")
            with (
                mock.patch(
                    "agent.review.subprocess.run",
                    side_effect=(merge, diff, head, changed),
                ) as run,
                mock.patch(
                    "agent.review.run_process_group", return_value=completed
                ) as process_group,
            ):
                result, prompt, _ = review.run_review(
                    repo,
                    feature,
                    runtime_evidence_text=runtime,
                    evidence_fields=EVIDENCE_FIELDS,
                )
            self.assertEqual(result.result, "pass")
            for name in ("spec.md", "plan.md", "tasks.md", "validation-log.md"):
                self.assertIn(f"{name}-start", prompt)
                self.assertIn(f"{name}-end", prompt)
            self.assertIn("diff-start", prompt)
            self.assertIn("diff-end", prompt)
            self.assertIn("Do not run commands", prompt)
            self.assertIn(":(exclude)specs/012-test/**", run.call_args_list[1].args[0])
            command = process_group.call_args.args[0]
            self.assertIn(review.REVIEW_MODEL, command)
            self.assertIn('model_reasoning_effort="low"', command)
            self.assertEqual(
                process_group.call_args.args[3], review.REVIEW_TIMEOUT_SECONDS
            )

    def test_review_fails_closed_instead_of_truncating_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            feature = repo / "specs" / "012-test"
            feature.mkdir(parents=True)
            (repo / "prompts").mkdir()
            (repo / "schemas").mkdir()
            (repo / "schemas" / "review-result.schema.json").write_text(
                "{}", encoding="utf-8"
            )
            template = (
                Path(__file__).resolve().parents[1] / "prompts" / "review-feature.md"
            )
            (repo / "prompts" / "review-feature.md").write_text(
                template.read_text(encoding="utf-8"), encoding="utf-8"
            )
            for name in ("spec.md", "plan.md", "tasks.md"):
                (feature / name).write_text(name, encoding="utf-8")
            contract = "version=2\n"
            validation, runtime = review_evidence_fixture(contract, "abc")
            (feature / "validation-log.md").write_text(validation, encoding="utf-8")
            (feature / "validation.toml").write_text(contract, encoding="utf-8")
            merge = subprocess.CompletedProcess([], 0, "abc\n", "")
            oversized = "material-at-start\n" + "x" * review.MAX_REVIEW_INPUT_CHARS
            diff = subprocess.CompletedProcess([], 0, oversized, "")
            head = subprocess.CompletedProcess([], 0, "abc\n", "")
            changed = subprocess.CompletedProcess([], 0, "src/a.py\n", "")
            with (
                mock.patch(
                    "agent.review.subprocess.run",
                    side_effect=(merge, diff, head, changed),
                ) as run,
                mock.patch("agent.review.run_process_group") as process_group,
                self.assertRaisesRegex(
                    RuntimeError, "refusing to review truncated content"
                ),
            ):
                review.run_review(
                    repo,
                    feature,
                    runtime_evidence_text=runtime,
                    evidence_fields=EVIDENCE_FIELDS,
                )
            self.assertEqual(run.call_count, 4)
            process_group.assert_not_called()

    def test_empty_review_paths_preserve_fixed_inputs_and_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo, check=True
            )
            feature = repo / "specs" / "011-test"
            feature.mkdir(parents=True)
            (repo / "prompts").mkdir()
            (repo / "schemas").mkdir()
            template = (
                Path(__file__).resolve().parents[1] / "prompts" / "review-feature.md"
            )
            (repo / "prompts" / "review-feature.md").write_text(
                template.read_text(encoding="utf-8"), encoding="utf-8"
            )
            schema = (
                Path(__file__).resolve().parents[1]
                / "schemas"
                / "review-result.schema.json"
            )
            (repo / "schemas" / "review-result.schema.json").write_text(
                schema.read_text(encoding="utf-8"), encoding="utf-8"
            )
            contract = "version=2\n"
            validation, _ = review_evidence_fixture(
                contract, "pending", "VALIDATION-FIXED\n"
            )
            artifacts = {
                "spec.md": "SPEC-FIXED\n",
                "plan.md": "PLAN-FIXED\n",
                "tasks.md": "TASKS-FIXED\n",
                "validation.toml": contract,
                "validation-log.md": validation,
            }
            for name, value in artifacts.items():
                (feature / name).write_text(value, encoding="utf-8")
            (repo / "src").mkdir()
            (repo / "src" / "a.py").write_text("A-base\n", encoding="utf-8")
            (repo / "src" / "b.py").write_text("B-base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            subprocess.run(
                ["git", "switch", "-qc", "feature/011-test"], cwd=repo, check=True
            )
            (repo / "src" / "a.py").write_text("A-change\n", encoding="utf-8")
            (repo / "src" / "b.py").write_text("B-change\n", encoding="utf-8")
            subprocess.run(["git", "add", "src"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "change"], cwd=repo, check=True)

            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()
            _, runtime = review_evidence_fixture(contract, head)
            with mock.patch(
                "agent.review.subprocess.run", wraps=subprocess.run
            ) as git_run:
                empty = review.prepare_review(
                    repo,
                    feature,
                    "security [1/1]",
                    (),
                    runtime,
                    EVIDENCE_FIELDS,
                )
            diff_commands = [
                call.args[0]
                for call in git_run.call_args_list
                if call.args and call.args[0][:2] == ["git", "diff"]
            ]
            self.assertEqual(len(diff_commands), 1)
            self.assertEqual(diff_commands[0][2], "--name-only")
            self.assertNotIn("--", diff_commands[0])
            self.assertNotIn("--no-ext-diff", diff_commands[0])
            self.assertIn("<git-diff>\n\n</git-diff>", empty.prompt)
            self.assertIn("<evidence-semantics>", empty.prompt)
            self.assertIn(
                '"post_watermark_absence_from_log_is_stale":false', empty.prompt
            )
            self.assertNotIn("A-change", empty.prompt)
            self.assertNotIn("B-change", empty.prompt)
            for marker in (*artifacts.values(), runtime):
                self.assertIn(marker.strip(), empty.prompt)
            fixed_files = {
                f"specs/011-test/{name}" for name in artifacts
            } | {"prompts/review-feature.md", "schemas/review-result.schema.json"}
            self.assertEqual(set(empty.identity.reviewed_files), fixed_files)

            focused = review.prepare_reviews(
                repo,
                feature,
                "security",
                runtime,
                EVIDENCE_FIELDS,
            )
            self.assertEqual(len(focused), 1)
            self.assertIn("<git-diff>\n\n</git-diff>", focused[0].prompt)

            selected = review.prepare_review(
                repo,
                feature,
                review_paths=("src/a.py",),
                runtime_evidence_text=runtime,
                evidence_fields=EVIDENCE_FIELDS,
            )
            self.assertIn("A-change", selected.prompt)
            self.assertNotIn("B-change", selected.prompt)
            self.assertIn("src/a.py", selected.identity.reviewed_files)

            complete = review.prepare_review(
                repo,
                feature,
                review_paths=None,
                runtime_evidence_text=runtime,
                evidence_fields=EVIDENCE_FIELDS,
            )
            self.assertIn("A-change", complete.prompt)
            self.assertIn("B-change", complete.prompt)

            completed = subprocess.CompletedProcess(
                [], 0, '{"result":"pass","findings":[]}', ""
            )
            budget = delivery.ReviewCallBudget(1)
            with mock.patch(
                "agent.review.run_process_group", return_value=completed
            ) as process_group:
                result, _ = budget.run(lambda: review.run_prepared(repo, empty))
            self.assertEqual(result.result, "pass")
            self.assertEqual(budget.used, 1)
            process_group.assert_called_once()

            (feature / "spec.md").write_text(
                "x" * review.MAX_REVIEW_INPUT_CHARS, encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "Fixed independent review input"):
                review.prepare_reviews(
                    repo, feature, "security", runtime, EVIDENCE_FIELDS
                )

    def test_review_identity_changes_with_head_and_complete_input(self):
        identity = review_identity()
        same = review.ReviewIdentity(**identity.__dict__)
        changed_head = review.ReviewIdentity(**{**identity.__dict__, "head_sha": "def"})
        changed_input = review.ReviewIdentity(
            **{**identity.__dict__, "diff_input_digest": "input-b"}
        )
        self.assertEqual(identity.digest, same.digest)
        self.assertNotEqual(identity.digest, changed_head.digest)
        self.assertNotEqual(identity.digest, changed_input.digest)

    def test_review_evidence_semantics_bind_snapshot_and_runtime_events(self):
        contract = "version=2\n"
        contract_digest = hashlib.sha256(contract.encode()).hexdigest()
        metadata = {
            "feature": "012-test",
            "event_schema_version": 1,
            "snapshot_format_version": 2,
            "included_event_sequence": 40,
            "generated_at": "2026-07-13T00:00:00+00:00",
            "validation_contract_digest": contract_digest,
        }
        validation = (
            "# Validation log\n<!-- validation-snapshot: "
            + json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            + " -->\n"
        )
        head = "a" * 40
        blob = "b" * 40
        result_digest = "f" * 64
        fields = {
            "tracked_snapshot_event_sequence": 41,
            "validation_log_blob_sha": blob,
            "final_validation_attempt_event_sequence": 42,
            "final_validation_accepted_event_sequence": 43,
            "final_validation_result_digest": result_digest,
        }
        events = [
            {
                "sequence": 41,
                "kind": "tracked-evidence-snapshot",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "included_event_sequence": 40,
                    "log_blob_sha": blob,
                    "validation_contract_digest": contract_digest,
                },
            },
            {
                "sequence": 42,
                "kind": "final-validation-attempt",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "snapshot_event_sequence": 41,
                    "exact_head_sha": head,
                    "validation_log_blob_sha": blob,
                    "validation_contract_digest": contract_digest,
                    "result_digest": result_digest,
                },
            },
            {
                "sequence": 43,
                "kind": "final-validation-accepted",
                "result": "PASS",
                "head_sha": head,
                "data": {
                    "snapshot_event_sequence": 41,
                    "attempt_event_sequence": 42,
                    "exact_head_sha": head,
                    "validation_log_blob_sha": blob,
                    "validation_contract_digest": contract_digest,
                    "result_digest": result_digest,
                },
            },
        ]

        incomplete_lifecycles = (
            [],
            [{"sequence": 1, "kind": "weakening", "result": "PASS"}],
            events[:1],
            events[:2],
        )
        for incomplete in incomplete_lifecycles:
            with self.subTest(incomplete_events=len(incomplete)):
                with self.assertRaisesRegex(ValueError, "lifecycle is incomplete"):
                    review.render_evidence_semantics(
                        validation, contract, json.dumps(incomplete), fields, head
                    )

        # Later, non-accepted evidence must not replace the referenced lifecycle.
        events.append(
            {
                "sequence": 44,
                "kind": "final-validation-attempt",
                "result": "FAIL",
                "head_sha": head,
                "data": {},
            }
        )

        rendered = review.render_evidence_semantics(
            validation, contract, json.dumps(events), fields, head
        )
        semantics = json.loads(rendered)
        self.assertEqual(semantics["status"], "mechanically-verified")
        self.assertEqual(semantics["validation_log_watermark"], 40)
        self.assertEqual(semantics["tracked_snapshot_event_sequence"], 41)
        self.assertEqual(semantics["final_validation_attempt_event_sequence"], 42)
        self.assertEqual(semantics["final_validation_accepted_event_sequence"], 43)
        self.assertFalse(semantics["post_watermark_absence_from_log_is_stale"])

        duplicated = json.loads(json.dumps(events))
        duplicated[-1]["sequence"] = 43
        duplicated[-1]["kind"] = "final-validation-accepted"
        duplicated[-1]["result"] = "PASS"
        duplicated[-1]["data"] = dict(events[2]["data"])
        with self.assertRaisesRegex(ValueError, "sequence is duplicated"):
            review.render_evidence_semantics(
                validation, contract, json.dumps(duplicated), fields, head
            )

        mutations = {
            "watermark": (0, "included_event_sequence", 39, "snapshot watermark"),
            "blob": (0, "log_blob_sha", "0" * 40, "snapshot log blob"),
            "attempt-head": (1, "exact_head_sha", "0" * 40, "attempt exact HEAD"),
            "attempt-snapshot": (
                1,
                "snapshot_event_sequence",
                999,
                "attempt snapshot reference",
            ),
            "attempt-blob": (
                1,
                "validation_log_blob_sha",
                "0" * 40,
                "attempt log blob",
            ),
            "attempt-contract": (
                1,
                "validation_contract_digest",
                "0" * 64,
                "attempt contract digest",
            ),
            "attempt-result": (
                1,
                "result_digest",
                "0" * 64,
                "attempt result digest",
            ),
            "accepted-attempt": (
                2,
                "attempt_event_sequence",
                999,
                "accepted attempt reference",
            ),
            "accepted-snapshot": (
                2,
                "snapshot_event_sequence",
                999,
                "accepted snapshot reference",
            ),
            "accepted-head": (
                2,
                "exact_head_sha",
                "0" * 40,
                "accepted exact HEAD",
            ),
            "result": (2, "result_digest", "0" * 64, "accepted result digest"),
            "contract": (
                2,
                "validation_contract_digest",
                "0" * 64,
                "accepted contract digest",
            ),
        }
        for label, (index, key, value, expected_error) in mutations.items():
            with self.subTest(label=label):
                changed = json.loads(json.dumps(events))
                changed[index]["data"][key] = value
                with self.assertRaisesRegex(ValueError, expected_error):
                    review.render_evidence_semantics(
                        validation, contract, json.dumps(changed), fields, head
                    )

        current = review_identity()
        old_prompt = review.ReviewIdentity(
            **{**current.__dict__, "prompt_version": "2"}
        )
        self.assertNotEqual(current.digest, old_prompt.digest)

    def test_every_canonical_identity_field_invalidates_cached_pass(self):
        self.assertEqual(
            set(review.REVIEW_IDENTITY_FIELDS),
            {
                "identity_schema_version",
                "feature",
                "head_sha",
                "shard",
                "review_schema_version",
                "prompt_version",
                "reviewer_model",
                "reviewer_command_identity",
                "review_settings",
                "reviewed_files",
                "spec_digest",
                "plan_digest",
                "tasks_digest",
                "validation_contract_digest",
                "diff_input_digest",
                "runtime_evidence_digest",
                "tracked_snapshot_event_sequence",
                "validation_log_blob_sha",
                "final_validation_attempt_event_sequence",
                "final_validation_accepted_event_sequence",
                "final_validation_result_digest",
            },
        )
        identity = review_identity(reviewed_files=("b.py", "a.py"))
        event = Event(
            1,
            1,
            "now",
            "007-x",
            "repo",
            "branch",
            "worktree",
            "review",
            "review-shard",
            "PASS",
            "abc",
            data={"identity_digest": identity.digest},
        )
        self.assertIs(reusable_event([event], identity.digest), event)
        with tempfile.TemporaryDirectory() as directory:
            from agent.events import EventStore

            store = EventStore(Path(directory) / "events.jsonl")
            decision = record_reuse_decision(
                store,
                source=event,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity_digest=identity.digest,
            )
            self.assertEqual(decision.kind, "review-reused")
            self.assertEqual(decision.data["source_sequence"], event.sequence)
        for field in review.REVIEW_IDENTITY_FIELDS:
            with self.subTest(field=field):
                values = dict(identity.__dict__)
                value = values[field]
                if field == "identity_schema_version":
                    values[field] = "unknown"
                    with self.assertRaises(ValueError):
                        review.ReviewIdentity(**values)
                    continue
                if isinstance(value, int):
                    values[field] = value + 1
                elif isinstance(value, tuple):
                    values[field] = value + ("changed",)
                else:
                    values[field] = value + "-changed"
                changed = review.ReviewIdentity(**values)
                self.assertNotEqual(identity.digest, changed.digest)
                self.assertIsNone(reusable_event([event], changed.digest))

    def test_identical_failure_signature_stops_at_two(self):
        identity = review_identity()
        failure = Event(
            1,
            1,
            "now",
            "007-x",
            "repo",
            "branch",
            "worktree",
            "review",
            "review-shard",
            "INVALID",
            "abc",
            data={
                "identity_digest": identity.digest,
                "failure_signature": "same-failure",
            },
        )
        second = Event(**{**failure.__dict__, "sequence": 2})
        self.assertEqual(
            matching_failure_count([failure, second], identity, "same-failure"),
            2,
        )

    def test_non_timeout_review_failure_redacts_stderr_before_raise(self):
        prepared = review.PreparedReview(review_identity(), "prompt", ("codex", "exec"))
        completed = subprocess.CompletedProcess(
            prepared.command,
            1,
            "",
            "token=token-value password=hunter2 Authorization: Bearer bearer-value",
        )
        with (
            mock.patch("agent.review.run_process_group", return_value=completed),
            self.assertRaises(RuntimeError) as raised,
        ):
            review.run_prepared(Path.cwd(), prepared)
        message = str(raised.exception)
        for secret in ("token-value", "hunter2", "bearer-value"):
            self.assertNotIn(secret, message)

    def test_identity_payload_validation_and_file_order_are_fail_closed(self):
        identity = review_identity(reviewed_files=("b.py", "a.py"))
        payload = identity.payload()
        reversed_files = dict(payload, reviewed_files=["b.py", "a.py"])
        self.assertEqual(
            review.ReviewIdentity.from_payload(reversed_files).digest, identity.digest
        )
        missing = dict(payload)
        missing.pop("feature")
        with self.assertRaises(ValueError):
            review.ReviewIdentity.from_payload(missing)
        with self.assertRaises(ValueError):
            review.ReviewIdentity.from_payload(
                dict(payload, identity_schema_version="unknown")
            )
        with self.assertRaises((TypeError, ValueError)):
            review.ReviewIdentity.from_payload(dict(payload, reviewed_files=1))

    def test_integration_context_invalidates_prepared_identity(self):
        identity = review_identity(shard="integration")
        prepared = review.PreparedReview(identity, "prompt", ("codex", "exec"))
        first = review.bind_context(prepared, {"security": "pass"})
        second = review.bind_context(prepared, {"security": "fail"})
        self.assertNotEqual(first.identity.digest, second.identity.digest)

    def test_spec_scope_receives_complete_diff_and_focuses_cover_paths(self):
        paths = [
            "scripts/agent/review.py",
            "scripts/agent/work.py",
            "tests/test_review.py",
            "prompts/review-feature.md",
        ]
        self.assertEqual(
            set(review._paths_for_focus(paths, "spec-scope")), set(paths)
        )
        selected = set()
        for focus in ("security", "tests", "maintainability"):
            group = set(review._paths_for_focus(paths, focus))
            self.assertFalse(selected.intersection(group))
            selected.update(group)
        self.assertTrue(selected.issubset(set(paths)))
        self.assertEqual(selected, set(paths) - {"prompts/review-feature.md"})
        self.assertIn("scripts/agent/review.py", selected)
        self.assertIn("tests/test_review.py", selected)

    def test_review_guidance_is_focus_specific(self):
        security = review._review_guidance("security [1/1]")
        tests = review._review_guidance("tests [1/1]")
        self.assertIn("secret exposure", security)
        self.assertNotIn("test strength", security)
        self.assertIn("test strength", tests)

    def test_runtime_review_snapshot_excludes_mutating_review_events(self):
        validation = mock.Mock(
            sequence=1, kind="validation", result="PASS", head_sha="abc", data={}
        )
        shard = mock.Mock(
            sequence=2, kind="review-shard", result="PASS", head_sha="abc", data={}
        )
        final = mock.Mock(
            sequence=3,
            kind="final-validation-accepted",
            result="PASS",
            head_sha="abc",
            data={
                "result_digest": "token=secret-value",
                "command_identity": "python --token secret-value",
                "unapproved_detail": "password=hunter2",
            },
        )
        rendered = review.render_runtime_evidence([validation, shard, final], "abc")
        self.assertIn('"kind":"validation"', rendered)
        self.assertIn('"kind":"final-validation-accepted"', rendered)
        self.assertNotIn("review-shard", rendered)
        self.assertNotIn("unapproved_detail", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("python --token", rendered)

    def test_timeout_terminates_local_process_group_and_records_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            grandchild_path = Path(directory) / "grandchild.pid"
            child_program = (
                "import os,subprocess,sys,time; time.sleep(0.05); os.setsid(); "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                f"open({str(grandchild_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            program = (
                "import subprocess,sys,time; "
                f"p=subprocess.Popen([sys.executable,'-c',{child_program!r}]); "
                f"open({str(child_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            command = (sys.executable, "-c", program)
            with (
                mock.patch("agent.review.os.killpg", wraps=os.killpg) as killpg,
                self.assertRaises(review.ReviewTimeout) as captured,
            ):
                review.run_process_group(
                    command,
                    "",
                    Path(directory),
                    0.2,
                    {
                        "shard": "tests",
                        "head_sha": "abc",
                        "attempt": 1,
                        "input_digest": "digest",
                    },
                    term_grace_seconds=0.2,
                )
            diagnostic = captured.exception.diagnostic
            self.assertEqual(diagnostic["shard"], "tests")
            self.assertEqual(diagnostic["head_sha"], "abc")
            self.assertEqual(diagnostic["attempt"], 1)
            self.assertEqual(diagnostic["input_digest"], "digest")
            self.assertEqual(diagnostic["configured_timeout"], 0.2)
            self.assertGreaterEqual(diagnostic["elapsed_seconds"], 0.2)
            self.assertEqual(diagnostic["command_id"], Path(command[0]).name + " -c")
            self.assertEqual(diagnostic["prompt_chars"], 0)
            self.assertEqual(diagnostic["prompt_bytes"], 0)
            self.assertIsInstance(diagnostic["pid"], int)
            self.assertEqual(diagnostic["process_status"], "timeout")
            self.assertEqual(diagnostic["termination"], "term")
            self.assertEqual(diagnostic["root_pid"], diagnostic["pid"])
            self.assertEqual(diagnostic["process_group_id"], diagnostic["root_pid"])
            self.assertEqual(
                diagnostic["observed_descendant_pids"],
                diagnostic["tracked_descendant_pids"],
            )
            self.assertEqual(
                diagnostic["term_targets"]["process_group_id"],
                diagnostic["process_group_id"],
            )
            self.assertEqual(diagnostic["kill_targets"]["pids"], [])
            self.assertTrue(diagnostic["termination_confirmed"])
            self.assertEqual(diagnostic["known_survivors"], [])
            self.assertNotIn("token-value", diagnostic["stderr_tail"])
            self.assertTrue(diagnostic["process_group_terminated"])
            self.assertEqual(
                [call.args[1] for call in killpg.call_args_list if call.args[1]],
                [signal.SIGTERM],
            )
            for pid_path in (child_path, grandchild_path):
                child_pid = int(pid_path.read_text())
                for _ in range(20):
                    status = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(child_pid)],
                        text=True,
                        capture_output=True,
                        check=False,
                    ).stdout.strip()
                    if not status or status.startswith("Z"):
                        break
                    time.sleep(0.02)
                else:
                    self.fail(
                        f"review descendant {child_pid} survived process-group timeout"
                    )

    def test_timeout_kills_process_group_when_term_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            grandchild_path = Path(directory) / "grandchild.pid"
            grandchild = (
                "import signal,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
            )
            child = (
                "import signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"p=subprocess.Popen([sys.executable,'-c',{grandchild!r}]); "
                f"open({str(grandchild_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            program = (
                "import signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
                f"open({str(child_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            with (
                mock.patch("agent.review.os.killpg", wraps=os.killpg) as killpg,
                self.assertRaises(review.ReviewTimeout) as captured,
            ):
                review.run_process_group(
                    (sys.executable, "-c", program),
                    "",
                    Path(directory),
                    0.2,
                    {
                        "shard": "maintainability",
                        "head_sha": "def",
                        "attempt": 2,
                        "input_digest": "digest",
                    },
                    term_grace_seconds=0.1,
                )
            self.assertEqual(captured.exception.diagnostic["termination"], "kill")
            self.assertEqual(
                [call.args[1] for call in killpg.call_args_list if call.args[1]],
                [
                    signal.SIGTERM,
                    signal.SIGKILL,
                ],
            )
            for pid_path in (child_path, grandchild_path):
                child_pid = int(pid_path.read_text())
                for _ in range(20):
                    status = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(child_pid)],
                        text=True,
                        capture_output=True,
                        check=False,
                    ).stdout.strip()
                    if not status or status.startswith("Z"):
                        break
                    time.sleep(0.02)
                else:
                    self.fail("SIGKILL did not remove review descendant process")

    def test_timeout_output_normalizes_wrapped_bytes(self):
        self.assertEqual(review._output_text(b"partial\xff"), "partial\ufffd")

    def test_timeout_termination_diagnostic_is_persisted_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            diagnostic = {
                "shard": "security",
                "head_sha": "abc",
                "attempt": 1,
                "configured_timeout": 1,
                "elapsed_seconds": 1.1,
                "command_id": "codex exec",
                "prompt_chars": 10,
                "prompt_bytes": 10,
                "input_digest": "digest",
                "stdout_tail": "",
                "stderr_tail": "token=secret-value",
                "process_status": "timeout",
                "pid": 123,
                "termination": "kill",
                "process_group_terminated": True,
                "tracked_descendant_pids": [124, 125],
            }
            event = delivery.record_review_failure_event(
                store,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity=review_identity(),
                attempt=1,
                error=review.ReviewTimeout(diagnostic),
            )
            persisted = store.read()[0]
            self.assertEqual(event.sequence, persisted.sequence)
            self.assertEqual(persisted.result, "TIMEOUT")
            self.assertEqual(persisted.data["diagnostic"]["termination"], "kill")
            self.assertTrue(persisted.data["diagnostic"]["process_group_terminated"])
            serialized = json.dumps(persisted.data, sort_keys=True)
            self.assertNotIn("secret-value", serialized)
            self.assertIn("[REDACTED]", serialized)
            self.assertNotIn("identity", persisted.data)
            empty_diagnostic_timeout = review.ReviewTimeout(diagnostic)
            empty_diagnostic_timeout.diagnostic = {"unapproved": "token=hidden"}
            second = delivery.record_review_failure_event(
                store,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity=review_identity(),
                attempt=2,
                error=empty_diagnostic_timeout,
            )
            self.assertEqual(second.result, "TIMEOUT")
            self.assertEqual(second.data["diagnostic"], {})
            survivor_diagnostic = {
                **diagnostic,
                "known_survivors": ["pid:123"],
                "termination_confirmed": False,
                "unapproved": "password=hidden-value",
            }
            survivor = delivery.record_review_failure_event(
                store,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity=review_identity(),
                attempt=3,
                error=review.ReviewTimeout(survivor_diagnostic),
            )
            self.assertEqual(survivor.result, "HUMAN_REQUIRED")
            self.assertEqual(
                survivor.data["diagnostic"]["known_survivors"], ["pid:123"]
            )
            self.assertNotIn("hidden-value", json.dumps(survivor.data))
        self.assertEqual(review._output_text("text"), "text")
        self.assertEqual(review._output_text(None), "")

    def test_risk_only_escalates_and_merge_is_fully_gated(self):
        medium = assess("low", [".github/workflows/ci.yml"], [], POLICY)
        self.assertEqual(medium.effective, "medium")
        high = assess("low", ["auth/login.py"], [], POLICY)
        self.assertEqual(high.effective, "high")
        domain_high = assess("low", [], [], POLICY, ("billing",))
        self.assertEqual(domain_high.effective, "high")
        low = assess("low", ["src/a.py"], [], POLICY)
        self.assertTrue(merge_allowed(low, True, POLICY, True, True, []))
        self.assertFalse(merge_allowed(medium, True, POLICY, True, True, []))

    def test_stack_detection_and_proposal(self):
        generic = adapters.Adapter("generic", ("Makefile",), {"unit": "test"}, None)
        python = adapters.Adapter("python", ("pyproject.toml",), {"unit": "test"}, None)
        node = adapters.Adapter("node", ("package.json",), {"unit": "test"}, None)
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "Makefile").write_text("", encoding="utf-8")
            selected, evidence = adapters.detect(repo, [generic, python, node])
            self.assertEqual(selected.name, "generic")
            (repo / "pyproject.toml").write_text("", encoding="utf-8")
            self.assertEqual(
                adapters.detect(repo, [generic, python, node])[0].name, "python"
            )
            (repo / "package.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Ambiguous"):
                adapters.detect(repo, [generic, python, node])
            self.assertIn("test:", adapters.render_make_proposal(python))

    def test_evidence_redacts_tokens_and_budget_is_finite(self):
        self.assertNotIn("secret-value", redact("token=secret-value"))
        self.assertIn("[REDACTED]", redact("Authorization: Bearer abcdef"))
        budget = Budget(60)
        self.assertLessEqual(budget.remaining(10), 10)
