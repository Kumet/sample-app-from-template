import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent import delivery, review, review_shards
from agent.events import EventStore
from agent.gates import (
    REQUIRED_REVIEW_SHARDS,
    _valid_aggregate_gate,
    require_pre_push,
)
from agent.weakening import Finding


class ReviewGateSemanticsTests(unittest.TestCase):
    HEAD = "a" * 40
    FEATURE = "017-test"

    def _finding(self, *, required: bool) -> Finding:
        return Finding(
            "medium",
            "tests",
            "tests/test_example.py",
            "Structured review finding",
            required,
        )

    def _identity(self, shard: str, *, head: str | None = None) -> review.ReviewIdentity:
        return review.ReviewIdentity(
            identity_schema_version=review.REVIEW_IDENTITY_SCHEMA_VERSION,
            feature=self.FEATURE,
            head_sha=head or self.HEAD,
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
            diff_input_digest=(shard[0] * 64),
            runtime_evidence_digest="6" * 64,
            tracked_snapshot_event_sequence=1,
            validation_log_blob_sha="7" * 40,
            final_validation_attempt_event_sequence=2,
            final_validation_accepted_event_sequence=3,
            final_validation_result_digest="8" * 64,
        )

    def _common(self, **overrides) -> dict:
        values = {
            "feature": self.FEATURE,
            "repository": "repo",
            "branch": "feature/017-test",
            "worktree": "worktree",
            "phase": "review",
            "kind": "review-shard",
            "head_sha": self.HEAD,
        }
        values.update(overrides)
        return values

    def _append_shard(
        self,
        store: EventStore,
        shard: str,
        result: review.ReviewResult,
        *,
        event_overrides: dict | None = None,
        data_overrides: dict | None = None,
    ):
        identity = self._identity(shard)
        data = {
            "shard": shard,
            "identity_digest": identity.digest,
            "identity": identity.payload(),
            "attempt": 1,
            **result.evidence_fields(),
        }
        if data_overrides:
            data.update(data_overrides)
        event = store.append(
            **self._common(**(event_overrides or {})),
            result=result.result.upper(),
            data=data,
        )
        aggregate_result, aggregate_data = review.aggregate_evidence_fields(
            (result,), (identity.digest,), (event.sequence,)
        )
        aggregate = store.append(
            **self._common(),
            result=aggregate_result.result.upper(),
            data={"shard": shard, "aggregate": True, **aggregate_data},
        )
        return event, aggregate, identity

    def _complete_reviews(
        self,
        store: EventStore,
        *,
        tests_result: review.ReviewResult | None = None,
    ):
        store.append(
            **self._common(phase="delivery", kind="weakening"),
            result="PASS",
        )
        values = {}
        for shard in REQUIRED_REVIEW_SHARDS:
            result = (
                tests_result
                if shard == "tests" and tests_result is not None
                else review.ReviewResult("pass", ())
            )
            values[shard] = self._append_shard(store, shard, result)
        return values

    def test_raw_fail_with_only_non_required_findings_has_pass_gate(self):
        result = review.ReviewResult("fail", (self._finding(required=False),))
        fields = result.evidence_fields()
        self.assertEqual(result.result, "fail")
        self.assertEqual(result.gate_verdict, "pass")
        self.assertEqual(fields["reviewer_result"], "FAIL")
        self.assertEqual(fields["gate_verdict"], "PASS")
        self.assertEqual(fields["required_findings"], [])
        self.assertEqual(len(fields["non_required_findings"]), 1)

    def test_raw_fail_without_findings_fails_closed(self):
        result = review.ReviewResult("fail", ())
        self.assertEqual(result.gate_verdict, "fail")
        self.assertEqual(result.evidence_fields()["gate_verdict"], "FAIL")
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            self._complete_reviews(store, tests_result=result)
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "tests"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_required_finding_fails_gate(self):
        result = review.ReviewResult("fail", (self._finding(required=True),))
        self.assertEqual(result.gate_verdict, "fail")
        self.assertEqual(len(result.required_findings), 1)

    def test_missing_required_flag_and_unknown_result_are_rejected(self):
        missing = {
            "result": "fail",
            "findings": [
                {
                    "severity": "medium",
                    "category": "tests",
                    "file": "tests/test_example.py",
                    "description": "missing required",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "invalid fields"):
            review.parse_review(json.dumps(missing))
        with self.assertRaisesRegex(ValueError, "pass or fail"):
            review.parse_review('{"result":"unknown","findings":[]}')

    def test_reviewer_subprocess_error_cannot_produce_passing_gate_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            identity = self._identity("tests")
            prepared = review.PreparedReview(
                identity, "prompt", ("codex", "exec")
            )
            completed = subprocess.CompletedProcess(
                prepared.command,
                1,
                '{"result":"pass","findings":[]}',
                "reviewer failed",
            )
            with (
                mock.patch("agent.review.run_process_group", return_value=completed),
                self.assertRaisesRegex(RuntimeError, "retry budget exhausted"),
            ):
                delivery.run_prepared_review_with_retries(
                    Path(directory),
                    prepared,
                    delivery.ReviewCallBudget(1),
                    1,
                    event_store=store,
                    feature=self.FEATURE,
                    repository="repo",
                    branch="feature/017-test",
                    worktree="worktree",
                    head_sha=self.HEAD,
                    shard="tests",
                )

            events = store.read()
            self.assertEqual([event.result for event in events], ["INVALID"])
            self.assertIsNone(review.reusable_gate_event(events, identity.digest))

    def test_reviewer_timeout_cannot_produce_passing_gate_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            identity = self._identity("tests")
            prepared = review.PreparedReview(
                identity, "prompt", ("codex", "exec")
            )
            timeout = review.ReviewTimeout(
                {
                    "shard": "tests",
                    "configured_timeout": review.REVIEW_TIMEOUT_SECONDS,
                }
            )
            with (
                mock.patch("agent.review.run_process_group", side_effect=timeout),
                self.assertRaisesRegex(RuntimeError, "retry budget exhausted"),
            ):
                delivery.run_prepared_review_with_retries(
                    Path(directory),
                    prepared,
                    delivery.ReviewCallBudget(1),
                    1,
                    event_store=store,
                    feature=self.FEATURE,
                    repository="repo",
                    branch="feature/017-test",
                    worktree="worktree",
                    head_sha=self.HEAD,
                    shard="tests",
                )

            events = store.read()
            self.assertEqual([event.result for event in events], ["TIMEOUT"])
            self.assertIsNone(review.reusable_gate_event(events, identity.digest))

    def test_non_required_raw_fail_passes_complete_pre_push_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            result = review.ReviewResult("fail", (self._finding(required=False),))
            values = self._complete_reviews(store, tests_result=result)
            tests_event = values["tests"][0]
            self.assertEqual(tests_event.result, "FAIL")
            self.assertEqual(tests_event.data["gate_verdict"], "PASS")
            self.assertEqual(
                values["tests"][1].data["non_required_findings"],
                tests_event.data["non_required_findings"],
            )
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                require_pre_push(
                    Path(directory), Path(directory) / self.FEATURE, store.read(), self.HEAD
                )

    def test_required_finding_cannot_pass_pre_push(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            result = review.ReviewResult("fail", (self._finding(required=True),))
            self._complete_reviews(store, tests_result=result)
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "tests"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_incomplete_canonical_chunk_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            result = review.ReviewResult("fail", (self._finding(required=False),))
            values = self._complete_reviews(store, tests_result=result)
            chunk, _, identity = values["tests"]
            broken = dict(chunk.data)
            broken.pop("non_required_findings")
            broken_event = store.append(
                **self._common(), result="FAIL", data=broken
            )
            _, aggregate_data = review.aggregate_evidence_fields(
                (result,), (identity.digest,), (broken_event.sequence,)
            )
            store.append(
                **self._common(),
                result="PASS",
                data={"shard": "tests", "aggregate": True, **aggregate_data},
            )
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "tests"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_aggregate_chunk_sequence_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            values = self._complete_reviews(store)
            aggregate = values["security"][1]
            broken = dict(aggregate.data)
            broken["chunk_event_sequences"] = [999]
            store.append(**self._common(), result="PASS", data=broken)
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "security"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_aggregate_from_another_head_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            values = self._complete_reviews(store)
            aggregate = values["security"][1]
            stale_aggregate = store.append(
                **self._common(head_sha="b" * 40),
                result="PASS",
                data=aggregate.data,
            )
            self.assertFalse(
                _valid_aggregate_gate(store.read(), stale_aggregate, self.HEAD)
            )

    def test_chunk_context_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            store.append(
                **self._common(phase="delivery", kind="weakening"), result="PASS"
            )
            for shard in REQUIRED_REVIEW_SHARDS:
                overrides = {"branch": "other"} if shard == "security" else None
                result = review.ReviewResult("pass", ())
                self._append_shard(store, shard, result, event_overrides=overrides)
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "security"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_aggregate_rejects_chunk_from_another_shard(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            values = self._complete_reviews(store)
            integration_aggregate = values["integration"][1]
            result = review.ReviewResult("pass", ())
            identity = self._identity("other")
            chunk = store.append(
                **self._common(),
                result="PASS",
                data={
                    "shard": "other",
                    "identity_digest": identity.digest,
                    "identity": identity.payload(),
                    **result.evidence_fields(),
                },
            )
            aggregate_result, aggregate_data = review.aggregate_evidence_fields(
                (result,), (identity.digest,), (chunk.sequence,)
            )
            store.append(
                **self._common(),
                result=aggregate_result.result.upper(),
                data={
                    **integration_aggregate.data,
                    **aggregate_data,
                },
            )
            with mock.patch("agent.gates.evidence_snapshot.require_final_evidence"):
                with self.assertRaisesRegex(ValueError, "integration"):
                    require_pre_push(
                        Path(directory),
                        Path(directory) / self.FEATURE,
                        store.read(),
                        self.HEAD,
                    )

    def test_exact_identity_raw_fail_gate_pass_is_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            result = review.ReviewResult("fail", (self._finding(required=False),))
            event, _, identity = self._append_shard(store, "tests", result)
            self.assertEqual(
                review.reusable_gate_event(store.read(), identity.digest), event
            )
            changed = review.ReviewIdentity(
                **{**identity.__dict__, "head_sha": "b" * 40}
            )
            self.assertIsNone(review.reusable_gate_event(store.read(), changed.digest))

    def test_chunk_suffix_identity_matches_base_shard_event(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            base = self._identity("tests")
            identity = review.ReviewIdentity(
                **{**base.__dict__, "shard": "tests [1/1]"}
            )
            result = review.ReviewResult("pass", ())
            event = store.append(
                **self._common(),
                result="PASS",
                data={
                    "shard": "tests",
                    "identity_digest": identity.digest,
                    "identity": identity.payload(),
                    **result.evidence_fields(),
                },
            )
            self.assertEqual(
                review.result_from_chunk_event(event, identity.digest), result
            )
            self.assertEqual(
                review.reusable_gate_event(store.read(), identity.digest), event
            )

    def test_chunks_without_canonical_gate_evidence_are_not_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EventStore(Path(directory) / "events.jsonl")
            identity = self._identity("tests")
            failed = store.append(
                **self._common(),
                result="FAIL",
                data={
                    "shard": "tests",
                    "identity_digest": identity.digest,
                    "identity": identity.payload(),
                    "result": "fail",
                    "findings": [self._finding(required=False).__dict__],
                },
            )
            self.assertIsNone(review.reusable_gate_event([failed], identity.digest))
            passed = store.append(
                **self._common(),
                result="PASS",
                data={
                    "shard": "tests",
                    "identity_digest": identity.digest,
                    "identity": identity.payload(),
                    "findings": [],
                },
            )
            self.assertIsNone(
                review.reusable_gate_event(store.read(), identity.digest)
            )
            with self.assertRaisesRegex(ValueError, "canonical gate evidence"):
                review.result_from_chunk_event(passed, identity.digest)

    def test_parsed_raw_fail_finding_reaches_pr_body_only_after_redaction(self):
        raw_finding = {
            "severity": "medium",
            "category": "confidential-review-category",
            "file": "private/reviewer/path.py",
            "description": "token=reviewer-supplied-confidential-detail",
            "required": False,
        }
        parsed = review.parse_review(
            json.dumps({"result": "fail", "findings": [raw_finding]})
        )
        self.assertEqual(parsed.result, "fail")
        self.assertEqual(parsed.gate_verdict, "pass")
        self.assertEqual(parsed.findings[0].__dict__, raw_finding)
        shard_results = [
            review_shards.ShardResult(
                shard,
                self.HEAD,
                parsed if shard == "tests" else review.ReviewResult("pass", ()),
            )
            for shard in (*review_shards.SHARDS, "integration")
        ]
        result = review_shards.aggregate(shard_results, self.HEAD)
        self.assertEqual(result.findings, parsed.findings)
        assessment = type("Assessment", (), {"effective": "medium", "reasons": ()})()
        body = delivery._pr_body(
            self.FEATURE,
            assessment,
            result,
            (),
            [],
            self.HEAD,
        )
        self.assertIn("1 findings", body)
        self.assertIn("Finding 1: severity=medium", body)
        self.assertIn("required=false", body)
        self.assertIn(f"category={raw_finding['category']}", body)
        self.assertIn(f"file={raw_finding['file']}", body)
        self.assertNotIn(raw_finding["description"], body)
        self.assertIn("description=token=[REDACTED]", body)


if __name__ == "__main__":
    unittest.main()
