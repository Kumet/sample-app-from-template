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
from agent.policy import RepositoryPolicy, validation_commands
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
    "final_validation_event_sequence": 11,
    "final_validation_result_digest": "f" * 64,
}


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
        "final_validation_event_sequence": 11,
        "final_validation_result_digest": "6" * 64,
    }
    values.update(changes)
    return review.ReviewIdentity(**values)


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
                result, prompt, _ = review.run_review(
                    repo, feature, evidence_fields=EVIDENCE_FIELDS
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
                mock.patch("agent.review.run_process_group") as process_group,
                self.assertRaisesRegex(
                    RuntimeError, "refusing to review truncated content"
                ),
            ):
                review.run_review(repo, feature, evidence_fields=EVIDENCE_FIELDS)
            self.assertEqual(run.call_count, 4)
            process_group.assert_not_called()

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
                "final_validation_event_sequence",
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

    def test_runtime_review_snapshot_excludes_mutating_review_events(self):
        validation = mock.Mock(
            sequence=1, kind="validation", result="PASS", head_sha="abc", data={}
        )
        shard = mock.Mock(
            sequence=2, kind="review-shard", result="PASS", head_sha="abc", data={}
        )
        final = mock.Mock(
            sequence=3,
            kind="final-validation",
            result="PASS",
            head_sha="abc",
            data={
                "result_digest": "token=secret-value",
                "unapproved_detail": "password=hunter2",
            },
        )
        rendered = review.render_runtime_evidence([validation, shard, final], "abc")
        self.assertIn('"kind":"validation"', rendered)
        self.assertIn('"kind":"final-validation"', rendered)
        self.assertNotIn("review-shard", rendered)
        self.assertNotIn("unapproved_detail", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("hunter2", rendered)

    def test_timeout_terminates_local_process_group_and_records_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            grandchild_path = Path(directory) / "grandchild.pid"
            child_program = (
                "import subprocess,sys,time; "
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
            self.assertNotIn("token-value", diagnostic["stderr_tail"])
            self.assertTrue(diagnostic["process_group_terminated"])
            self.assertEqual(
                [call.args[1] for call in killpg.call_args_list if call.args[1]],
                [signal.SIGSTOP, signal.SIGTERM, signal.SIGCONT],
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
            child = (
                "import signal,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
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
                    signal.SIGSTOP,
                    signal.SIGTERM,
                    signal.SIGCONT,
                    signal.SIGKILL,
                ],
            )
            child_pid = int(child_path.read_text())
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
                self.fail("SIGKILL did not remove review child process")

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
            self.assertNotIn("secret-value", str(persisted.data))
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
