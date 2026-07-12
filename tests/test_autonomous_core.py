import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unittest import mock

from agent import adapters, recovery, review, weakening
from agent.budget import Budget
from agent.evidence import redact
from agent.policy import RepositoryPolicy, validation_commands
from agent.review import ReviewResult, parse_review, review_with_repairs
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


class AutonomousCoreTests(unittest.TestCase):
    def test_allowlist_builds_only_make_commands(self):
        self.assertEqual(
            validation_commands({"unit": "test"}, POLICY), {"unit": ("make", "test")}
        )
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            validation_commands({"bad": "deploy"}, POLICY)
        with self.assertRaises(ValueError):
            validation_commands({"bad": "test;rm"}, POLICY)

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
        findings = weakening.inspect_patch(patch)
        self.assertTrue(any(f.required and f.category == "test-skip" for f in findings))
        self.assertTrue(any(f.category == "assertion-removal" for f in findings))

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
            for name in ("spec.md", "plan.md", "tasks.md", "validation-log.md"):
                content = f"{name}-start\n" + "a" * 13_000 + f"\n{name}-end"
                (feature / name).write_text(content, encoding="utf-8")
            (feature / "validation.toml").write_text("version=2\n", encoding="utf-8")
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
                result, prompt, _ = review.run_review(repo, feature)
            self.assertEqual(result.result, "pass")
            for name in ("spec.md", "plan.md", "tasks.md", "validation-log.md"):
                self.assertIn(f"{name}-start", prompt)
                self.assertIn(f"{name}-end", prompt)
            self.assertIn("diff-start", prompt)
            self.assertIn("diff-end", prompt)
            self.assertIn("Do not run commands", prompt)
            self.assertIn(":(exclude)specs/012-test/**", run.call_args_list[1].args[0])
            command = process_group.call_args.args[0]
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
            for name in ("spec.md", "plan.md", "tasks.md", "validation-log.md"):
                (feature / name).write_text(name, encoding="utf-8")
            (feature / "validation.toml").write_text("version=2\n", encoding="utf-8")
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
                self.assertRaisesRegex(
                    RuntimeError, "refusing to review truncated content"
                ),
            ):
                review.run_review(repo, feature)
            self.assertEqual(run.call_count, 4)

    def test_review_identity_changes_with_head_and_complete_input(self):
        identity = review.ReviewIdentity(
            "007-x",
            "abc",
            "security",
            "1",
            "1",
            ("model=low",),
            ("codex", "exec"),
            ("a.py",),
            "input-a",
        )
        same = review.ReviewIdentity(**identity.__dict__)
        changed_head = review.ReviewIdentity(**{**identity.__dict__, "head_sha": "def"})
        changed_input = review.ReviewIdentity(
            **{**identity.__dict__, "input_digest": "input-b"}
        )
        self.assertEqual(identity.digest, same.digest)
        self.assertNotEqual(identity.digest, changed_head.digest)
        self.assertNotEqual(identity.digest, changed_input.digest)

    def test_integration_context_invalidates_prepared_identity(self):
        identity = review.ReviewIdentity(
            "007-x",
            "abc",
            "integration",
            "1",
            "1",
            ("model=low",),
            ("codex", "exec"),
            ("a.py",),
            "input-a",
        )
        prepared = review.PreparedReview(identity, "prompt", ("codex", "exec"))
        first = review.bind_context(prepared, {"security": "pass"})
        second = review.bind_context(prepared, {"security": "fail"})
        self.assertNotEqual(first.identity.digest, second.identity.digest)

    def test_file_focus_partition_covers_every_changed_path(self):
        paths = [
            "scripts/agent/review.py",
            "scripts/agent/work.py",
            "tests/test_review.py",
            "prompts/review-feature.md",
        ]
        selected = set()
        for focus in ("spec-scope", "security", "tests", "maintainability"):
            group = review._paths_for_focus(paths, focus)
            self.assertFalse(selected.intersection(group))
            selected.update(group)
        self.assertEqual(selected, set(paths))

    def test_review_guidance_is_focus_specific(self):
        security = review._review_guidance("security [1/1]")
        tests = review._review_guidance("tests [1/1]")
        self.assertIn("secret exposure", security)
        self.assertNotIn("test strength", security)
        self.assertIn("test strength", tests)

    def test_timeout_terminates_local_process_group_and_records_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            program = (
                "import subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c',"
                "'import time; time.sleep(60)']); "
                f"open({str(child_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            command = (sys.executable, "-c", program)
            with self.assertRaises(review.ReviewTimeout) as captured:
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
            self.assertTrue(diagnostic["process_group_terminated"])
            child_pid = int(child_path.read_text())
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("review child process survived process-group timeout")

    def test_timeout_kills_process_group_when_term_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            child = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
            program = (
                "import signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
                f"open({str(child_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            with self.assertRaises(review.ReviewTimeout) as captured:
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
            child_pid = int(child_path.read_text())
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("SIGKILL did not remove review child process")

    def test_timeout_output_normalizes_wrapped_bytes(self):
        self.assertEqual(review._output_text(b"partial\xff"), "partial\ufffd")
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
