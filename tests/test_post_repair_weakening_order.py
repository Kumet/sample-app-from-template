import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery, review, weakening
from agent.events import EventStore


class PostRepairWeakeningOrderTests(unittest.TestCase):
    feature = "016-post-repair-weakening-order"
    branch = "agent/016-post-repair-weakening-order"
    head = "a" * 40
    worktree = "/repo/.agent-worktrees/016-post-repair-weakening-order"
    command_identity = "c" * 64

    def canonical_data(
        self, candidates=(), accepted_sequence=1, command_identity=None
    ):
        return {
            "mechanical_verdict": "PASS",
            "blocking_findings": [],
            "review_candidates": [item.__dict__ for item in candidates],
            "final_validation_accepted_event_sequence": accepted_sequence,
            "command_identity": command_identity or self.command_identity,
        }

    def append_acceptance(self, store, **changes):
        values = {
            "feature": self.feature,
            "repository": "/repo",
            "branch": self.branch,
            "worktree": self.worktree,
            "phase": "post-evidence",
            "kind": "final-validation-accepted",
            "result": "PASS",
            "head_sha": self.head,
            "data": {
                "exact_head_sha": self.head,
                "command_identity": self.command_identity,
            },
        }
        values.update(changes)
        return store.append(**values)

    def append_weakening(self, store, **changes):
        values = {
            "feature": self.feature,
            "repository": "/repo",
            "branch": self.branch,
            "worktree": self.worktree,
            "phase": "delivery",
            "kind": "weakening",
            "result": "PASS",
            "head_sha": self.head,
            "data": self.canonical_data(),
        }
        values.update(changes)
        return store.append(**values)

    def test_current_canonical_identity_is_required_before_review(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            accepted = self.append_acceptance(store)
            event = self.append_weakening(
                store,
                data=self.canonical_data(accepted_sequence=accepted.sequence),
            )
            selected = delivery._require_current_review_weakening(
                store,
                head_sha=self.head,
                feature=self.feature,
                repository="/repo",
                branch=self.branch,
                worktree=self.worktree,
                final_validation_accepted_event_sequence=accepted.sequence,
            )
            self.assertEqual(selected.sequence, event.sequence)

    def test_missing_or_stale_evidence_consumes_no_review_call(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            accepted = self.append_acceptance(store)
            self.append_weakening(
                store,
                head_sha="b" * 40,
                data=self.canonical_data(accepted_sequence=accepted.sequence),
            )
            budget = delivery.ReviewCallBudget(8)
            reviewer = mock.Mock()
            with self.assertRaisesRegex(ValueError, "current HEAD"):
                delivery._require_current_review_weakening(
                    store,
                    head_sha=self.head,
                    feature=self.feature,
                    repository="/repo",
                    branch=self.branch,
                    worktree=self.worktree,
                    final_validation_accepted_event_sequence=accepted.sequence,
                )
                budget.run(reviewer)
            self.assertEqual(budget.used, 0)
            reviewer.assert_not_called()

    def test_identity_mismatch_and_legacy_or_malformed_data_fail_closed(self):
        variants = {
            "feature": {"feature": "other-feature"},
            "repository": {"repository": "/other-repo"},
            "branch": {"branch": "other-branch"},
            "worktree": {"worktree": "/other-worktree"},
            "legacy": {"data": {"findings": []}},
            "extra-field": {"data": {**self.canonical_data(), "extra": True}},
        }
        for label, changes in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                store = EventStore(Path(directory) / "events.jsonl")
                accepted = self.append_acceptance(store)
                self.append_weakening(store, **changes)
                with self.assertRaises(ValueError):
                    delivery._require_current_review_weakening(
                        store,
                        head_sha=self.head,
                        feature=self.feature,
                        repository="/repo",
                        branch=self.branch,
                        worktree=self.worktree,
                        final_validation_accepted_event_sequence=accepted.sequence,
                    )

    def test_missing_or_stale_final_validation_acceptance_fails_closed(self):
        variants = (None, "b" * 40)
        for accepted_head in variants:
            with (
                self.subTest(accepted_head=accepted_head),
                tempfile.TemporaryDirectory() as directory,
            ):
                store = EventStore(Path(directory) / "events.jsonl")
                if accepted_head is None:
                    accepted_sequence = 99
                else:
                    accepted = self.append_acceptance(
                        store,
                        head_sha=accepted_head,
                        data={
                            "exact_head_sha": accepted_head,
                            "command_identity": self.command_identity,
                        },
                    )
                    accepted_sequence = accepted.sequence
                self.append_weakening(
                    store,
                    data=self.canonical_data(
                        accepted_sequence=accepted_sequence
                    ),
                )
                budget = delivery.ReviewCallBudget(8)
                reviewer = mock.Mock()
                with self.assertRaisesRegex(
                    ValueError, "final-validation|Final-validation"
                ):
                    delivery._require_current_review_weakening(
                        store,
                        head_sha=self.head,
                        feature=self.feature,
                        repository="/repo",
                        branch=self.branch,
                        worktree=self.worktree,
                        final_validation_accepted_event_sequence=accepted_sequence,
                    )
                    budget.run(reviewer)
                self.assertEqual(budget.used, 0)
                reviewer.assert_not_called()

    def test_prior_run_weakening_cannot_approve_latest_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            previous = self.append_acceptance(store)
            self.append_weakening(
                store,
                data=self.canonical_data(accepted_sequence=previous.sequence),
            )
            current = self.append_acceptance(store)
            with self.assertRaisesRegex(ValueError, "run identity"):
                delivery._require_current_review_weakening(
                    store,
                    head_sha=self.head,
                    feature=self.feature,
                    repository="/repo",
                    branch=self.branch,
                    worktree=self.worktree,
                    final_validation_accepted_event_sequence=current.sequence,
                )

    def test_weakening_must_bind_current_validation_command_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            accepted = self.append_acceptance(store)
            self.append_weakening(
                store,
                data=self.canonical_data(
                    accepted_sequence=accepted.sequence,
                    command_identity="d" * 64,
                ),
            )
            with self.assertRaisesRegex(ValueError, "run identity"):
                delivery._require_current_review_weakening(
                    store,
                    head_sha=self.head,
                    feature=self.feature,
                    repository="/repo",
                    branch=self.branch,
                    worktree=self.worktree,
                    final_validation_accepted_event_sequence=accepted.sequence,
                )

    def test_fail_or_blocking_pass_evidence_is_rejected(self):
        blocking = weakening.Finding(
            "high", "test-skip", "tests/test_a.py", "skip added", True
        )
        variants = (
            {"result": "FAIL"},
            {
                "data": {
                    "mechanical_verdict": "PASS",
                    "blocking_findings": [blocking.__dict__],
                    "review_candidates": [],
                    "final_validation_accepted_event_sequence": 1,
                    "command_identity": self.command_identity,
                }
            },
        )
        for changes in variants:
            with tempfile.TemporaryDirectory() as directory:
                store = EventStore(Path(directory) / "events.jsonl")
                accepted = self.append_acceptance(store)
                self.append_weakening(store, **changes)
                with self.assertRaises(ValueError):
                    delivery._require_current_review_weakening(
                        store,
                        head_sha=self.head,
                        feature=self.feature,
                        repository="/repo",
                        branch=self.branch,
                        worktree=self.worktree,
                        final_validation_accepted_event_sequence=accepted.sequence,
                    )

    def test_candidate_only_inspection_records_pass_after_acceptance(self):
        candidate_patch = (
            "diff --git a/tests/test_a.py b/tests/test_a.py\n"
            "+++ b/tests/test_a.py\n-assert old\n+assert new\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            accepted = self.append_acceptance(store)

            def git_result(_repo, arguments):
                return SimpleNamespace(
                    stdout=self.head + "\n"
                    if arguments[:2] == ["rev-parse", "HEAD"]
                    else candidate_patch
                )

            with mock.patch.object(
                delivery.git_utils, "run_git", side_effect=git_result
            ):
                inspection = delivery._inspect_and_record_current_weakening(
                    Path(self.worktree),
                    store,
                    feature=self.feature,
                    repository="/repo",
                    branch=self.branch,
                    worktree=self.worktree,
                    default_branch="main",
                )
            events = store.read()
            self.assertEqual(
                [(item.kind, item.result) for item in events],
                [
                    ("final-validation-accepted", "PASS"),
                    ("weakening", "PASS"),
                ],
            )
            self.assertEqual(len(inspection.review_candidates), 1)
            self.assertEqual(
                events[-1].data,
                self.canonical_data(
                    inspection.review_candidates,
                    accepted_sequence=accepted.sequence,
                ),
            )

    def test_high_confidence_inspection_stops_without_event_or_review(self):
        inspection = weakening.Inspection(
            (
                weakening.Finding(
                    "high", "test-deletion", "tests/test_a.py", "deleted", True
                ),
            ),
            (),
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            with (
                mock.patch.object(
                    delivery.git_utils,
                    "run_git",
                    side_effect=(
                        SimpleNamespace(stdout=self.head + "\n"),
                        SimpleNamespace(stdout="patch"),
                    ),
                ),
                mock.patch.object(
                    delivery.weakening, "inspect_patch", return_value=inspection
                ),
                self.assertRaisesRegex(RuntimeError, "High-confidence"),
            ):
                delivery._inspect_and_record_current_weakening(
                    Path(self.worktree),
                    store,
                    feature=self.feature,
                    repository="/repo",
                    branch=self.branch,
                    worktree=self.worktree,
                    default_branch="main",
                )
            self.assertEqual(store.read(), [])

    def test_finalize_then_weakening_order_is_shared_by_both_repair_paths(self):
        calls = []
        feature_dir = Path(self.worktree) / "specs" / self.feature
        with (
            mock.patch.object(
                delivery,
                "_finalize_delivery_evidence",
                side_effect=lambda *args: calls.append("finalize"),
            ),
            mock.patch.object(
                delivery,
                "_inspect_and_record_current_weakening",
                side_effect=lambda *args, **kwargs: calls.append("weakening"),
            ),
        ):
            delivery._finalize_and_record_weakening(
                Path(self.worktree),
                feature_dir,
                object(),
                mock.Mock(),
                "/repo",
                self.branch,
                "main",
            )
        self.assertEqual(calls, ["finalize", "weakening"])
        source = inspect.getsource(delivery.deliver)
        self.assertEqual(source.count("_finalize_and_record_weakening("), 2)
        self.assertLess(
            source.index("_require_current_review_weakening("),
            source.index("review.prepare_reviews("),
        )

    def test_changed_head_gets_new_event_but_identical_head_is_reused(self):
        inspection = weakening.Inspection((), ())
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            common = {
                "feature": self.feature,
                "repository": "/repo",
                "branch": self.branch,
                "worktree": self.worktree,
                "final_validation_accepted_event_sequence": 1,
                "command_identity": self.command_identity,
            }
            first = delivery._record_weakening_pass(
                store, inspection, head_sha=self.head, **common
            )
            duplicate = delivery._record_weakening_pass(
                store, inspection, head_sha=self.head, **common
            )
            changed = delivery._record_weakening_pass(
                store, inspection, head_sha="b" * 40, **common
            )
            self.assertEqual(first.sequence, duplicate.sequence)
            self.assertGreater(changed.sequence, first.sequence)
            self.assertEqual(len(store.read()), 2)


if __name__ == "__main__":
    unittest.main()
