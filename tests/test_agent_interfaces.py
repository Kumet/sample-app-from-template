import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent import codex_runner
from agent.parser import Task, WorkConfig
from agent.work import _execute_task, dry_run, status


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "feature/test"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        feature = self.repo / "specs" / "012-test"
        feature.mkdir(parents=True)
        for name in ("spec.md", "plan.md", "validation-log.md"):
            (feature / name).write_text(f"# {name}\n", encoding="utf-8")
        (feature / "tasks.md").write_text(
            "- [x] T001: done\n  - Validation: unit\n"
            "- [ ] T002: next\n  - Validation: unit\n",
            encoding="utf-8",
        )
        (feature / "validation.toml").write_text(
            'version=1\nmax_tasks=20\nmax_attempts_per_task=3\nmax_final_validation_attempts=3\n'
            '[commands]\nunit=["make","test"]\nfull=["make","validate"]\n'
            '[scope]\nallowed=["src/**"]\nforbidden=["**/*.key"]\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_is_read_only(self):
        before = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo, text=True, capture_output=True, check=True).stdout
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            dry_run(self.repo, "012")
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["next_task"], "T002")
        after = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo, text=True, capture_output=True, check=True).stdout
        self.assertEqual(before, after)
        self.assertFalse((self.repo / ".agent-work").exists())

    def test_status_is_read_only(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status(self.repo, "012-test")
        self.assertEqual(json.loads(output.getvalue())["completion_percent"], 50)
        self.assertFalse((self.repo / ".agent-work").exists())

    @mock.patch("agent.codex_runner.subprocess.run")
    def test_codex_uses_argument_array_and_safe_options(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        result = codex_runner.run(self.repo, "prompt")
        command = run.call_args.args[0]
        self.assertEqual(result.returncode, 0)
        self.assertIn("workspace-write", command)
        self.assertIn('approval_policy="never"', command)
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_retry_limits_are_bounded_by_config_model(self):
        config = WorkConfig(1, 20, 3, 3, {"unit": ("true",)}, ("src/**",), ("**/*.key",))
        self.assertLessEqual(config.max_attempts_per_task, 5)

    @mock.patch("agent.codex_runner.render_prompt", return_value="prompt")
    @mock.patch("agent.work._append_log")
    @mock.patch("agent.codex_runner.run")
    def test_identical_codex_failure_stops_after_two_attempts(self, run, _log, _prompt):
        run.return_value = codex_runner.CodexResult(1, "", "same failure")
        config = WorkConfig(
            1, 20, 5, 3, {"unit": ("true",)},
            ("specs/012-test/**",), ("**/*.key",),
        )
        feature = self.repo / "specs" / "012-test"
        task = Task("T002", "next", False, (), ("unit",), 1)
        run_dir = self.repo / ".agent-work" / "test"
        run_dir.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "Identical failure repeated"):
            _execute_task(self.repo, feature, config, task, run_dir)
        self.assertEqual(run.call_count, 2)
