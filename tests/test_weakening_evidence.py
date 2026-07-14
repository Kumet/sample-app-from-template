import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery, review, weakening
from agent.events import EventStore


def event(sequence, head, data, result="PASS"):
    return SimpleNamespace(
        sequence=sequence,
        kind="weakening",
        result=result,
        head_sha=head,
        data=data,
    )


class WeakeningInspectionTests(unittest.TestCase):
    def test_assertion_expectation_replacement_is_only_a_review_candidate(self):
        patch = """diff --git a/tests/test_database.py b/tests/test_database.py
--- a/tests/test_database.py
+++ b/tests/test_database.py
@@ -1 +1,3 @@
-assert tables == ["projects"]
+assert tables == ["projects", "tasks"]
+assert "projects" in initialized_tables
+assert initialized_tables == ["projects", "tasks"]
"""
        inspection = weakening.inspect_patch(patch)
        self.assertEqual(inspection.mechanical_verdict, "PASS")
        self.assertEqual(inspection.blocking_findings, ())
        self.assertEqual(len(inspection.review_candidates), 1)
        self.assertEqual(
            inspection.review_candidates[0].category, "assertion-removal"
        )
        payload = inspection.event_data()
        self.assertEqual(payload["mechanical_verdict"], "PASS")
        self.assertEqual(payload["blocking_findings"], [])
        self.assertEqual(len(payload["review_candidates"]), 1)
        self.assertNotIn("findings", payload)

    def test_unreplaced_assertion_remains_visible_to_tests_review(self):
        inspection = weakening.inspect_patch(
            "diff --git a/tests/test_a.py b/tests/test_a.py\n"
            "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n"
            "@@ -1 +0,0 @@\n-assert behavior\n"
        )
        self.assertEqual(inspection.blocking_findings, ())
        self.assertEqual(
            [item.category for item in inspection.review_candidates],
            ["assertion-removal"],
        )

    def test_high_confidence_test_deletion_skip_and_ci_weakening_still_block(self):
        cases = {
            "test-deletion": (
                "diff --git a/tests/test_a.py b/tests/test_a.py\n"
                "deleted file mode 100644\n"
            ),
            "test-skip": (
                "diff --git a/tests/test_a.py b/tests/test_a.py\n"
                "+++ b/tests/test_a.py\n+@"
                "unittest."
                "skip('later')\n"
            ),
            "ci-weakening": (
                "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n"
                "+++ b/.github/workflows/ci.yml\n+continue-"
                "on-error: true\n"
            ),
        }
        for category, patch in cases.items():
            with self.subTest(category=category):
                inspection = weakening.inspect_patch(patch)
                self.assertEqual(inspection.mechanical_verdict, "FAIL")
                self.assertIn(
                    category,
                    [item.category for item in inspection.blocking_findings],
                )
                self.assertTrue(
                    all(item.required for item in inspection.blocking_findings)
                )


class WeakeningReviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.head = "a" * 40
        self.finding = {
            "severity": "medium",
            "category": "assertion-removal",
            "file": "tests/test_a.py",
            "description": "Assertion removed",
            "required": False,
        }
        self.payload = {
            "mechanical_verdict": "PASS",
            "blocking_findings": [],
            "review_candidates": [self.finding],
        }

    def test_only_latest_identical_current_head_event_is_projected(self):
        rendered = review.render_runtime_evidence(
            [
                event(1, self.head, self.payload),
                event(2, "b" * 40, self.payload),
                event(3, self.head, self.payload),
            ],
            self.head,
        )
        values = json.loads(rendered)
        self.assertEqual([item["sequence"] for item in values], [3])
        self.assertEqual(values[0]["data"], self.payload)

    def test_delivery_does_not_append_duplicate_exact_head_pass(self):
        inspection = weakening.Inspection(
            (),
            (
                weakening.Finding(
                    "medium",
                    "assertion-removal",
                    "tests/test_a.py",
                    "Assertion removed",
                    False,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            arguments = {
                "feature": "015-test",
                "repository": "repo",
                "branch": "feature/015-test",
                "worktree": "worktree",
                "head_sha": self.head,
            }
            first = delivery._record_weakening_pass(
                store, inspection, **arguments
            )
            second = delivery._record_weakening_pass(
                store, inspection, **arguments
            )
            self.assertEqual(first.sequence, second.sequence)
            self.assertEqual(len(store.read()), 1)
            self.assertEqual(store.read()[0].data, self.payload)

    def test_contradictory_or_failing_current_head_evidence_fails_closed(self):
        changed = {
            **self.payload,
            "review_candidates": [
                {**self.finding, "file": "tests/test_other.py"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "contradictory"):
            review.render_runtime_evidence(
                [event(1, self.head, self.payload), event(2, self.head, changed)],
                self.head,
            )
        with self.assertRaisesRegex(ValueError, "did not pass"):
            review.render_runtime_evidence(
                [event(1, self.head, self.payload, "FAIL")], self.head
            )

    def test_malformed_or_blocking_pass_evidence_fails_closed(self):
        blocking = {**self.finding, "severity": "high", "required": True}
        with self.assertRaisesRegex(ValueError, "blocking findings"):
            review.render_runtime_evidence(
                [
                    event(
                        1,
                        self.head,
                        {
                            "mechanical_verdict": "PASS",
                            "blocking_findings": [blocking],
                            "review_candidates": [],
                        },
                    )
                ],
                self.head,
            )
        with self.assertRaisesRegex(ValueError, "incomplete or unknown"):
            review.render_runtime_evidence(
                [event(1, self.head, {"mechanical_verdict": "PASS"})], self.head
            )

    def test_legacy_pass_event_is_normalized_without_ambiguity(self):
        rendered = review.render_runtime_evidence(
            [event(1, self.head, {"findings": [self.finding]})], self.head
        )
        data = json.loads(rendered)[0]["data"]
        self.assertEqual(data, self.payload)

    def test_prompt_and_shard_guidance_define_candidate_semantics(self):
        prompt = (
            Path(__file__).resolve().parents[1]
            / "prompts"
            / "review-feature.md"
        ).read_text(encoding="utf-8")
        self.assertIn("low-confidence hypotheses", prompt)
        self.assertIn("current-HEAD diff", prompt)
        self.assertIn("updated expectation", prompt)
        self.assertIn("Only the tests shard", prompt)
        self.assertIn("candidate alone is not", prompt)
        self.assertIn("corroborate", review._review_guidance("tests [1/1]"))
        for shard in ("spec-scope", "security", "maintainability"):
            self.assertIn(
                "candidate",
                review._review_guidance(f"{shard} [1/1]"),
            )
        self.assertIn("candidate alone", review._review_guidance("integration"))

    def test_prompt_and_identity_versions_invalidate_old_reviews(self):
        self.assertEqual(review.REVIEW_PROMPT_VERSION, "4")
        self.assertEqual(review.REVIEW_IDENTITY_SCHEMA_VERSION, "4")
        self.assertEqual(review.MAX_REVIEW_INPUT_CHARS, 100_000)


if __name__ == "__main__":
    unittest.main()
