from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
            forbidden=(".agent-work/**", ".agent-worktrees/**"),
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
        }

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
            "a.py a.py",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery_patch.parse_approved_paths(value)

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


if __name__ == "__main__":
    unittest.main()
