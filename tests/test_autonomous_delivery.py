import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent import delivery as delivery_module
from agent import git_utils, state, worktree
from agent.github_delivery import GitHubDelivery, checks_with_repairs
from agent.parser import Task


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.pr_exists = False

    def __call__(self, command, cwd):
        self.commands.append(command)
        if command[:3] == ["gh", "pr", "list"]:
            value = (
                [{"number": 7, "url": "https://example/pr/7", "state": "OPEN"}]
                if self.pr_exists
                else []
            )
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        if command[:3] == ["gh", "pr", "create"]:
            self.pr_exists = True
            return subprocess.CompletedProcess(command, 0, "https://example/pr/7\n", "")
        if command[:3] == ["gh", "pr", "checks"]:
            return subprocess.CompletedProcess(command, 0, '[{"state":"SUCCESS"}]', "")
        if command[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(command, 0, '{"headRefOid":"sha"}', "")
        if command[:3] == ["gh", "run", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                '[{"databaseId":9,"headSha":"sha","status":"completed","conclusion":"failure"}]',
                "",
            )
        return subprocess.CompletedProcess(command, 0, "", "")


class DeliveryTests(unittest.TestCase):
    def _resumable_repo(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        feature = repo / "specs" / "008-test"
        feature.mkdir(parents=True)
        (repo / ".gitignore").write_text(
            ".agent-work/\n.agent-worktrees/\n", encoding="utf-8"
        )
        for name in ("spec.md", "plan.md"):
            (feature / name).write_text(name + "\n", encoding="utf-8")
        (feature / "tasks.md").write_text(
            "- [ ] T001: Test\n  - Requirements: REQ-001\n  - Validation: unit\n",
            encoding="utf-8",
        )
        (feature / "validation.toml").write_text("version=2\n", encoding="utf-8")
        (feature / "validation-log.md").write_text("log\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
        isolated = worktree.create(repo, "008-test", "main")
        subprocess.run(
            ["git", "switch", "-q", "-c", "feature/root"], cwd=repo, check=True
        )
        task = Task("T001", "Test", False, ("REQ-001",), ("unit",), 0)
        config = SimpleNamespace(commands={"unit": ("make", "test")})
        head = git_utils.run_git(isolated.path, ["rev-parse", "HEAD"]).stdout.strip()
        saved = state.RunState(
            1,
            "008-test",
            isolated.branch,
            head,
            head,
            state.contract_digest(isolated.path / "specs" / "008-test"),
            "T001",
            1,
            "implement",
            "unit-test",
            (),
            "failed",
            str(isolated.path),
            "now",
        )
        state.write_state(repo / ".agent-work" / "008-test" / "state.json", saved)
        return temporary, repo, isolated, config, task, saved

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
            self.assertEqual(
                sum(
                    command[:3] == ["gh", "pr", "create"] for command in runner.commands
                ),
                1,
            )
            self.assertTrue(delivery.checks(7))
            delivery.merge(7)
            self.assertIn(
                ["gh", "pr", "merge", "7", "--merge", "--delete-branch"],
                runner.commands,
            )

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
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps([{"state": state}]), ""
                    )
                if command[:3] == ["gh", "run", "view"]:
                    return subprocess.CompletedProcess(
                        command, 0, "test failed once", ""
                    )
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
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps([{"state": state}]), ""
                    )
                return super().__call__(command, cwd)

        github = GitHubDelivery(Path("."), PendingRunner())
        repairs = []
        self.assertTrue(
            checks_with_repairs(github, 7, repairs.append, 3, sleep=lambda _: None)
        )
        self.assertEqual(repairs, [])

    def test_checks_are_pending_before_github_registers_jobs(self):
        class EmptyRunner(FakeRunner):
            def __call__(self, command, cwd):
                if command[:3] == ["gh", "pr", "checks"]:
                    return subprocess.CompletedProcess(command, 0, "[]", "")
                return super().__call__(command, cwd)

        self.assertEqual(
            GitHubDelivery(Path("."), EmptyRunner()).check_state(7), "pending"
        )

    def test_framework_worktree_is_isolated_and_dirty_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
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
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            (repo / "base.txt").write_text("base", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
            isolated = worktree.create(repo, "013-clean", "main")
            worktree.remove_after_success(repo, isolated)
            self.assertFalse(isolated.path.exists())

    def test_state_aware_inspection_distinguishes_create_resume_and_complete(self):
        temporary, repo, isolated, config, task, saved = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            report = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertEqual(report["worktree_action"], "resume-existing-worktree")
            self.assertTrue(report["resume_safe"])
            self.assertEqual(report["state_failure_class"], "unit-test")
            self.assertEqual(report["pending_tasks"], ["T001"])
            self.assertTrue(report["root_start_safe"])
            self.assertTrue(report["worktree_path_match"])
            self.assertEqual(
                report["saved_worktree_path"], str(isolated.path.resolve())
            )
            state.write_state(
                repo / ".agent-work" / "008-test" / "state.json",
                state.RunState(**{**saved.__dict__, "status": "complete"}),
            )
            completed = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertEqual(completed["worktree_action"], "reuse-completed-worktree")
            self.assertTrue(completed["resume_safe"])
            (isolated.path / ".agent-worktree-owned").unlink()
            invalid = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(invalid["ownership_valid"])
            self.assertFalse(invalid["resume_safe"])

    def test_inspection_fails_closed_for_state_identity_mismatches(self):
        temporary, repo, _, config, task, saved = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            state_path = repo / ".agent-work" / "008-test" / "state.json"
            mutations = {
                "feature": "009-other",
                "branch": "agent/other",
                "head_commit": "0" * 40,
                "contract_digest": "bad",
                "changed_paths": ("unexpected.txt",),
                "worktree": str(repo / "missing-worktree"),
            }
            for field, value in mutations.items():
                with self.subTest(field=field):
                    state.write_state(
                        state_path, state.RunState(**{**saved.__dict__, field: value})
                    )
                    report = delivery_module.inspect_delivery_worktree(
                        repo, feature, config, [task]
                    )
                    self.assertFalse(report["resume_safe"])
                    self.assertTrue(report["blocking_reasons"])
            state_path.unlink()
            missing_state = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(missing_state["resume_safe"])
            self.assertEqual(
                missing_state["worktree_action"], "blocked-existing-worktree"
            )

    def test_worktree_path_match_rejects_alias_and_missing_path(self):
        temporary, repo, isolated, config, task, saved = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            state_path = repo / ".agent-work" / "008-test" / "state.json"
            alias = repo / ".agent-work" / "worktree-alias"
            alias.parent.mkdir(exist_ok=True)
            alias.symlink_to(isolated.path, target_is_directory=True)
            state.write_state(
                state_path,
                state.RunState(**{**saved.__dict__, "worktree": str(alias)}),
            )
            aliased = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(aliased["worktree_path_match"])
            self.assertFalse(aliased["resume_safe"])
            self.assertEqual(
                aliased["saved_worktree_path"], str(isolated.path.resolve())
            )
            self.assertEqual(aliased["saved_worktree_path_raw"], str(alias))

            state.write_state(state_path, saved)
            matched = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertTrue(matched["worktree_path_match"])
            self.assertTrue(matched["resume_safe"])
            self.assertEqual(
                matched["worktree_path"], str(isolated.path.resolve())
            )
            self.assertEqual(
                matched["expected_worktree_path"], str(isolated.path.resolve())
            )
            self.assertEqual(
                matched["saved_worktree_path"], str(isolated.path.resolve())
            )
            self.assertEqual(
                matched["saved_worktree_path_raw"], str(isolated.path)
            )

            state.write_state(
                state_path,
                state.RunState(
                    **{**saved.__dict__, "worktree": str(repo / "does-not-exist")}
                ),
            )
            missing = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(missing["worktree_path_match"])
            self.assertFalse(missing["resume_safe"])
            self.assertEqual(
                missing["saved_worktree_path"],
                str((repo / "does-not-exist").resolve(strict=False)),
            )
            self.assertTrue(
                any(
                    "another worktree" in reason
                    for reason in missing["blocking_reasons"]
                )
            )

    def test_inspection_reports_missing_contract_as_a_blocker(self):
        temporary, repo, isolated, config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            (isolated.path / "specs" / "008-test" / "plan.md").unlink()
            report = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(report["resume_safe"])
            self.assertFalse(report["contract_match"])
            self.assertEqual(report["worktree_action"], "blocked-existing-worktree")
            self.assertTrue(
                any(
                    "feature inspection failed" in reason
                    for reason in report["blocking_reasons"]
                )
            )

    def test_inspection_rejects_registered_worktree_with_missing_directory(self):
        temporary, repo, isolated, config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            moved = repo / "moved-worktree"
            isolated.path.rename(moved)
            report = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(report["worktree_exists"])
            self.assertFalse(report["resume_safe"])
            self.assertEqual(report["worktree_action"], "blocked-existing-worktree")
            self.assertTrue(
                any("registered" in reason for reason in report["blocking_reasons"])
            )

    def test_inspection_does_not_refresh_linked_worktree_index(self):
        temporary, repo, isolated, config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            index_path = Path(
                git_utils.run_git(
                    isolated.path, ["rev-parse", "--git-path", "index"]
                ).stdout.strip()
            )
            if not index_path.is_absolute():
                index_path = isolated.path / index_path
            before = (index_path.read_bytes(), index_path.stat().st_mtime_ns)
            delivery_module.inspect_delivery_worktree(repo, feature, config, [task])
            after = (index_path.read_bytes(), index_path.stat().st_mtime_ns)
            self.assertEqual(before, after)

    def test_dry_run_does_not_create_worktree_marker_or_runtime_state(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / "specs" / "008-test").mkdir(parents=True)
            task = Task("T001", "Test", False, ("REQ-001",), ("unit",), 0)
            config = SimpleNamespace(
                commands={"unit": ("make", "test")}, risk="high", auto_merge=False
            )
            before = {
                str(path.relative_to(repo)): path.read_bytes()
                for path in repo.rglob("*")
                if path.is_file()
            }
            before_head = git_utils.run_git(repo, ["rev-parse", "HEAD"], check=False)
            before_branch = git_utils.branch(repo)
            with (
                mock.patch.object(
                    delivery_module,
                    "require_lint",
                    return_value=SimpleNamespace(warnings=()),
                ),
                mock.patch.object(delivery_module, "load_config", return_value=config),
                mock.patch.object(delivery_module, "parse_tasks", return_value=[task]),
                mock.patch.object(delivery_module.worktree, "create") as create,
                mock.patch.object(delivery_module.validation, "run_named") as validate,
                mock.patch.object(delivery_module.review, "prepare_reviews") as reviewer,
                mock.patch.object(delivery_module, "GitHubDelivery") as github,
            ):
                result = delivery_module.dry_run(
                    repo, "008-test", SimpleNamespace(default_branch="main")
                )
            after = {
                str(path.relative_to(repo)): path.read_bytes()
                for path in repo.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertEqual(
                git_utils.run_git(repo, ["rev-parse", "HEAD"], check=False).stdout,
                before_head.stdout,
            )
            self.assertEqual(git_utils.branch(repo), before_branch)
            create.assert_not_called()
            validate.assert_not_called()
            reviewer.assert_not_called()
            github.assert_not_called()
            self.assertEqual(result["worktree_action"], "create-isolated-worktree")
            self.assertFalse((repo / ".agent-worktree-owned").exists())
            self.assertFalse((repo / ".agent-worktrees").exists())
            self.assertEqual(result["planned_remote_mutations"], [])
            self.assertEqual(
                result["deferred_remote_mutations"],
                ["push-feature-branch", "create-or-update-pr", "monitor-ci"],
            )
            self.assertEqual(
                result["remote_mutation_blocker"],
                "high-risk-pre-push-approval",
            )

    def test_resume_dry_run_preserves_linked_worktree_and_runtime_evidence(self):
        temporary, repo, isolated, base_config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            events = repo / ".agent-work" / "008-test" / "events.jsonl"
            events.write_text('{"event":"existing"}\n', encoding="utf-8")
            config = SimpleNamespace(
                commands=base_config.commands, risk="high", auto_merge=False
            )

            def snapshot():
                roots = (repo / ".git", repo / ".agent-work", isolated.path)
                files = {}
                for root in roots:
                    for path in root.rglob("*"):
                        if path.is_file() and not path.is_symlink():
                            key = f"{root.relative_to(repo)}::{path.relative_to(root)}"
                            files[key] = (path.read_bytes(), path.stat().st_mtime_ns)
                return {
                    "files": files,
                    "root_head": git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout,
                    "root_branch": git_utils.branch(repo),
                    "worktree_head": git_utils.run_git(
                        isolated.path, ["rev-parse", "HEAD"]
                    ).stdout,
                    "worktree_branch": git_utils.branch(isolated.path),
                }

            before = snapshot()
            with (
                mock.patch.object(
                    delivery_module,
                    "require_lint",
                    return_value=SimpleNamespace(warnings=()),
                ),
                mock.patch.object(delivery_module, "load_config", return_value=config),
                mock.patch.object(delivery_module, "parse_tasks", return_value=[task]),
                mock.patch.object(delivery_module.worktree, "create") as create,
                mock.patch.object(delivery_module.validation, "run_named") as validate,
                mock.patch.object(delivery_module.review, "prepare_reviews") as reviewer,
                mock.patch.object(delivery_module, "GitHubDelivery") as github,
            ):
                result = delivery_module.dry_run(
                    repo, feature.name, SimpleNamespace(default_branch="main")
                )
            self.assertEqual(snapshot(), before)
            self.assertEqual(result["worktree_action"], "resume-existing-worktree")
            self.assertTrue(result["resume_safe"])
            create.assert_not_called()
            validate.assert_not_called()
            reviewer.assert_not_called()
            github.assert_not_called()

    def test_public_delivery_entrypoints_share_worktree_inspection(self):
        temporary, repo, _, config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            dry_config = SimpleNamespace(
                commands=config.commands, risk="high", auto_merge=False
            )
            sentinel = {
                "worktree_action": "blocked-existing-worktree",
                "worktree_exists": True,
                "resume_safe": False,
                "blocking_reasons": ["sentinel inspection blocker"],
            }
            policy = SimpleNamespace(default_branch="main")
            with (
                mock.patch.object(
                    delivery_module,
                    "require_lint",
                    return_value=SimpleNamespace(warnings=()),
                ),
                mock.patch.object(
                    delivery_module, "load_config", return_value=dry_config
                ),
                mock.patch.object(delivery_module, "parse_tasks", return_value=[task]),
                mock.patch.object(
                    delivery_module,
                    "inspect_delivery_worktree",
                    return_value=sentinel,
                ) as inspect,
            ):
                report = delivery_module.dry_run(repo, feature.name, policy)
            self.assertEqual(
                {key: report[key] for key in sentinel},
                sentinel,
            )
            inspect.assert_called_once_with(
                repo, feature, dry_config, [task], policy.default_branch
            )

            work_function = mock.Mock()
            github_factory = mock.Mock()
            with (
                mock.patch.object(delivery_module.git_utils, "ensure_safe_start"),
                mock.patch.object(delivery_module, "require_lint"),
                mock.patch.object(
                    delivery_module, "load_config", return_value=dry_config
                ),
                mock.patch.object(delivery_module, "parse_tasks", return_value=[task]),
                mock.patch.object(
                    delivery_module,
                    "inspect_delivery_worktree",
                    return_value=sentinel,
                ) as inspect,
                mock.patch.object(delivery_module.worktree, "create") as create,
            ):
                with self.assertRaisesRegex(RuntimeError, "sentinel inspection blocker"):
                    delivery_module.deliver(
                        repo, feature.name, policy, work_function, github_factory
                    )
            inspect.assert_called_once_with(
                repo, feature, dry_config, [task], policy.default_branch
            )
            create.assert_not_called()
            work_function.assert_not_called()
            github_factory.assert_not_called()

    def test_ownership_helper_requires_registration_and_matching_marker(self):
        temporary, repo, isolated, _, _, _ = self._resumable_repo()
        with temporary:
            self.assertTrue(
                worktree.owns_registered_worktree(repo, isolated.path, "008-test")
            )
            self.assertFalse(
                worktree.owns_registered_worktree(repo, isolated.path, "009-other")
            )
            self.assertFalse(
                worktree.owns_registered_worktree(repo, repo, "008-test")
            )

    def test_marker_writer_rejects_repository_root_and_accepts_linked_worktree(self):
        temporary, repo, isolated, _, _, _ = self._resumable_repo()
        with temporary:
            with self.assertRaisesRegex(ValueError, "unregistered isolated"):
                worktree.write_ownership_marker(repo, repo, "008-test")
            marker = isolated.path / ".agent-worktree-owned"
            marker.unlink()
            worktree.write_ownership_marker(repo, isolated.path, "008-test")
            self.assertEqual(marker.read_text(encoding="utf-8"), "008-test\n")
            self.assertFalse((repo / ".agent-worktree-owned").exists())

            alias = repo / ".agent-worktrees" / "009-alias"
            alias.symlink_to(isolated.path, target_is_directory=True)
            before = marker.read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unregistered isolated"):
                worktree.write_ownership_marker(repo, alias, "009-alias")
            self.assertEqual(marker.read_text(encoding="utf-8"), before)

            external = repo / "external-marker-target"
            external.write_text("do-not-overwrite\n", encoding="utf-8")
            marker.unlink()
            marker.symlink_to(external)
            with self.assertRaisesRegex(ValueError, "existing ownership marker"):
                worktree.write_ownership_marker(repo, isolated.path, "008-test")
            self.assertEqual(external.read_text(encoding="utf-8"), "do-not-overwrite\n")
            inspected = delivery_module.inspect_delivery_worktree(
                repo,
                repo / "specs" / "008-test",
                SimpleNamespace(commands={"unit": ("make", "test")}),
                [],
            )
            self.assertFalse(inspected["ownership_valid"])
            self.assertTrue(
                any("unreadable" in reason for reason in inspected["blocking_reasons"])
            )

            marker.unlink()
            os.link(external, marker)
            hardlinked = delivery_module.inspect_delivery_worktree(
                repo,
                repo / "specs" / "008-test",
                SimpleNamespace(commands={"unit": ("make", "test")}),
                [],
            )
            self.assertFalse(hardlinked["ownership_valid"])
            self.assertIsNone(hardlinked["marker_feature"])
            self.assertNotIn("do-not-overwrite", str(hardlinked))

    def test_create_rejects_symlinked_worktree_container(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            external = Path(directory) / "external"
            repo.mkdir()
            external.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / ".agent-worktrees").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe worktree container"):
                worktree.create(repo, "008-test", "main")
            self.assertEqual(list(external.iterdir()), [])

    def test_inspection_rejects_unregistered_directory_and_unreadable_marker(self):
        temporary, repo, isolated, config, task, _ = self._resumable_repo()
        with temporary:
            feature = repo / "specs" / "008-test"
            marker = isolated.path / ".agent-worktree-owned"
            marker.write_bytes(b"\xff")
            unreadable = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(unreadable["resume_safe"])
            self.assertTrue(
                any("unreadable" in reason for reason in unreadable["blocking_reasons"])
            )

            subprocess.run(
                ["git", "worktree", "remove", "--force", str(isolated.path)],
                cwd=repo,
                check=True,
            )
            isolated.path.mkdir(parents=True)
            (isolated.path / ".agent-worktree-owned").write_text(
                "008-test\n", encoding="utf-8"
            )
            unregistered = delivery_module.inspect_delivery_worktree(
                repo, feature, config, [task]
            )
            self.assertFalse(unregistered["resume_safe"])
            self.assertTrue(
                any(
                    "not a registered" in reason
                    for reason in unregistered["blocking_reasons"]
                )
            )
