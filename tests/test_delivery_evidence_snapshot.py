import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from agent.events import EventStore, render_validation_log
from agent.gates import REQUIRED_REVIEW_SHARDS, require_pre_push
from agent.review import ReviewIdentity
from agent.evidence_snapshot import (
    contract_digest,
    git_blob_sha,
    record_final_validation,
    record_snapshot,
    require_final_evidence,
    utc_now,
)
from agent.validation import CommandResult


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
        log = render_validation_log(
            self.store.read(),
            self.feature.name,
            contract_digest(self.feature),
            utc_now(),
        )
        (self.feature / "validation-log.md").write_text(log, encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "evidence"], cwd=self.repo, check=True)
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
        self.assertEqual(binding.final_validation_event_sequence, final.sequence)
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
            identity = ReviewIdentity(
                identity_schema_version="2",
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
                tracked_snapshot_event_sequence=binding.snapshot_event_sequence,
                validation_log_blob_sha=binding.log_blob_sha,
                final_validation_event_sequence=binding.final_validation_event_sequence,
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

    def test_ordinary_validation_does_not_satisfy_final_evidence(self):
        self._snapshot_commit()
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
        with self.assertRaisesRegex(ValueError, "post-evidence final-validation"):
            require_final_evidence(self.repo, self.feature, self.store.read(), head)

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
