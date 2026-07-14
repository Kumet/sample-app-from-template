from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery, git_utils, recovery_patch, state, worktree
from agent.events import EventStore
from agent.parser import Task


class RecoveryPatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.repo.mkdir()
        self._git(self.repo, "init", "-q", "-b", "main")
        self._git(self.repo, "config", "user.email", "test@example.invalid")
        self._git(self.repo, "config", "user.name", "Test")
        self.feature_name = "014-test"
        self.feature_dir = self.repo / "specs" / self.feature_name
        self.feature_dir.mkdir(parents=True)
        (self.repo / ".gitignore").write_text(
            ".agent-work/\n.agent-worktrees/\n", encoding="utf-8"
        )
        (self.feature_dir / "spec.md").write_text("spec\n", encoding="utf-8")
        (self.feature_dir / "plan.md").write_text("plan\n", encoding="utf-8")
        (self.feature_dir / "tasks.md").write_text(
            "- [ ] T001: Recover\n"
            "  - Requirements: REQ-001\n"
            "  - Validation: unit\n",
            encoding="utf-8",
        )
        (self.feature_dir / "validation.toml").write_text(
            "version = 2\n", encoding="utf-8"
        )
        (self.feature_dir / "validation-log.md").write_text(
            "log\n", encoding="utf-8"
        )
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        self._git(self.repo, "add", ".")
        self._git(self.repo, "commit", "-q", "-m", "base")
        self.isolated = worktree.create(self.repo, self.feature_name, "main")
        self._git(self.repo, "switch", "-q", "-c", "feature/root")
        (self.isolated.path / "existing.py").write_text(
            "existing = True\n", encoding="utf-8"
        )
        head = git_utils.run_git(
            self.isolated.path, ["rev-parse", "HEAD"]
        ).stdout.strip()
        self.state_path = (
            self.repo / ".agent-work" / self.feature_name / "state.json"
        )
        state.write_state(
            self.state_path,
            state.RunState(
                1,
                self.feature_name,
                self.isolated.branch,
                head,
                head,
                state.contract_digest(
                    self.isolated.path / "specs" / self.feature_name
                ),
                "T002",
                2,
                "validate",
                "format-check",
                ("existing.py",),
                "failed",
                str(self.isolated.path),
                "2026-07-14T00:00:00+00:00",
            ),
        )
        self.config = SimpleNamespace(
            commands={"unit": ("make", "test")},
            allowed=("*.py",),
            forbidden=(".env", ".agent-work/**", ".agent-worktrees/**"),
        )
        self.task = Task("T001", "Recover", False, ("REQ-001",), ("unit",), 0)

    def tearDown(self):
        self.temporary.cleanup()

    def _git(self, repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def _add_recovery(self, content: str = "recovered = True\n") -> Path:
        path = self.isolated.path / "recovery.py"
        path.write_text(content, encoding="utf-8")
        return path

    def _artifact_fingerprint(self) -> dict:
        index = Path(
            git_utils.run_git(
                self.isolated.path, ["rev-parse", "--git-path", "index"]
            ).stdout.strip()
        )
        if not index.is_absolute():
            index = self.isolated.path / index
        events = self.state_path.with_name("events.jsonl")
        marker = self.isolated.path / ".agent-worktree-owned"
        return {
            "head": self._git(self.isolated.path, "rev-parse", "HEAD"),
            "branch": self._git(self.isolated.path, "branch", "--show-current"),
            "status": self._git(
                self.isolated.path, "status", "--porcelain=v1", "--untracked-files=all"
            ),
            "state": self.state_path.read_bytes(),
            "events": events.read_bytes() if events.exists() else None,
            "marker": marker.read_bytes(),
            "index": hashlib.sha256(index.read_bytes()).hexdigest(),
            "worktree_files": self._worktree_file_fingerprint(),
        }

    def _worktree_file_fingerprint(self) -> dict[str, str]:
        values = {}
        for path in sorted(self.isolated.path.rglob("*")):
            relative = str(path.relative_to(self.isolated.path))
            if relative == ".git" or path.is_dir():
                continue
            values[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return values

    def test_preview_is_non_mutating_and_binds_complete_recovery(self):
        self._add_recovery()
        before = self._artifact_fingerprint()
        result = recovery_patch.preview(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        after = self._artifact_fingerprint()

        self.assertEqual(before, after)
        self.assertTrue(result["can_apply"])
        self.assertEqual(result["approved_paths"], ("recovery.py",))
        self.assertEqual(
            result["current_changed_paths"], ("existing.py", "recovery.py")
        )
        self.assertTrue(result["ownership_valid"])
        self.assertTrue(result["head_match"])
        self.assertTrue(result["contract_match"])
        self.assertEqual(len(result["diff_digest"]), 64)

    def test_apply_records_evidence_and_makes_delivery_resume_safe(self):
        self._add_recovery()
        result = recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        saved = state.read_state(self.state_path)
        events = EventStore(self.state_path.with_name("events.jsonl")).read()

        self.assertEqual(saved.changed_paths, ("existing.py", "recovery.py"))
        self.assertEqual(saved.recovery_event_sequence, 1)
        self.assertEqual(saved.recovery_diff_digest, result["diff_digest"])
        self.assertEqual(
            [(event.kind, event.result) for event in events],
            [
                ("recovery-patch-approved", "PASS"),
                ("recovery-patch-applied", "PASS"),
            ],
        )
        approval = events[0]
        for field in (
            "saved_head",
            "current_head",
            "contract_digest",
            "branch",
            "worktree",
            "prior_changed_paths",
            "approved_paths",
            "current_changed_paths",
            "diff_digest",
            "ownership_valid",
        ):
            self.assertIn(field, approval.data)
        inspection = delivery.inspect_delivery_worktree(
            self.repo,
            self.feature_dir,
            self.config,
            [self.task],
            "main",
        )
        self.assertTrue(inspection["resume_safe"], inspection["blocking_reasons"])
        self.assertTrue(inspection["recovery_evidence_valid"])
        self.assertEqual(
            inspection["worktree_action"], "resume-existing-worktree"
        )

    def test_post_approval_content_or_index_change_fails_closed(self):
        path = self._add_recovery()
        recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        path.write_text("recovered = False\n", encoding="utf-8")
        inspection = delivery.inspect_delivery_worktree(
            self.repo, self.feature_dir, self.config, [self.task], "main"
        )
        self.assertFalse(inspection["resume_safe"])
        self.assertIn(
            "recovery diff changed after approval", inspection["blocking_reasons"]
        )

        path.write_text("recovered = True\n", encoding="utf-8")
        self._git(self.isolated.path, "add", "--", "recovery.py")
        inspection = delivery.inspect_delivery_worktree(
            self.repo, self.feature_dir, self.config, [self.task], "main"
        )
        self.assertFalse(inspection["resume_safe"])
        self.assertIn(
            "recovery diff changed after approval", inspection["blocking_reasons"]
        )

    def test_unapproved_scope_contract_head_and_ownership_changes_are_rejected(self):
        self._add_recovery()
        (self.isolated.path / "extra.py").write_text("extra = True\n", encoding="utf-8")
        report = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("recovery.py",)
        )
        self.assertFalse(report.can_apply)
        self.assertIn(
            "approved paths do not exactly match newly changed paths",
            report.blocking_reasons,
        )
        (self.isolated.path / "extra.py").unlink()

        forbidden = SimpleNamespace(
            commands=self.config.commands,
            allowed=("existing.py",),
            forbidden=("recovery.py",),
        )
        with self.assertRaisesRegex(ValueError, "Forbidden files changed"):
            recovery_patch.inspect(
                self.repo, self.feature_dir, forbidden, ("recovery.py",)
            )

        (self.isolated.path / "specs" / self.feature_name / "spec.md").write_text(
            "changed contract\n", encoding="utf-8"
        )
        report = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("recovery.py",)
        )
        self.assertIn("feature contract differs from saved state", report.blocking_reasons)

        (self.isolated.path / "specs" / self.feature_name / "spec.md").write_text(
            "spec\n", encoding="utf-8"
        )
        self._git(self.isolated.path, "add", "base.txt")
        (self.isolated.path / "base.txt").write_text("new base\n", encoding="utf-8")
        self._git(self.isolated.path, "add", "base.txt")
        self._git(self.isolated.path, "commit", "-q", "-m", "head changed")
        report = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("recovery.py",)
        )
        self.assertIn("worktree HEAD differs from saved state", report.blocking_reasons)

        marker = self.isolated.path / ".agent-worktree-owned"
        marker.unlink()
        marker.symlink_to(self.isolated.path / "base.txt")
        report = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("recovery.py",)
        )
        self.assertIn("worktree ownership is invalid", report.blocking_reasons)

    def test_path_parser_rejects_globs_runtime_paths_and_duplicates(self):
        self.assertEqual(
            recovery_patch.parse_approved_paths("b.py a.py"), ("a.py", "b.py")
        )
        for value in (
            "",
            "../x.py",
            "/x.py",
            "*.py",
            ".agent-work/state.json",
            "nested/.agent-work/state.json",
            "nested/.agent-worktrees/014-test/file.py",
            "nested/.agent-worktree-owned",
            "nested/.env.production",
            "nested/private.pem",
            "nested/.ssh/config",
            "nested/credentials.json",
            "nested/secrets.toml",
            "configs/credentials/token.txt",
            "tmp/secrets/value.txt",
            "nested/.credentials/value.txt",
            "nested/.secrets/value.txt",
            "nested/private-keys/value.txt",
            "nested/private_keys/value.txt",
            "nested/api-keys/value.txt",
            "nested/api_keys/value.txt",
            "nested/tokens/value.txt",
            "nested/id_rsa",
            "nested/ID_DSA",
            "nested/id_ecdsa",
            "nested/ID_ED25519",
            "nested/authorized_keys",
            "nested/AUTHORIZED_KEYS",
            "nested/.htpasswd",
            "nested/.PGPASS",
            "nested/private.jks",
            "nested/PRIVATE.KEYSTORE",
            "a.py a.py",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery_patch.parse_approved_paths(value)

    def test_command_path_rejects_secret_and_runtime_paths(self):
        with self.assertRaisesRegex(ValueError, "Sensitive paths cannot be approved"):
            recovery_patch.parse_approved_paths(".env")
        with self.assertRaisesRegex(ValueError, "Runtime paths cannot be approved"):
            recovery_patch.parse_approved_paths(".agent-work/state.json")

    def test_existing_saved_path_and_committed_recovery_are_not_approvable(self):
        existing = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("existing.py",)
        )
        self.assertFalse(existing.can_apply)
        self.assertIn(
            "approved paths do not exactly match newly changed paths",
            existing.blocking_reasons,
        )

        self._add_recovery()
        self._git(self.isolated.path, "add", "--", "recovery.py")
        self._git(
            self.isolated.path,
            "commit",
            "-q",
            "-m",
            "committed recovery before approval",
        )
        committed = recovery_patch.inspect(
            self.repo, self.feature_dir, self.config, ("recovery.py",)
        )
        self.assertFalse(committed.can_apply)
        self.assertIn(
            "worktree HEAD differs from saved state", committed.blocking_reasons
        )
        self.assertIn(
            "approved paths do not exactly match newly changed paths",
            committed.blocking_reasons,
        )

    def test_sensitive_saved_path_is_rejected_before_diff_or_file_io(self):
        sensitive = "configs/credentials/token.py"
        with (
            mock.patch.object(recovery_patch, "_run_git_bytes") as git_diff,
            mock.patch.object(Path, "lstat") as lstat,
            mock.patch.object(Path, "open") as file_open,
        ):
            with self.assertRaisesRegex(
                ValueError, "Sensitive paths cannot be approved"
            ):
                recovery_patch.diff_digest(
                    self.isolated.path, ("existing.py", sensitive)
                )
        git_diff.assert_not_called()
        lstat.assert_not_called()
        file_open.assert_not_called()

        self._add_recovery()
        saved = state.read_state(self.state_path)
        state.write_state(
            self.state_path,
            replace(saved, changed_paths=("existing.py", sensitive)),
        )
        original_lstat = Path.lstat
        original_open = Path.open

        def guarded_lstat(path, *args, **kwargs):
            if sensitive in str(path):
                raise AssertionError("sensitive path reached lstat")
            return original_lstat(path, *args, **kwargs)

        def guarded_open(path, *args, **kwargs):
            if sensitive in str(path):
                raise AssertionError("sensitive path reached open")
            return original_open(path, *args, **kwargs)

        with (
            mock.patch.object(
                recovery_patch.git_utils,
                "changed_paths_read_only",
                return_value=["existing.py", sensitive, "recovery.py"],
            ),
            mock.patch.object(recovery_patch, "_run_git_bytes") as git_diff,
            mock.patch.object(recovery_patch, "resolve_feature") as resolve,
            mock.patch.object(recovery_patch, "contract_digest") as contract,
            mock.patch.object(
                recovery_patch.validation,
                "validate_scope",
                wraps=recovery_patch.validation.validate_scope,
            ) as scope,
            mock.patch.object(Path, "lstat", new=guarded_lstat),
            mock.patch.object(Path, "open", new=guarded_open),
        ):
            report = recovery_patch.inspect(
                self.repo, self.feature_dir, self.config, ("recovery.py",)
            )
        self.assertFalse(report.can_apply)
        self.assertIn(
            "current changed path rejected: Sensitive paths cannot be approved as recovery paths",
            report.blocking_reasons,
        )
        self.assertEqual(report.current_changed_paths, ())
        git_diff.assert_not_called()
        resolve.assert_not_called()
        contract.assert_not_called()
        self.assertEqual(scope.call_count, 1)

    def test_apply_reinspects_after_approval_event_before_state_mutation(self):
        recovery = self._add_recovery()
        original_state = self.state_path.read_bytes()
        original_append = EventStore.append

        def append_then_change(store, **kwargs):
            event = original_append(store, **kwargs)
            if kwargs["kind"] == "recovery-patch-approved":
                recovery.write_text("changed after approval\n", encoding="utf-8")
            return event

        with mock.patch.object(EventStore, "append", new=append_then_change):
            with self.assertRaisesRegex(
                ValueError, "changed after approval evidence was recorded"
            ):
                recovery_patch.apply(
                    self.repo,
                    self.feature_dir,
                    self.config,
                    ("recovery.py",),
                    "Human approved format-only recovery",
                )

        self.assertEqual(self.state_path.read_bytes(), original_state)
        events = EventStore(self.state_path.with_name("events.jsonl")).read()
        self.assertEqual(
            [(event.kind, event.result) for event in events],
            [("recovery-patch-approved", "PASS")],
        )

    def test_applied_event_failure_restores_state_and_allows_formal_retry(self):
        self._add_recovery()
        original_state = self.state_path.read_bytes()
        original_append = EventStore.append
        calls = 0

        def fail_applied(store, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected applied event failure")
            return original_append(store, **kwargs)

        with mock.patch.object(EventStore, "append", new=fail_applied):
            with self.assertRaisesRegex(OSError, "injected applied event failure"):
                recovery_patch.apply(
                    self.repo,
                    self.feature_dir,
                    self.config,
                    ("recovery.py",),
                    "Human approved format-only recovery",
                )

        self.assertEqual(self.state_path.read_bytes(), original_state)
        events = EventStore(self.state_path.with_name("events.jsonl")).read()
        self.assertEqual(
            [(event.kind, event.result) for event in events],
            [("recovery-patch-approved", "PASS")],
        )

        result = recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Retry the formally approved recovery",
        )
        self.assertEqual(result["approval_event_sequence"], 2)
        self.assertEqual(result["applied_event_sequence"], 3)
        retried = state.read_state(self.state_path)
        self.assertEqual(retried.recovery_event_sequence, 2)
        events = EventStore(self.state_path.with_name("events.jsonl")).read()
        self.assertEqual(
            [(event.kind, event.result) for event in events],
            [
                ("recovery-patch-approved", "PASS"),
                ("recovery-patch-approved", "PASS"),
                ("recovery-patch-applied", "PASS"),
            ],
        )

    def test_missing_or_tampered_evidence_fails_closed(self):
        self._add_recovery()
        recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        events_path = self.state_path.with_name("events.jsonl")
        records = events_path.read_text(encoding="utf-8").splitlines()
        records.pop()
        events_path.write_text("\n".join(records) + "\n", encoding="utf-8")
        inspection = delivery.inspect_delivery_worktree(
            self.repo, self.feature_dir, self.config, [self.task], "main"
        )
        self.assertFalse(inspection["resume_safe"])
        self.assertIn(
            "recovery state update lacks applied evidence",
            inspection["blocking_reasons"],
        )

    def test_applied_binding_and_state_binding_tampering_fail_closed(self):
        self._add_recovery()
        recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        events_path = self.state_path.with_name("events.jsonl")
        records = events_path.read_text(encoding="utf-8").splitlines()
        applied = json.loads(records[1])
        applied["data"]["diff_digest"] = "0" * 64
        records[1] = json.dumps(applied, sort_keys=True)
        events_path.write_text("\n".join(records) + "\n", encoding="utf-8")
        inspection = delivery.inspect_delivery_worktree(
            self.repo, self.feature_dir, self.config, [self.task], "main"
        )
        self.assertFalse(inspection["resume_safe"])
        self.assertIn(
            "recovery applied evidence does not match saved state",
            inspection["blocking_reasons"],
        )

        raw_state = json.loads(self.state_path.read_text(encoding="utf-8"))
        raw_state["recovery_event_sequence"] = True
        self.state_path.write_text(json.dumps(raw_state), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid recovery event sequence"):
            state.read_state(self.state_path)

    def test_removed_binding_is_rejected_but_legacy_and_later_state_are_allowed(self):
        legacy = state.read_state(self.state_path)
        self.assertEqual(
            recovery_patch.verify_active_evidence(
                self.repo,
                self.feature_dir,
                legacy,
                legacy.branch,
                legacy.head_commit,
                list(legacy.changed_paths),
            ),
            (),
        )

        self._add_recovery()
        recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "Human approved format-only recovery",
        )
        attributed = state.read_state(self.state_path)
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        raw.pop("recovery_event_sequence")
        raw.pop("recovery_diff_digest")
        self.state_path.write_text(json.dumps(raw), encoding="utf-8")
        removed = state.read_state(self.state_path)
        self.assertEqual(
            recovery_patch.verify_active_evidence(
                self.repo,
                self.feature_dir,
                removed,
                removed.branch,
                removed.head_commit,
                list(removed.changed_paths),
            ),
            ("saved recovery evidence binding was removed",),
        )

        incomplete = replace(attributed, recovery_diff_digest=None)
        self.assertEqual(
            recovery_patch.verify_active_evidence(
                self.repo,
                self.feature_dir,
                incomplete,
                incomplete.branch,
                incomplete.head_commit,
                list(incomplete.changed_paths),
            ),
            ("saved recovery evidence binding is incomplete",),
        )

        later = replace(
            attributed,
            updated_at="2026-07-14T23:59:59+00:00",
            recovery_event_sequence=None,
            recovery_diff_digest=None,
        )
        self.assertEqual(
            recovery_patch.verify_active_evidence(
                self.repo,
                self.feature_dir,
                later,
                later.branch,
                later.head_commit,
                list(later.changed_paths),
            ),
            (),
        )

    def test_reason_is_redacted_and_active_evidence_rechecks_worktree(self):
        self._add_recovery()
        recovery_patch.apply(
            self.repo,
            self.feature_dir,
            self.config,
            ("recovery.py",),
            "format recovery token=supersecretvalue",
        )
        events = EventStore(self.state_path.with_name("events.jsonl")).read()
        self.assertIn("token=[REDACTED]", events[0].detail)
        self.assertNotIn("supersecretvalue", events[0].detail)

        saved = state.read_state(self.state_path)
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        tampered = replace(saved, worktree=str(outside))
        with mock.patch.object(recovery_patch, "diff_digest") as digest:
            blockers = recovery_patch.verify_active_evidence(
                self.repo,
                self.feature_dir,
                tampered,
                tampered.branch,
                tampered.head_commit,
                list(tampered.changed_paths),
            )
        self.assertEqual(
            blockers, ("active recovery evidence names an invalid worktree",)
        )
        digest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
