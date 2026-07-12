import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent.github_delivery import GitHubDelivery, checks_with_repairs
from agent import worktree


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.pr_exists = False

    def __call__(self, command, cwd):
        self.commands.append(command)
        if command[:3] == ["gh", "pr", "list"]:
            value = [{"number": 7, "url": "https://example/pr/7", "state": "OPEN"}] if self.pr_exists else []
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        if command[:3] == ["gh", "pr", "create"]:
            self.pr_exists = True
            return subprocess.CompletedProcess(command, 0, "https://example/pr/7\n", "")
        if command[:3] == ["gh", "pr", "checks"]:
            return subprocess.CompletedProcess(command, 0, '[{"state":"SUCCESS"}]', "")
        if command[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(command, 0, '{"headRefOid":"sha"}', "")
        if command[:3] == ["gh", "run", "list"]:
            return subprocess.CompletedProcess(command, 0,
                '[{"databaseId":9,"headSha":"sha","status":"completed","conclusion":"failure"}]', "")
        return subprocess.CompletedProcess(command, 0, "", "")


class DeliveryTests(unittest.TestCase):
    def test_pr_is_created_once_then_reused_and_merge_uses_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            body = repo / "body.md"
            body.write_text("body", encoding="utf-8")
            runner = FakeRunner()
            delivery = GitHubDelivery(repo, runner)
            first = delivery.ensure_pr("feature/test", "Title", body)
            second = delivery.ensure_pr("feature/test", "Title", body)
            self.assertEqual(first.number, second.number)
            self.assertEqual(sum(command[:3] == ["gh", "pr", "create"] for command in runner.commands), 1)
            self.assertTrue(delivery.checks(7))
            delivery.merge(7)
            self.assertIn(["gh", "pr", "merge", "7", "--merge", "--delete-branch"], runner.commands)

    def test_default_branch_push_is_forbidden(self):
        delivery = GitHubDelivery(Path("."), FakeRunner())
        with self.assertRaises(ValueError):
            delivery.push("main")

    def test_ci_repair_is_bounded_and_then_passes(self):
        class RepairingRunner(FakeRunner):
            def __init__(self):
                super().__init__()
                self.check_count = 0
            def __call__(self, command, cwd):
                if command[:3] == ["gh", "pr", "checks"]:
                    self.check_count += 1
                    state = "FAILURE" if self.check_count == 1 else "SUCCESS"
                    return subprocess.CompletedProcess(command, 0, json.dumps([{"state": state}]), "")
                if command[:3] == ["gh", "run", "view"]:
                    return subprocess.CompletedProcess(command, 0, "test failed once", "")
                return super().__call__(command, cwd)
        runner = RepairingRunner()
        github = GitHubDelivery(Path("."), runner)
        repairs = []
        self.assertTrue(checks_with_repairs(github, 7, repairs.append, 3))
        self.assertEqual(repairs, ["test failed once"])

    def test_pending_ci_is_polled_without_repair(self):
        class PendingRunner(FakeRunner):
            def __init__(self):
                super().__init__()
                self.count = 0
            def __call__(self, command, cwd):
                if command[:3] == ["gh", "pr", "checks"]:
                    self.count += 1
                    state = "PENDING" if self.count == 1 else "SUCCESS"
                    return subprocess.CompletedProcess(command, 0, json.dumps([{"state": state}]), "")
                return super().__call__(command, cwd)
        github = GitHubDelivery(Path("."), PendingRunner())
        repairs = []
        self.assertTrue(checks_with_repairs(github, 7, repairs.append, 3, sleep=lambda _: None))
        self.assertEqual(repairs, [])

    def test_checks_are_pending_before_github_registers_jobs(self):
        class EmptyRunner(FakeRunner):
            def __call__(self, command, cwd):
                if command[:3] == ["gh", "pr", "checks"]:
                    return subprocess.CompletedProcess(command, 0, "[]", "")
                return super().__call__(command, cwd)
        self.assertEqual(GitHubDelivery(Path("."), EmptyRunner()).check_state(7), "pending")

    def test_framework_worktree_is_isolated_and_dirty_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "base.txt").write_text("base", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            isolated = worktree.create(repo, "012-test", "main")
            self.assertTrue((isolated.path / ".agent-worktree-owned").is_file())
            (isolated.path / "dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "dirty"):
                worktree.remove_after_success(repo, isolated)
            self.assertTrue(isolated.path.exists())

    def test_clean_framework_worktree_can_be_explicitly_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "base.txt").write_text("base", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            isolated = worktree.create(repo, "013-clean", "main")
            worktree.remove_after_success(repo, isolated)
            self.assertFalse(isolated.path.exists())
