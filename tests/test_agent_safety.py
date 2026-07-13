import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent import git_utils
from agent.delivery import _safe_command_failure, record_review_failure_event
from agent.events import EventStore
from agent.evidence import redact_value, safe_error_detail
from agent.parser import WorkConfig
from agent.validation import ScopeViolation, validate_scope


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=self.repo, check=True
        )
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_main_is_rejected(self):
        with self.assertRaises(git_utils.GitError):
            git_utils.ensure_safe_start(self.repo)

    def test_dirty_feature_branch_is_rejected(self):
        subprocess.run(
            ["git", "switch", "-q", "-c", "feature/test"], cwd=self.repo, check=True
        )
        (self.repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaises(git_utils.GitError):
            git_utils.ensure_safe_start(self.repo)

    def test_scope_rejects_forbidden_and_outside_paths(self):
        config = WorkConfig(1, 20, 3, 3, {}, ("src/**",), ("**/*.key",))
        validate_scope(["src/app.py"], config)
        with self.assertRaisesRegex(ValueError, "Forbidden"):
            validate_scope(["src/signing.key"], config)
        with self.assertRaisesRegex(ValueError, "Out-of-scope"):
            validate_scope(["README.md"], config)

    def test_scope_violation_preserves_multiple_normalized_paths(self):
        config = WorkConfig(1, 20, 3, 3, {}, ("src/**",), ("**/*.key",))
        with self.assertRaises(ScopeViolation) as raised:
            validate_scope(["build/one/", "build/two.txt"], config)
        self.assertEqual(raised.exception.category, "outside")
        self.assertEqual(raised.exception.paths, ("build/one", "build/two.txt"))

    def test_agent_work_runtime_state_does_not_make_tree_dirty(self):
        subprocess.run(
            ["git", "switch", "-q", "-c", "feature/test"], cwd=self.repo, check=True
        )
        (self.repo / ".agent-work" / "run").mkdir(parents=True)
        (self.repo / ".agent-work" / "run" / "log").write_text("x", encoding="utf-8")
        self.assertEqual(git_utils.changed_paths(self.repo), [])

    def test_review_exception_secrets_are_redacted_at_persistence_boundary(self):
        secrets = (
            "token=token-value-123 password=hunter2 "
            "Authorization: Bearer bearer-value-456 sk-abcdefghijklmnopqrstuv"
        )
        safe = safe_error_detail(RuntimeError(secrets + "\x01"))
        for value in ("token-value-123", "hunter2", "bearer-value-456", "sk-"):
            self.assertNotIn(value, safe)
        self.assertIn("RuntimeError", safe)

        path = self.repo / ".agent-work" / "007" / "events.jsonl"
        store = EventStore(path)
        store.append(
            feature="007",
            repository=str(self.repo),
            branch="feature/test",
            worktree=str(self.repo),
            phase="review",
            kind="review-shard",
            result="INVALID",
            head_sha="abc",
            detail=secrets,
            data={"error": secrets, "diagnostic": {"stderr_tail": secrets}},
        )
        persisted = path.read_text(encoding="utf-8")
        for value in ("token-value-123", "hunter2", "bearer-value-456", "sk-"):
            self.assertNotIn(value, persisted)

    def test_timeout_diagnostic_uses_same_recursive_redaction(self):
        value = redact_value(
            {"stderr_tail": "password=hidden", "nested": ["token=hidden-token"]}
        )
        self.assertNotIn("hidden", str(value))

    def test_non_timeout_review_failure_persists_only_allowlisted_metadata(self):
        path = self.repo / ".agent-work" / "007" / "events.jsonl"
        store = EventStore(path)
        secret = "arbitrary reviewer output token=do-not-persist"
        event = record_review_failure_event(
            store,
            feature="007",
            repository=str(self.repo),
            branch="feature/test",
            worktree=str(self.repo),
            head_sha="abc",
            shard="security",
            identity=SimpleNamespace(digest="identity-digest"),
            attempt=1,
            error=RuntimeError(secret),
        )
        persisted = path.read_text(encoding="utf-8")
        self.assertEqual(event.result, "INVALID")
        self.assertEqual(event.detail, "RuntimeError")
        self.assertEqual(event.data["error_class"], "RuntimeError")
        self.assertEqual(event.data["diagnostic"], {})
        self.assertNotIn("error", event.data)
        self.assertNotIn("arbitrary reviewer output", persisted)
        self.assertNotIn("do-not-persist", persisted)

    def test_command_failure_is_redacted_before_exception_exposure(self):
        unsafe = (
            "token=token-value password=hunter2 "
            "Authorization: Bearer bearer-value sk-abcdefghijklmnopqrstuv"
        )
        message = str(_safe_command_failure("validation failed", unsafe))
        for secret in ("token-value", "hunter2", "bearer-value", "sk-"):
            self.assertNotIn(secret, message)
        self.assertIn("validation failed", message)
