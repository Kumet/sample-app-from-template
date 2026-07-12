import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent.parser import ContractError, mark_complete, parse_tasks, resolve_feature


class ParserTests(unittest.TestCase):
    def test_parses_completed_and_next_task(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text(
                "# Tasks\n\n- [x] T001: done\n  - Validation: unit\n"
                "- [ ] T002: next\n  - Requirements: REQ-2\n  - Validation: unit, full\n",
                encoding="utf-8",
            )
            tasks = parse_tasks(path, {"unit", "full"})
            self.assertTrue(tasks[0].completed)
            self.assertEqual(tasks[1].validations, ("unit", "full"))
            mark_complete(path, tasks[1])
            self.assertIn("- [x] T002:", path.read_text(encoding="utf-8"))

    def test_rejects_unknown_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text("- [ ] T001: task\n  - Validation: arbitrary command\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                parse_tasks(path, {"unit"})

    def test_rejects_empty_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.md"
            path.write_text("# Tasks\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                parse_tasks(path, {"unit"})

    def test_resolves_unique_feature_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "specs" / "012-one").mkdir(parents=True)
            self.assertEqual(resolve_feature(repo, "012").name, "012-one")
            (repo / "specs" / "012-two").mkdir()
            with self.assertRaises(ContractError):
                resolve_feature(repo, "012")
            with self.assertRaises(ContractError):
                resolve_feature(repo, "../../etc")
