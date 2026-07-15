import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery, review
from agent.evidence import redact_value
from agent.events import EventStore
from agent.gates import _valid_aggregate_gate
from agent.weakening import Finding


class CanonicalReviewRedactionTests(unittest.TestCase):
    HEAD = "a" * 40
    FEATURE = "023-test"

    def _identity(self, shard: str = "tests") -> review.ReviewIdentity:
        return review.ReviewIdentity(
            identity_schema_version=review.REVIEW_IDENTITY_SCHEMA_VERSION,
            feature=self.FEATURE,
            head_sha=self.HEAD,
            shard=shard,
            review_schema_version=review.REVIEW_SCHEMA_VERSION,
            prompt_version=review.REVIEW_PROMPT_VERSION,
            reviewer_model=review.REVIEW_MODEL,
            reviewer_command_identity="c" * 64,
            review_settings=review.MODEL_SETTINGS,
            reviewed_files=("tests/test_example.py",),
            spec_digest="1" * 64,
            plan_digest="2" * 64,
            tasks_digest="3" * 64,
            validation_contract_digest="4" * 64,
            diff_input_digest="5" * 64,
            runtime_evidence_digest="6" * 64,
            tracked_snapshot_event_sequence=1,
            validation_log_blob_sha="7" * 40,
            final_validation_attempt_event_sequence=2,
            final_validation_accepted_event_sequence=3,
            final_validation_result_digest="8" * 64,
        )

    def _result(self, description: str, *, required: bool = False):
        return review.ReviewResult(
            "fail",
            (
                Finding(
                    "high" if required else "low",
                    "tests",
                    "tests/test_example.py",
                    description,
                    required,
                ),
            ),
        )

    def _common(self) -> dict:
        return {
            "feature": self.FEATURE,
            "repository": "repo",
            "branch": "agent/023-test",
            "worktree": "worktree",
            "phase": "review",
            "kind": "review-shard",
            "head_sha": self.HEAD,
        }

    def _append_chunk(self, store: EventStore, result: review.ReviewResult):
        identity = self._identity()
        event = store.append(
            **self._common(),
            result=result.result.upper(),
            data={
                "shard": "tests",
                "identity_digest": identity.digest,
                "identity": identity.payload(),
                **result.evidence_fields(),
            },
        )
        return event, identity

    def test_secret_shaped_finding_patterns_are_canonicalized_before_digest(self):
        cases = (
            ("Reject password=plain-value", "password=[REDACTED]"),
            ("Reject token=plain-value", "token=[REDACTED]"),
            ("Reject secret=plain-value", "secret=[REDACTED]"),
            ("Reject api_key=plain-value", "api_key=[REDACTED]"),
            ("Reject api-key=plain-value", "api-key=[REDACTED]"),
            ("Reject Authorization: Bearer plain-value", "Bearer [REDACTED]"),
            ("Reject " + "ghp_" + "abcdefghijklmnopqrstuvwxyz", "[REDACTED]"),
            ("Reject " + "sk-" + "abcdefghijklmnopqrstuvwxyz", "[REDACTED]"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                result = self._result(raw)
                fields = result.evidence_fields()
                rendered = json.dumps(fields, sort_keys=True)
                self.assertNotIn(raw, rendered)
                self.assertIn(expected, fields["findings"][0]["description"])
                canonical_payload = {
                    "result": "fail",
                    "findings": fields["findings"],
                }
                self.assertEqual(
                    fields["review_payload_digest"],
                    review._digest(canonical_payload),
                )
                self.assertEqual(fields["reviewer_result"], "FAIL")
                self.assertEqual(fields["gate_verdict"], "PASS")

    def test_event_store_redaction_is_idempotent_and_chunk_round_trips(self):
        raw = "Reject password=do-not-persist"
        result = self._result(raw)
        fields = result.evidence_fields()
        self.assertEqual(redact_value(fields), fields)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            store = EventStore(path)
            event, identity = self._append_chunk(store, result)
            stored = store.read()[0]
            self.assertEqual(event, stored)
            self.assertNotIn(raw, path.read_text(encoding="utf-8"))
            self.assertEqual(stored.data["findings"], fields["findings"])
            evidence_path = Path(directory) / "review.json"
            evidence_path.write_text(
                json.dumps({"head_sha": self.HEAD, **fields}, sort_keys=True),
                encoding="utf-8",
            )
            self.assertNotIn(raw, evidence_path.read_text(encoding="utf-8"))
            restored = review.result_from_chunk_event(stored, identity.digest)
            self.assertEqual(restored.result, "fail")
            self.assertTrue(restored.gate_passed)
            self.assertEqual(
                restored.findings[0].description,
                "Reject password=[REDACTED]",
            )

    def test_required_finding_remains_blocking_after_redaction(self):
        fields = self._result("token=required-value", required=True).evidence_fields()
        self.assertEqual(fields["reviewer_result"], "FAIL")
        self.assertEqual(fields["gate_verdict"], "FAIL")
        self.assertEqual(len(fields["required_findings"]), 1)
        self.assertEqual(fields["non_required_findings"], [])
        self.assertIn("[REDACTED]", fields["required_findings"][0]["description"])

    def test_persisted_finding_or_digest_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            event, identity = self._append_chunk(
                store, self._result("password=original-value")
            )
            finding_changed = dict(event.data)
            finding_changed["findings"] = [dict(event.data["findings"][0])]
            finding_changed["findings"][0]["description"] = "password=[CHANGED]"
            with self.assertRaisesRegex(ValueError, "canonical|review_payload_digest"):
                review.result_from_chunk_event(
                    replace(event, data=finding_changed), identity.digest
                )
            digest_changed = dict(event.data)
            digest_changed["review_payload_digest"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "review_payload_digest"):
                review.result_from_chunk_event(
                    replace(event, data=digest_changed), identity.digest
                )

    def test_aggregate_uses_redacted_findings_and_survives_persistence(self):
        raw = "Reject password=aggregate-value"
        result = self._result(raw)
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            chunk, identity = self._append_chunk(store, result)
            aggregate_result, aggregate_data = review.aggregate_evidence_fields(
                (result,), (identity.digest,), (chunk.sequence,)
            )
            aggregate = store.append(
                **self._common(),
                result=aggregate_result.result.upper(),
                data={"shard": "tests", "aggregate": True, **aggregate_data},
            )
            self.assertNotIn(raw, json.dumps(aggregate.data, sort_keys=True))
            self.assertEqual(aggregate.result, "PASS")
            self.assertEqual(aggregate.data["gate_verdict"], "PASS")
            self.assertTrue(
                _valid_aggregate_gate(store.read(), aggregate, self.HEAD)
            )
            changed = dict(aggregate.data)
            changed["aggregate_digest"] = "0" * 64
            self.assertFalse(
                _valid_aggregate_gate(
                    store.read(), replace(aggregate, data=changed), self.HEAD
                )
            )

    def test_old_identity_version_and_mismatched_payload_are_not_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            event, identity = self._append_chunk(
                store, self._result("password=identity-value")
            )
            old_payload = {**identity.payload(), "identity_schema_version": "4"}
            old_data = {
                **event.data,
                "identity": old_payload,
                "identity_digest": review._digest(old_payload),
            }
            old_event = replace(event, data=old_data)
            with self.assertRaisesRegex(ValueError, "identity schema"):
                review.result_from_chunk_event(old_event)
            self.assertIsNone(
                review.reusable_gate_event([old_event], old_data["identity_digest"])
            )

    def test_pr_body_and_repair_detail_only_use_redacted_findings(self):
        raw = "Reject password=external-output-value"
        result = self._result(raw)
        assessment = type("Assessment", (), {"effective": "high", "reasons": ()})()
        body = delivery._pr_body(
            self.FEATURE,
            assessment,
            result,
            (),
            validated_head=self.HEAD,
        )
        repair = delivery._review_repair_detail(result.findings)
        self.assertNotIn(raw, body)
        self.assertNotIn(raw, repair)
        self.assertIn("password=[REDACTED]", body)
        self.assertIn("password=[REDACTED]", repair)

    def test_review_limits_and_identity_version_remain_bounded(self):
        self.assertEqual(review.REVIEW_IDENTITY_SCHEMA_VERSION, "5")
        self.assertEqual(review.MAX_REVIEW_INPUT_CHARS, 100_000)


if __name__ == "__main__":
    unittest.main()
