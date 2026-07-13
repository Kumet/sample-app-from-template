import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent.events import EventStore, render_validation_log
from agent.evidence_snapshot import (
    contract_digest,
    git_blob_sha,
    record_final_validation_accepted,
    record_final_validation_attempt,
    record_snapshot,
    require_final_evidence,
    utc_now,
)
from agent.gates import REQUIRED_REVIEW_SHARDS, require_pre_push
from agent.review import ReviewIdentity
from agent.review_shards import reusable_event
from agent.validation import CommandResult


def record_final_validation(store, **kwargs):
    attempt = record_final_validation_attempt(store, **kwargs)
    if not kwargs["result"].succeeded:
        return attempt
    accepted_kwargs = {
        key: kwargs[key]
        for key in (
            "repo",
            "feature_dir",
            "repository",
            "branch",
            "worktree",
            "snapshot",
        )
    }
    return record_final_validation_accepted(store, **accepted_kwargs, attempt=attempt)


class EvidenceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.feature = self.repo / "specs" / "007-test"
        self.feature.mkdir(parents=True)
        (self.feature / "validation.toml").write_text("version=2\n", encoding="utf-8")
        self.store = EventStore(Path(self.temp.name) / "events.jsonl")
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=self.repo, check=True
        )

    def tearDown(self):
        self.temp.cleanup()

    def _snapshot_commit(self):
        before = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        log = render_validation_log(
            self.store.read(),
            self.feature.name,
            contract_digest(self.feature),
            utc_now(),
        )
        (self.feature / "validation-log.md").write_text(log, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "evidence"], cwd=self.repo, check=True)
        after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertNotEqual(before, after)
        snapshot = record_snapshot(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
        )
        return snapshot

    def test_snapshot_blob_and_post_evidence_validation_bind_exact_head(self):
        snapshot = self._snapshot_commit()
        result = CommandResult("full", ("make", "validate"), 0, "ok", "")
        final = record_final_validation(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=result,
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        binding = require_final_evidence(
            self.repo, self.feature, self.store.read(), head
        )
        self.assertEqual(binding.snapshot_event_sequence, snapshot.sequence)
        self.assertEqual(
            binding.final_validation_accepted_event_sequence, final.sequence
        )
        self.assertEqual(
            binding.log_blob_sha,
            git_blob_sha(self.repo, "specs/007-test/validation-log.md"),
        )
        common = dict(
            feature=self.feature.name,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            phase="review",
            head_sha=head,
        )
        self.store.append(
            **common, kind="weakening", result="PASS", data={"findings": []}
        )
        for shard in REQUIRED_REVIEW_SHARDS:
            if shard == "integration":
                with self.assertRaisesRegex(
                    ValueError, "Missing exact-HEAD review shards: integration"
                ):
                    require_pre_push(self.repo, self.feature, self.store.read(), head)
            identity = ReviewIdentity(
                identity_schema_version="4",
                feature=self.feature.name,
                head_sha=head,
                shard=shard,
                review_schema_version="1",
                prompt_version="2",
                reviewer_model="gpt-5.4-mini",
                reviewer_command_identity="c" * 64,
                review_settings=("model=gpt-5.4-mini",),
                reviewed_files=("file.py",),
                spec_digest="1" * 64,
                plan_digest="2" * 64,
                tasks_digest="3" * 64,
                validation_contract_digest=binding.validation_contract_digest,
                diff_input_digest="4" * 64,
                runtime_evidence_digest="7" * 64,
                tracked_snapshot_event_sequence=binding.snapshot_event_sequence,
                validation_log_blob_sha=binding.log_blob_sha,
                final_validation_attempt_event_sequence=(
                    binding.final_validation_attempt_event_sequence
                ),
                final_validation_accepted_event_sequence=(
                    binding.final_validation_accepted_event_sequence
                ),
                final_validation_result_digest=binding.validation_result_digest,
            )
            self.store.append(
                **common,
                kind="review-shard",
                result="PASS",
                data={
                    "shard": shard,
                    "identity_digest": identity.digest,
                    "identity": identity.payload(),
                    "findings": [],
                },
            )
            self.store.append(
                **common,
                kind="review-shard",
                result="PASS",
                data={
                    "shard": shard,
                    "aggregate": True,
                    "chunk_identities": [identity.digest],
                },
            )
        require_pre_push(self.repo, self.feature, self.store.read(), head)
        latest_spec_scope = next(
            event
            for event in reversed(self.store.read())
            if (event.data or {}).get("shard") == "spec-scope"
            and (event.data or {}).get("aggregate") is True
        )
        self.store.append(
            **common,
            kind="review-shard",
            result="PASS",
            data=latest_spec_scope.data,
        )
        with self.assertRaisesRegex(ValueError, "Integration review predates"):
            require_pre_push(self.repo, self.feature, self.store.read(), head)
        (self.repo / "post-review.txt").write_text("changed", encoding="utf-8")
        subprocess.run(["git", "add", "post-review.txt"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "post-review change"],
            cwd=self.repo,
            check=True,
        )
        new_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        with self.assertRaisesRegex(ValueError, "tracked-evidence-snapshot"):
            require_pre_push(self.repo, self.feature, self.store.read(), new_head)
        changed_identity = ReviewIdentity(**{**identity.__dict__, "head_sha": new_head})
        self.assertIsNone(reusable_event(self.store.read(), changed_identity.digest))

    def test_ordinary_validation_does_not_satisfy_final_evidence(self):
        snapshot = self._snapshot_commit()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.store.append(
            feature=self.feature.name,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            phase="final",
            kind="validation",
            result="PASS",
            head_sha=head,
        )
        self.store.append(
            feature=self.feature.name,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            phase="post-evidence",
            kind="final-validation",
            result="PASS",
            head_sha=head,
            data={"evidence_snapshot_event_sequence": snapshot.sequence},
        )
        with self.assertRaisesRegex(ValueError, "final-validation-accepted"):
            require_final_evidence(self.repo, self.feature, self.store.read(), head)

    def test_attempt_is_audited_but_only_accepted_pass_opens_gate(self):
        snapshot = self._snapshot_commit()
        common = dict(
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        failed = record_final_validation_attempt(
            self.store,
            **common,
            result=CommandResult("full", ("make", "validate"), 1, "", "failed"),
        )
        self.assertEqual(
            (failed.kind, failed.result), ("final-validation-attempt", "FAIL")
        )
        self.assertFalse(
            any(
                event.kind == "final-validation-accepted" for event in self.store.read()
            )
        )
        with self.assertRaisesRegex(ValueError, "final-validation-accepted"):
            require_final_evidence(
                self.repo, self.feature, self.store.read(), snapshot.head_sha
            )
        attempt = record_final_validation_attempt(
            self.store,
            **common,
            result=CommandResult("full", ("make", "validate"), 0, "ok", ""),
        )
        with self.assertRaisesRegex(ValueError, "final-validation-accepted"):
            require_final_evidence(
                self.repo, self.feature, self.store.read(), snapshot.head_sha
            )
        accepted = record_final_validation_accepted(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            attempt=attempt,
        )
        self.assertEqual(
            (accepted.kind, accepted.result), ("final-validation-accepted", "PASS")
        )
        self.assertEqual(accepted.data["attempt_event_sequence"], attempt.sequence)
        self.assertEqual(accepted.data["snapshot_event_sequence"], snapshot.sequence)

    def test_acceptance_mismatch_appends_rejection(self):
        snapshot = self._snapshot_commit()
        attempt = record_final_validation_attempt(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=CommandResult("full", ("make", "validate"), 0, "ok", ""),
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        malformed = replace(attempt, head_sha="different")
        with self.assertRaisesRegex(ValueError, "attempt HEAD mismatch"):
            record_final_validation_accepted(
                self.store,
                repo=self.repo,
                feature_dir=self.feature,
                repository=str(self.repo),
                branch="test",
                worktree=str(self.repo),
                snapshot=snapshot,
                attempt=malformed,
            )
        rejected = self.store.read()[-1]
        self.assertEqual(
            (rejected.kind, rejected.result), ("final-validation-rejected", "FAIL")
        )
        self.assertEqual(rejected.data["attempt_event_sequence"], malformed.sequence)

    def test_blob_contract_snapshot_and_dirty_acceptance_are_rejected(self):
        snapshot = self._snapshot_commit()
        attempt = record_final_validation_attempt(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=CommandResult("full", ("make", "validate"), 0, "ok", ""),
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        cases = (
            (
                "log blob",
                replace(
                    attempt,
                    data={**(attempt.data or {}), "validation_log_blob_sha": "0" * 40},
                ),
                snapshot,
            ),
            (
                "contract digest",
                replace(
                    attempt,
                    data={
                        **(attempt.data or {}),
                        "validation_contract_digest": "0" * 64,
                    },
                ),
                snapshot,
            ),
            ("snapshot HEAD", attempt, replace(snapshot, head_sha="different")),
        )
        for label, candidate_attempt, candidate_snapshot in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                record_final_validation_accepted(
                    self.store,
                    repo=self.repo,
                    feature_dir=self.feature,
                    repository=str(self.repo),
                    branch="test",
                    worktree=str(self.repo),
                    snapshot=candidate_snapshot,
                    attempt=candidate_attempt,
                )
            self.assertEqual(self.store.read()[-1].kind, "final-validation-rejected")
        (self.repo / "dirty.txt").write_text("dirty", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "clean worktree"):
            record_final_validation_accepted(
                self.store,
                repo=self.repo,
                feature_dir=self.feature,
                repository=str(self.repo),
                branch="test",
                worktree=str(self.repo),
                snapshot=snapshot,
                attempt=attempt,
            )
        self.assertEqual(self.store.read()[-1].kind, "final-validation-rejected")

    def test_final_evidence_rejects_dirty_or_new_head(self):
        snapshot = self._snapshot_commit()
        result = CommandResult("full", ("make", "validate"), 0, "ok", "")
        record_final_validation(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=result,
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        (self.repo / "later.txt").write_text("later", encoding="utf-8")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        with self.assertRaisesRegex(ValueError, "clean worktree"):
            require_final_evidence(self.repo, self.feature, self.store.read(), head)

    def test_snapshot_and_final_mismatches_fail_closed(self):
        snapshot = self._snapshot_commit()
        result = CommandResult("full", ("make", "validate"), 0, "ok", "")
        final = record_final_validation(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=result,
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        head = snapshot.head_sha
        cases = (
            ("snapshot reference", {"snapshot_event_sequence": 999}),
            ("log blob", {"validation_log_blob_sha": "0" * 40}),
            ("contract digest", {"validation_contract_digest": "0" * 64}),
        )
        for label, replacement in cases:
            with self.subTest(label=label):
                data = dict(final.data or {})
                data.update(replacement)
                malformed = replace(final, sequence=final.sequence + 1, data=data)
                isolated_events = [
                    event
                    for event in self.store.read()
                    if event.sequence != final.sequence
                ] + [malformed]
                with self.assertRaises(ValueError):
                    require_final_evidence(
                        self.repo, self.feature, isolated_events, head
                    )

    def test_new_commit_invalidates_final_evidence(self):
        snapshot = self._snapshot_commit()
        result = CommandResult("full", ("make", "validate"), 0, "ok", "")
        record_final_validation(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=result,
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        (self.repo / "later.txt").write_text("later", encoding="utf-8")
        subprocess.run(["git", "add", "later.txt"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "later"], cwd=self.repo, check=True)
        new_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        with self.assertRaisesRegex(ValueError, "Missing tracked-evidence-snapshot"):
            require_final_evidence(self.repo, self.feature, self.store.read(), new_head)

    def test_commit_after_attempt_is_rejected(self):
        snapshot = self._snapshot_commit()
        attempt = record_final_validation_attempt(
            self.store,
            repo=self.repo,
            feature_dir=self.feature,
            repository=str(self.repo),
            branch="test",
            worktree=str(self.repo),
            snapshot=snapshot,
            result=CommandResult("full", ("make", "validate"), 0, "ok", ""),
            started_at=utc_now(),
            completed_at=utc_now(),
        )
        (self.repo / "later.txt").write_text("later", encoding="utf-8")
        subprocess.run(["git", "add", "later.txt"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "later"], cwd=self.repo, check=True)
        with self.assertRaisesRegex(ValueError, "attempt HEAD mismatch"):
            record_final_validation_accepted(
                self.store,
                repo=self.repo,
                feature_dir=self.feature,
                repository=str(self.repo),
                branch="test",
                worktree=str(self.repo),
                snapshot=snapshot,
                attempt=attempt,
            )
        self.assertEqual(self.store.read()[-1].kind, "final-validation-rejected")
