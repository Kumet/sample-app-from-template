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

from agent.ci_tracking import WorkflowRun, normalize_status, require_log_sha, select_run
from agent.contract_migration import preview as migration_preview
from agent.contract_migration import render_v2
from agent.doctor import Check, readiness
from agent.delivery import record_review_failure_event
from agent.events import EventStore, render_validation_log
from agent.gates import (
    REQUIRED_REVIEW_SHARDS,
    evaluate_gates,
    require_exact_validation,
    require_mergeable,
)
from agent.notifications import github_comment, payload, stdout_json, write_outbox
from agent.quality import validate as validate_quality
from agent.queue import Queue
from agent.release import check as release_check
from agent import review
from agent.review import REVIEW_IDENTITY_FIELDS, ReviewIdentity, ReviewResult
from agent.review_shards import (
    SHARDS,
    ShardResult,
    aggregate,
    record_reuse_decision,
    reusable_event,
    split_files,
)
from agent.scope_approval import (
    apply as scope_apply,
)
from agent.scope_approval import (
    preview as scope_preview,
)
from agent.scope_approval import (
    preview_request as scope_request_preview,
)
from agent.scope_approval import (
    request as scope_request,
)
from agent.state import RunState, write_state
from agent.telemetry import Limits, Usage, parse_codex_tokens
from agent.validation import ScopeViolation
from agent.work import _scope_paths


class ProductionReadyTests(unittest.TestCase):
    def test_known_reviewer_survivor_requires_human(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            identity = ReviewIdentity(
                identity_schema_version="4",
                feature="007-x",
                head_sha="abc",
                shard="security",
                review_schema_version="1",
                prompt_version="2",
                reviewer_model="gpt-5.4-mini",
                reviewer_command_identity="c" * 64,
                review_settings=("model=gpt-5.4-mini",),
                reviewed_files=("file.py",),
                spec_digest="1" * 64,
                plan_digest="2" * 64,
                tasks_digest="3" * 64,
                validation_contract_digest="4" * 64,
                diff_input_digest="5" * 64,
                runtime_evidence_digest="6" * 64,
                tracked_snapshot_event_sequence=1,
                validation_log_blob_sha="b" * 40,
                final_validation_attempt_event_sequence=2,
                final_validation_accepted_event_sequence=3,
                final_validation_result_digest="7" * 64,
            )
            diagnostic = {
                "shard": "security",
                "head_sha": "abc",
                "attempt": 1,
                "configured_timeout": 1,
                "known_survivors": ["pid:123"],
                "termination_confirmed": False,
            }
            event = record_review_failure_event(
                store,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity=identity,
                attempt=1,
                error=review.ReviewTimeout(diagnostic),
            )
            self.assertEqual(event.result, "HUMAN_REQUIRED")
            self.assertEqual(event.data["diagnostic"]["known_survivors"], ["pid:123"])

    def test_exact_validation_and_review_shards_share_head(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            common = dict(feature="007-x", repository="repo", branch="b", worktree="w")
            store.append(
                **common,
                phase="final",
                kind="validation",
                result="PASS",
                head_sha="abc",
            )
            with self.assertRaisesRegex(ValueError, "final-validation-accepted"):
                require_exact_validation(store.read(), "abc")
            store.append(
                **common,
                phase="post-evidence",
                kind="final-validation-accepted",
                result="PASS",
                head_sha="abc",
            )
            store.append(
                **common,
                phase="delivery",
                kind="weakening",
                result="PASS",
                head_sha="abc",
            )
            for shard in REQUIRED_REVIEW_SHARDS:
                identity = ReviewIdentity(
                    identity_schema_version="4",
                    feature="007-x",
                    head_sha="abc",
                    shard=shard,
                    review_schema_version="1",
                    prompt_version="2",
                    reviewer_model="test",
                    reviewer_command_identity="c" * 64,
                    review_settings=("model=test",),
                    reviewed_files=("file.py",),
                    spec_digest="1" * 64,
                    plan_digest="2" * 64,
                    tasks_digest="3" * 64,
                    validation_contract_digest="4" * 64,
                    diff_input_digest=f"input-{shard}",
                    runtime_evidence_digest="7" * 64,
                    tracked_snapshot_event_sequence=1,
                    validation_log_blob_sha="b" * 40,
                    final_validation_attempt_event_sequence=2,
                    final_validation_accepted_event_sequence=3,
                    final_validation_result_digest="5" * 64,
                )
                store.append(
                    **common,
                    phase="review",
                    kind="review-shard",
                    result="PASS",
                    head_sha="abc",
                    data={
                        "shard": shard,
                        "identity_digest": identity.digest,
                        "identity": identity.payload(),
                        "findings": [],
                    },
                )
                store.append(
                    **common,
                    phase="review",
                    kind="review-shard",
                    result="PASS",
                    head_sha="abc",
                    data={
                        "shard": shard,
                        "aggregate": True,
                        "chunk_identities": [identity.digest],
                    },
                )
            self.assertEqual(
                require_exact_validation(store.read(), "abc").head_sha, "abc"
            )
            with self.assertRaisesRegex(ValueError, "final-validation-accepted"):
                require_exact_validation(store.read(), "def")

    def test_validation_log_render_does_not_copy_future_final_event(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            common = dict(feature="007-x", repository="repo", branch="b", worktree="w")
            before = store.append(
                **common,
                phase="task",
                kind="task-complete",
                result="PASS",
                head_sha="parent",
            )
            rendered = render_validation_log(store.read(), "007-x")
            final = store.append(
                **common,
                phase="final",
                kind="validation",
                result="PASS",
                head_sha="exact",
            )
            self.assertIn(f"| {before.sequence} |", rendered)
            self.assertNotIn(f"| {final.sequence} |", rendered)
            self.assertEqual(store.read()[-1].head_sha, "exact")

    def test_review_cache_reuses_only_matching_pass_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            identity = ReviewIdentity(
                identity_schema_version="4",
                feature="007-x",
                head_sha="abc",
                shard="security",
                review_schema_version="1",
                prompt_version="2",
                reviewer_model="gpt-5.4-mini",
                reviewer_command_identity="c" * 64,
                review_settings=("model=gpt-5.4-mini",),
                reviewed_files=("file.py",),
                spec_digest="1" * 64,
                plan_digest="2" * 64,
                tasks_digest="3" * 64,
                validation_contract_digest="4" * 64,
                diff_input_digest="5" * 64,
                runtime_evidence_digest="7" * 64,
                tracked_snapshot_event_sequence=1,
                validation_log_blob_sha="b" * 40,
                final_validation_attempt_event_sequence=2,
                final_validation_accepted_event_sequence=3,
                final_validation_result_digest="6" * 64,
            )
            passed = store.append(
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                phase="review",
                kind="review-shard",
                result="PASS",
                head_sha="abc",
                data={"identity_digest": identity.digest},
            )
            store.append(
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                phase="review",
                kind="review-shard",
                result="TIMEOUT",
                head_sha="abc",
                data={"identity_digest": "timeout"},
            )
            self.assertEqual(reusable_event(store.read(), identity.digest), passed)
            reuse = record_reuse_decision(
                store,
                source=passed,
                feature="007-x",
                repository="repo",
                branch="branch",
                worktree="worktree",
                head_sha="abc",
                shard="security",
                identity_digest=identity.digest,
            )
            self.assertEqual(reuse.data["source_sequence"], passed.sequence)
            self.assertEqual(reuse.data["identity_digest"], identity.digest)
            for field in REVIEW_IDENTITY_FIELDS:
                values = dict(identity.__dict__)
                value = values[field]
                if field == "identity_schema_version":
                    payload = identity.payload()
                    payload[field] = "unknown"
                    with self.assertRaises(ValueError):
                        ReviewIdentity.from_payload(payload)
                    continue
                values[field] = (
                    value + 1
                    if isinstance(value, int)
                    else value + ("changed",)
                    if isinstance(value, tuple)
                    else value + "-changed"
                )
                changed = ReviewIdentity(**values)
                with self.subTest(field=field):
                    self.assertIsNone(reusable_event(store.read(), changed.digest))
            incomplete = identity.payload()
            incomplete.pop("head_sha")
            with self.assertRaises(ValueError):
                ReviewIdentity.from_payload(incomplete)
            malformed = identity.payload()
            malformed["reviewed_files"] = "file.py"
            with self.assertRaises((TypeError, ValueError)):
                ReviewIdentity.from_payload(malformed)
            self.assertIsNone(reusable_event(store.read(), "timeout"))
            for result in ("FAIL", "TIMEOUT", "CANCELLED", "INVALID", "PARSE_FAILED"):
                non_pass = store.append(
                    feature="007-x",
                    repository="repo",
                    branch="branch",
                    worktree="worktree",
                    phase="review",
                    kind="review-shard",
                    result=result,
                    head_sha="abc",
                    data={"identity_digest": identity.digest},
                )
                with self.subTest(result=result):
                    self.assertIsNone(reusable_event([non_pass], identity.digest))

    def test_reviewer_timeout_removes_child_and_grandchild_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            child_path = Path(directory) / "child.pid"
            grandchild_path = Path(directory) / "grandchild.pid"
            grandchild_program = (
                "import signal,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
            )
            child_program = (
                "import os,signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "time.sleep(0.05); os.setsid(); "
                f"p=subprocess.Popen([sys.executable,'-c',{grandchild_program!r}]); "
                f"open({str(grandchild_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            parent_program = (
                "import signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"p=subprocess.Popen([sys.executable,'-c',{child_program!r}]); "
                f"open({str(child_path)!r},'w').write(str(p.pid)); time.sleep(60)"
            )
            with (
                mock.patch("agent.review.os.killpg", wraps=os.killpg) as killpg,
                self.assertRaises(review.ReviewTimeout) as raised,
            ):
                review.run_process_group(
                    (sys.executable, "-c", parent_program),
                    "",
                    Path(directory),
                    0.2,
                    {
                        "shard": "security",
                        "head_sha": "abc",
                        "attempt": 1,
                        "input_digest": "digest",
                    },
                    term_grace_seconds=0.2,
                )
            self.assertTrue(raised.exception.diagnostic["process_group_terminated"])
            self.assertEqual(raised.exception.diagnostic["termination"], "kill")
            self.assertEqual(
                [call.args[1] for call in killpg.call_args_list if call.args[1]],
                [
                    signal.SIGSTOP,
                    signal.SIGTERM,
                    signal.SIGCONT,
                    signal.SIGKILL,
                ],
            )
            tracked = set(raised.exception.diagnostic["tracked_descendant_pids"])
            for path in (child_path, grandchild_path):
                pid = int(path.read_text())
                self.assertIn(pid, tracked)
                for _ in range(100):
                    status = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(pid)],
                        text=True,
                        capture_output=True,
                        check=False,
                    ).stdout.strip()
                    if not status:
                        break
                    time.sleep(0.02)
                else:
                    self.fail(f"review descendant {pid} survived timeout cleanup")

    def test_events_recover_truncated_tail_and_render_all_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            store = EventStore(path)
            store.append(
                feature="012-x",
                repository="repo",
                branch="b",
                worktree="w",
                phase="test",
                kind="validation",
                result="FAIL",
                head_sha="a",
                detail="first",
            )
            store.append(
                feature="012-x",
                repository="repo",
                branch="b",
                worktree="w",
                phase="test",
                kind="validation",
                result="PASS",
                head_sha="b",
                detail="second",
            )
            with path.open("ab") as handle:
                handle.write(b'{"truncated":')
            events = store.read()
            self.assertEqual(len(events), 2)
            store.append(
                feature="012-x",
                repository="repo",
                branch="b",
                worktree="w",
                phase="test",
                kind="review",
                result="PASS",
                head_sha="b",
                detail="third",
            )
            events = store.read()
            self.assertEqual([event.sequence for event in events], [1, 2, 3])
            markdown = render_validation_log(events, "012-x")
            self.assertIn("first", markdown)
            self.assertIn("second", markdown)
            self.assertIn("third", markdown)

    def test_exact_sha_gates_fail_on_new_head(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "tracked.txt").write_text("one", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
            old_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            store = EventStore(Path(directory) / "events.jsonl")
            for kind in (
                "final-validation-accepted",
                "weakening",
                "review",
                "ci",
            ):
                store.append(
                    feature="x",
                    repository="r",
                    branch="b",
                    worktree="w",
                    phase=kind,
                    kind=kind,
                    result="PASS",
                    head_sha=old_head,
                )
            self.assertTrue(evaluate_gates(store.read(), old_head).passed)
            (repo / "tracked.txt").write_text("two", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "two"], cwd=repo, check=True)
            new_head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            report = evaluate_gates(store.read(), new_head)
            self.assertEqual(
                set(report.mismatched),
                {"final-validation-accepted", "weakening", "review", "ci"},
            )
            with self.assertRaisesRegex(ValueError, "not fully gated"):
                require_mergeable(store.read(), new_head)

    def test_quality_requires_explicit_reason(self):
        valid = {
            name: (
                {"enabled": True}
                if name == "test"
                else {"enabled": False, "reason": "not applicable"}
            )
            for name in ("lint", "typecheck", "test", "build")
        }
        self.assertEqual(validate_quality(valid), [])
        valid["lint"] = {"enabled": False}
        self.assertTrue(validate_quality(valid))

    def test_doctor_readiness_levels(self):
        checks = [Check("git", "PASS", ""), Check("github-auth", "FAIL", "")]
        result = readiness(checks)
        self.assertFalse(result["medium_delivery"])

    def test_ci_selects_exact_sha(self):
        runs = [
            WorkflowRun(1, "old", "completed", "failure"),
            WorkflowRun(2, "new", "in_progress", None),
        ]
        selected = select_run(runs, "new")
        self.assertEqual(selected.run_id, 2)
        self.assertEqual(normalize_status(selected), "pending")
        with self.assertRaises(ValueError):
            require_log_sha(runs[0], "new")

    def test_review_shards_complete_and_sha_bound(self):
        chunks = split_files({"a.py": "a" * 10, "b.py": "b" * 10}, max_chars=15)
        self.assertEqual(len(chunks), 2)
        results = [
            ShardResult(name, "sha", ReviewResult("pass", ()))
            for name in (*SHARDS, "integration")
        ]
        self.assertEqual(aggregate(results, "sha").result, "pass")
        with self.assertRaises(ValueError):
            aggregate(results, "other")

    def test_migration_only_accepts_make_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            feature = Path(directory)
            (feature / "validation.toml").write_text(
                "version=1\nmax_tasks=2\nmax_attempts_per_task=3\nmax_final_validation_attempts=3\n"
                '[commands]\nunit=["make","test"]\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8",
            )
            self.assertTrue(migration_preview(feature, {"test"})["safe"])
            self.assertIn("version = 2", render_v2(feature, {"test"}))
            (feature / "validation.toml").write_text(
                "version=1\nmax_tasks=2\nmax_attempts_per_task=3\nmax_final_validation_attempts=3\n"
                '[commands]\nbad=["python","evil.py"]\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8",
            )
            self.assertFalse(migration_preview(feature, {"test"})["safe"])

    def test_notifications_are_structured_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            note = payload("human-required", "012-x", "stopped", "token=secret", "abc")
            self.assertNotIn("secret", stdout_json(note))
            self.assertTrue(write_outbox(Path(directory), note).is_file())
            completed = subprocess.CompletedProcess([], 0, "", "")
            runner = mock.Mock(return_value=completed)
            github_comment(note, Path(directory), 3, runner)
            self.assertEqual(runner.call_args.args[0][:4], ["gh", "pr", "comment", "3"])

    def test_queue_lock_duplicate_park_and_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = Queue(Path(directory) / "queue.json")
            queue.add("012-x")
            with self.assertRaises(ValueError):
                queue.add("012-x")
            self.assertEqual(queue.update("012-x", "parked")[0].status, "parked")
            queue.acquire()
            with self.assertRaises(ValueError):
                queue.acquire()
            queue.release()
            self.assertEqual(queue.update("012-x", "cancelled")[0].status, "cancelled")

    def test_budgets_report_and_stop(self):
        limits = Limits(60, 2, 1, 1, 100, 100)
        usage = Usage(codex_calls=1)
        self.assertEqual(usage.remaining(limits)["codex_calls"], 1)
        usage.consume("codex_calls")
        with self.assertRaisesRegex(RuntimeError, "Budget exhausted"):
            usage.require_available(limits)
        self.assertEqual(parse_codex_tokens("tokens used\n12,345"), 12345)

    def test_scope_approval_requires_event_and_updates_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / "specs" / "012-x"
            feature.mkdir(parents=True)
            (feature / "spec.md").write_text(
                "## Scope\n\n### Allowed changes\n\n- `src/**`\n\n"
                "### Forbidden changes\n\n- secrets\n",
                encoding="utf-8",
            )
            (feature / "validation.toml").write_text(
                'version=2\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8",
            )
            store = EventStore(root / "events.jsonl")
            store.append(
                feature="012-x",
                repository="r",
                branch="b",
                worktree="w",
                phase="task",
                kind="scope-request",
                result="HUMAN_REQUIRED",
                head_sha="abc",
                data={"path": "prompts/**"},
            )
            self.assertEqual(
                scope_preview(feature, "prompts/**", "review", store)["path"],
                "prompts/**",
            )
            scope_apply(feature, "prompts/**", "review", store)
            self.assertIn(
                "prompts/**", (feature / "spec.md").read_text(encoding="utf-8")
            )
            self.assertIn(
                '"prompts/**"',
                (feature / "validation.toml").read_text(encoding="utf-8"),
            )

    def test_scope_paths_survive_exception_wrapping(self):
        violation = ScopeViolation("outside", ["src/pkg.egg-info/", "README.md"])
        try:
            try:
                raise violation
            except ScopeViolation as error:
                raise RuntimeError(
                    f"Unsafe scope failure requires human review: {error}"
                ) from error
        except RuntimeError as wrapped:
            self.assertEqual(_scope_paths(wrapped), ("src/pkg.egg-info", "README.md"))

    def test_scope_request_is_explicit_non_approving_and_append_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / "specs" / "012-x"
            feature.mkdir(parents=True)
            (feature / "spec.md").write_text(
                "## Scope\n\n### Allowed changes\n\n- `src/**`\n\n"
                "### Forbidden changes\n\n- secrets\n",
                encoding="utf-8",
            )
            (feature / "plan.md").write_text("plan\n", encoding="utf-8")
            (feature / "tasks.md").write_text("tasks\n", encoding="utf-8")
            (feature / "validation.toml").write_text(
                'version=2\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8",
            )
            state_path = root / ".agent-work" / "012-x" / "state.json"
            write_state(
                state_path,
                RunState(
                    1,
                    "012-x",
                    "feature/012-x",
                    "base",
                    "head",
                    "digest",
                    "T001",
                    1,
                    "implement",
                    "scope",
                    ("src/pkg.egg-info/",),
                    "failed",
                    "/tmp/worktree",
                    "now",
                ),
            )
            store = EventStore(root / ".agent-work" / "012-x" / "events.jsonl")
            store.append(
                feature="012-x",
                repository=str(root),
                branch="feature/012-x",
                worktree="/tmp/worktree",
                phase="task",
                kind="scope-request",
                result="FAIL",
                head_sha="head",
                detail=(
                    "Unsafe scope failure requires human review: "
                    "Out-of-scope files changed: src/pkg.egg-info/"
                ),
                data={"path": "Out-of-scope files changed: src/pkg.egg-info/"},
            )

            before = store.path.read_bytes()
            preview = scope_request_preview(
                feature, ".gitignore", "ignore build output", store, state_path
            )
            self.assertEqual(preview["mutation"], "append scope-request event")
            self.assertEqual(store.path.read_bytes(), before)
            scope_request(
                feature, ".gitignore", "ignore build output", store, state_path
            )
            request_event = store.read()[-1]
            self.assertEqual(request_event.result, "HUMAN_REQUIRED")
            self.assertEqual(request_event.data["paths"], [".gitignore"])
            self.assertNotEqual(request_event.kind, "scope-approved")
            with self.assertRaisesRegex(ValueError, "already exists"):
                scope_request_preview(feature, ".gitignore", "again", store, state_path)

            self.assertEqual(
                scope_preview(feature, ".gitignore", "approved", store)["path"],
                ".gitignore",
            )
            scope_apply(feature, ".gitignore", "approved", store, state_path)
            self.assertEqual(store.read()[-1].kind, "scope-approved")
            self.assertIn(
                '".gitignore"',
                (feature / "validation.toml").read_text(encoding="utf-8"),
            )
            with self.assertRaisesRegex(ValueError, "No matching"):
                scope_preview(feature, ".gitignore", "approve twice", store)

    def test_scope_request_and_approval_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / "specs" / "012-x"
            feature.mkdir(parents=True)
            (feature / "validation.toml").write_text(
                'version=2\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8",
            )
            store = EventStore(root / "events.jsonl")
            for unsafe in ("", "/tmp/x", "../x", "a\nb", "**", "*"):
                with self.assertRaises(ValueError):
                    scope_preview(feature, unsafe, "reason", store)
            store.append(
                feature="other",
                repository="r",
                branch="b",
                worktree="w",
                phase="task",
                kind="scope-request",
                result="HUMAN_REQUIRED",
                head_sha="abc",
                data={"paths": ["README.md"]},
            )
            with self.assertRaisesRegex(ValueError, "No matching"):
                scope_preview(feature, "README.md", "reason", store)
            store.append(
                feature="012-x",
                repository="r",
                branch="b",
                worktree="w",
                phase="task",
                kind="scope-request",
                result="FAIL",
                head_sha="abc",
                data={"path": "Out-of-scope files changed: README.md"},
            )
            with self.assertRaisesRegex(ValueError, "No matching"):
                scope_preview(feature, "README.md", "reason", store)

    def test_scope_approval_synchronizes_failed_worktree_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / "specs" / "012-x"
            worktree_feature = root / "worktree" / "specs" / "012-x"
            feature.mkdir(parents=True)
            worktree_feature.mkdir(parents=True)
            spec = (
                "## Scope\n\n### Allowed changes\n\n- `src/**`\n\n"
                "### Forbidden changes\n\n- secrets\n"
            )
            contract = (
                'version=2\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n'
            )
            for directory_path in (feature, worktree_feature):
                (directory_path / "spec.md").write_text(spec, encoding="utf-8")
                (directory_path / "plan.md").write_text("plan\n", encoding="utf-8")
                (directory_path / "tasks.md").write_text("tasks\n", encoding="utf-8")
                (directory_path / "validation.toml").write_text(
                    contract, encoding="utf-8"
                )
            state_path = root / ".agent-work" / "012-x" / "state.json"
            write_state(
                state_path,
                RunState(
                    1,
                    "012-x",
                    "agent/012-x",
                    "base",
                    "head",
                    "old",
                    "T001",
                    1,
                    "implement",
                    "scope",
                    ("src/generated/",),
                    "failed",
                    str(root / "worktree"),
                    "now",
                ),
            )
            store = EventStore(root / ".agent-work" / "012-x" / "events.jsonl")
            store.append(
                feature="012-x",
                repository=str(root),
                branch="agent/012-x",
                worktree=str(root / "worktree"),
                phase="approval",
                kind="scope-request",
                result="HUMAN_REQUIRED",
                head_sha="head",
                data={"paths": [".gitignore"]},
            )
            with mock.patch(
                "agent.scope_approval.git_utils.changed_paths",
                return_value=[
                    "specs/012-x/spec.md",
                    "specs/012-x/validation.toml",
                    "src/generated/",
                ],
            ):
                scope_apply(feature, ".gitignore", "approved", store, state_path)
            self.assertEqual(
                (feature / "spec.md").read_text(),
                (worktree_feature / "spec.md").read_text(),
            )
            self.assertEqual(
                (feature / "validation.toml").read_text(),
                (worktree_feature / "validation.toml").read_text(),
            )
            from agent.state import contract_digest, read_state

            state = read_state(state_path)
            self.assertEqual(state.contract_digest, contract_digest(worktree_feature))
            self.assertIn("specs/012-x/spec.md", state.changed_paths)

    def test_release_artifacts_without_git_constraints(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (repo / "CHANGELOG.md").write_text("1.0.0", encoding="utf-8")
            for name in ("migration-v1.md", "compatibility.md", "release-checklist.md"):
                (repo / "docs" / name).write_text(name, encoding="utf-8")
            self.assertEqual(
                release_check(repo, require_main=False, require_clean=False), []
            )
