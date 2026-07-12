import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent.ci_tracking import WorkflowRun, normalize_status, require_log_sha, select_run
from agent.contract_migration import preview as migration_preview, render_v2
from agent.doctor import Check, readiness
from agent.events import EventStore, render_validation_log
from agent.gates import evaluate_gates, require_mergeable
from agent.notifications import github_comment, payload, stdout_json, write_outbox
from agent.quality import validate as validate_quality
from agent.queue import Queue
from agent.release import check as release_check
from agent.review import ReviewResult
from agent.review_shards import SHARDS, ShardResult, aggregate, split_files
from agent.scope_approval import apply as scope_apply, preview as scope_preview
from agent.telemetry import Limits, Usage, parse_codex_tokens
from unittest import mock


class ProductionReadyTests(unittest.TestCase):
    def test_events_recover_truncated_tail_and_render_all_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            store = EventStore(path)
            store.append(feature="012-x", repository="repo", branch="b", worktree="w",
                         phase="test", kind="validation", result="FAIL", head_sha="a", detail="first")
            store.append(feature="012-x", repository="repo", branch="b", worktree="w",
                         phase="test", kind="validation", result="PASS", head_sha="b", detail="second")
            with path.open("ab") as handle:
                handle.write(b'{"truncated":')
            events = store.read()
            self.assertEqual(len(events), 2)
            store.append(feature="012-x", repository="repo", branch="b", worktree="w",
                         phase="test", kind="review", result="PASS", head_sha="b", detail="third")
            events = store.read()
            self.assertEqual([event.sequence for event in events], [1, 2, 3])
            markdown = render_validation_log(events, "012-x")
            self.assertIn("first", markdown)
            self.assertIn("second", markdown)
            self.assertIn("third", markdown)

    def test_exact_sha_gates_fail_on_new_head(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            for kind in ("validation", "weakening", "review", "ci"):
                store.append(feature="x", repository="r", branch="b", worktree="w",
                             phase=kind, kind=kind, result="PASS", head_sha="abc")
            self.assertTrue(evaluate_gates(store.read(), "abc").passed)
            with self.assertRaisesRegex(ValueError, "not fully gated"):
                require_mergeable(store.read(), "def")

    def test_quality_requires_explicit_reason(self):
        valid = {name: ({"enabled": True} if name == "test" else {"enabled": False, "reason": "not applicable"})
                 for name in ("lint", "typecheck", "test", "build")}
        self.assertEqual(validate_quality(valid), [])
        valid["lint"] = {"enabled": False}
        self.assertTrue(validate_quality(valid))

    def test_doctor_readiness_levels(self):
        checks = [Check("git", "PASS", ""), Check("github-auth", "FAIL", "")]
        result = readiness(checks)
        self.assertFalse(result["medium_delivery"])

    def test_ci_selects_exact_sha(self):
        runs = [WorkflowRun(1, "old", "completed", "failure"),
                WorkflowRun(2, "new", "in_progress", None)]
        selected = select_run(runs, "new")
        self.assertEqual(selected.run_id, 2)
        self.assertEqual(normalize_status(selected), "pending")
        with self.assertRaises(ValueError):
            require_log_sha(runs[0], "new")

    def test_review_shards_complete_and_sha_bound(self):
        chunks = split_files({"a.py": "a" * 10, "b.py": "b" * 10}, max_chars=15)
        self.assertEqual(len(chunks), 2)
        results = [ShardResult(name, "sha", ReviewResult("pass", ()))
                   for name in (*SHARDS, "integration")]
        self.assertEqual(aggregate(results, "sha").result, "pass")
        with self.assertRaises(ValueError):
            aggregate(results, "other")

    def test_migration_only_accepts_make_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            feature = Path(directory)
            (feature / "validation.toml").write_text(
                'version=1\nmax_tasks=2\nmax_attempts_per_task=3\nmax_final_validation_attempts=3\n'
                '[commands]\nunit=["make","test"]\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
                encoding="utf-8")
            self.assertTrue(migration_preview(feature, {"test"})["safe"])
            self.assertIn("version = 2", render_v2(feature, {"test"}))
            (feature / "validation.toml").write_text(
                'version=1\nmax_tasks=2\nmax_attempts_per_task=3\nmax_final_validation_attempts=3\n'
                '[commands]\nbad=["python","evil.py"]\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n', encoding="utf-8")
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
                "## Scope\n\n### Allowed changes\n\n- `src/**`\n\n### Forbidden changes\n\n- secrets\n",
                encoding="utf-8")
            (feature / "validation.toml").write_text(
                'version=2\n[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n', encoding="utf-8")
            store = EventStore(root / "events.jsonl")
            store.append(feature="012-x", repository="r", branch="b", worktree="w",
                         phase="task", kind="scope-request", result="HUMAN_REQUIRED",
                         head_sha="abc", data={"path": "prompts/**"})
            self.assertEqual(scope_preview(feature, "prompts/**", "review", store)["path"], "prompts/**")
            scope_apply(feature, "prompts/**", "review", store)
            self.assertIn("prompts/**", (feature / "spec.md").read_text(encoding="utf-8"))
            self.assertIn('"prompts/**"', (feature / "validation.toml").read_text(encoding="utf-8"))

    def test_release_artifacts_without_git_constraints(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "docs").mkdir()
            (repo / "VERSION").write_text("1.0.0\n", encoding="utf-8")
            (repo / "CHANGELOG.md").write_text("1.0.0", encoding="utf-8")
            for name in ("migration-v1.md", "compatibility.md", "release-checklist.md"):
                (repo / "docs" / name).write_text(name, encoding="utf-8")
            self.assertEqual(release_check(repo, require_main=False, require_clean=False), [])
