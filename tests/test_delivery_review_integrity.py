import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery
from agent.review import ReviewResult


class DeliveryReviewIntegrityTests(unittest.TestCase):
    def test_delivery_evidence_is_mechanically_validated_and_reviewed(self):
        check = mock.Mock(succeeded=True, stdout="", stderr="")
        calls = []

        def validate(*_args):
            calls.append("validate")
            return check

        def review(*_args):
            calls.append("review")
            return ReviewResult("pass", ()), "prompt", ""

        with mock.patch("agent.delivery.validation.run_named", side_effect=validate) as run_named, \
             mock.patch("agent.delivery.review.run_review", side_effect=review):
            delivery._validate_delivery_evidence(Path("repo"), Path("feature"), mock.Mock())

        self.assertEqual(calls, ["validate", "review"])
        self.assertEqual(run_named.call_args.args[2], "full")

    def test_delivery_evidence_stops_on_failed_review(self):
        check = mock.Mock(succeeded=True, stdout="", stderr="")
        failed = ReviewResult("fail", ())
        with mock.patch("agent.delivery.validation.run_named", return_value=check), \
             mock.patch("agent.delivery.review.run_review", return_value=(failed, "", "")):
            with self.assertRaisesRegex(RuntimeError, "independent review did not pass"):
                delivery._validate_delivery_evidence(Path("repo"), Path("feature"), mock.Mock())


if __name__ == "__main__":
    unittest.main()
