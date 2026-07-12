import subprocess
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent import git_utils
from agent.parser import WorkConfig
from agent.validation import validate_scope


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_main_is_rejected(self):
        with self.assertRaises(git_utils.GitError):
            git_utils.ensure_safe_start(self.repo)

    def test_dirty_feature_branch_is_rejected(self):
        subprocess.run(["git", "switch", "-q", "-c", "feature/test"], cwd=self.repo, check=True)
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

    def test_agent_work_runtime_state_does_not_make_tree_dirty(self):
        subprocess.run(["git", "switch", "-q", "-c", "feature/test"], cwd=self.repo, check=True)
        (self.repo / ".agent-work" / "run").mkdir(parents=True)
        (self.repo / ".agent-work" / "run" / "log").write_text("x", encoding="utf-8")
        self.assertEqual(git_utils.changed_paths(self.repo), [])
