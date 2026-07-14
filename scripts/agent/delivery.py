from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import (
    codex_runner,
    evidence_snapshot,
    git_utils,
    review,
    review_shards,
    recovery_patch,
    state,
    validation,
    weakening,
    worktree,
)
from .events import EventStore, render_validation_log
from .evidence import redact, redact_value, safe_error_detail
from .gates import require_mergeable, require_pre_push
from .github_delivery import GitHubDelivery, checks_with_repairs
from .notifications import payload as notification_payload
from .notifications import write_outbox
from .parser import Task, load_config, parse_tasks, resolve_feature
from .policy import RepositoryPolicy
from .risk import assess, merge_allowed
from .spec_lint import require_lint


def dry_run(repo: Path, feature: str, policy: RepositoryPolicy) -> dict:
    feature_dir = resolve_feature(repo, feature)
    report = require_lint(feature_dir, policy)
    config = load_config(feature_dir, policy)
    tasks = parse_tasks(feature_dir / "tasks.md", set(config.commands))
    inspection = inspect_delivery_worktree(
        repo, feature_dir, config, tasks, policy.default_branch
    )
    return {
        "feature": feature_dir.name,
        "risk": config.risk,
        "auto_merge_requested": config.auto_merge,
        "spec_warnings": list(report.warnings),
        **inspection,
        "planned_mutations": [
            inspection["worktree_action"],
            "run Codex tasks",
            "local commits",
        ],
        "planned_remote_mutations": (
            []
            if config.risk == "high"
            else ["push-feature-branch", "create-or-update-pr", "monitor-ci"]
        ),
        "deferred_remote_mutations": (
            ["push-feature-branch", "create-or-update-pr", "monitor-ci"]
            if config.risk == "high"
            else []
        ),
        "remote_mutation_blocker": (
            "high-risk-pre-push-approval" if config.risk == "high" else None
        ),
    }


def inspect_delivery_worktree(
    repo: Path, feature_dir: Path, config, tasks, default_branch: str | None = None
) -> dict:
    """Inspect delivery resume/create eligibility without changing any state."""
    path = repo / ".agent-worktrees" / feature_dir.name
    normalized_path = path.resolve(strict=False)
    safe_start = git_utils.inspect_safe_start(repo, default_branch)
    root_marker = repo / ".agent-worktree-owned"
    blockers = list(safe_start.blocking_reasons)
    if root_marker.exists():
        blockers.append("repository root contains an ownership marker")
    result = {
        "worktree_action": "create-isolated-worktree",
        "root_start_safe": safe_start.safe,
        "root_branch": safe_start.branch,
        "root_detached": safe_start.detached,
        "root_dirty": safe_start.dirty,
        "root_blocking_reasons": list(safe_start.blocking_reasons),
        "worktree_path": str(normalized_path),
        "expected_worktree_path": str(normalized_path),
        "saved_worktree_path": None,
        "saved_worktree_path_raw": None,
        "worktree_path_match": None,
        "worktree_exists": path.exists(),
        "ownership_valid": None,
        "marker_feature": None,
        "state_status": None,
        "state_failure_class": None,
        "state_task": None,
        "state_feature": None,
        "saved_head": None,
        "current_head": None,
        "contract_match": None,
        "branch_match": None,
        "changed_paths_match": None,
        "completed_tasks": [task.task_id for task in tasks if task.completed],
        "pending_tasks": [task.task_id for task in tasks if not task.completed],
        "resume_safe": False,
        "blocking_reasons": blockers,
    }
    if not path.exists():
        if worktree.is_registered_isolated(repo, path):
            blockers.append("worktree is registered but its directory is missing")
            result["worktree_action"] = "blocked-existing-worktree"
        result["resume_safe"] = not blockers
        return result
    result["worktree_action"] = "blocked-existing-worktree"
    eligible_action = None

    if not worktree.is_registered_isolated(repo, path):
        blockers.append("existing path is not a registered isolated worktree")
    marker = path / ".agent-worktree-owned"
    try:
        marker_feature = worktree.read_ownership_marker(marker)
    except FileNotFoundError:
        marker_feature = None
    except (OSError, UnicodeError, ValueError) as error:
        blockers.append(f"ownership marker is unreadable: {type(error).__name__}")
        marker_feature = None
    result["marker_feature"] = marker_feature
    result["ownership_valid"] = marker_feature == feature_dir.name
    if not result["ownership_valid"]:
        blockers.append("ownership marker is missing or names another feature")

    try:
        current_branch = git_utils.branch(path)
        current_head = git_utils.run_git(path, ["rev-parse", "HEAD"]).stdout.strip()
        changed_paths = git_utils.changed_paths_read_only(path)
    except Exception as error:
        blockers.append(f"worktree Git inspection failed: {type(error).__name__}")
        current_branch, current_head, changed_paths = None, None, []
    result["current_head"] = current_head

    state_path = repo / ".agent-work" / feature_dir.name / "state.json"
    try:
        saved = state.read_state(state_path)
    except Exception as error:
        blockers.append(f"saved state is unavailable: {type(error).__name__}")
        saved = None

    isolated_feature = None
    isolated_contract_digest = None
    try:
        isolated_feature = resolve_feature(path, feature_dir.name)
        isolated_contract_digest = state.contract_digest(isolated_feature)
        isolated_tasks = parse_tasks(
            isolated_feature / "tasks.md", set(config.commands)
        )
        result["completed_tasks"] = [
            task.task_id for task in isolated_tasks if task.completed
        ]
        result["pending_tasks"] = [
            task.task_id for task in isolated_tasks if not task.completed
        ]
    except Exception as error:
        blockers.append(f"worktree feature inspection failed: {type(error).__name__}")

    if saved is not None:
        result.update(
            {
                "state_status": saved.status,
                "state_failure_class": saved.failure_class,
                "state_task": saved.task,
                "state_feature": saved.feature,
                "saved_head": saved.head_commit,
                "saved_worktree_path_raw": saved.worktree,
                "branch_match": saved.branch == current_branch,
                "changed_paths_match": tuple(sorted(saved.changed_paths))
                == tuple(sorted(changed_paths)),
            }
        )
        result["contract_match"] = (
            isolated_contract_digest is not None
            and saved.contract_digest == isolated_contract_digest
        )
        if saved.feature != feature_dir.name:
            blockers.append("saved state names another feature")
        try:
            saved_path = Path(saved.worktree)
            normalized_saved_path = saved_path.resolve(strict=False)
            result["saved_worktree_path"] = str(normalized_saved_path)
            result["worktree_path_match"] = (
                saved_path.is_absolute()
                and saved_path == path.absolute()
                and saved_path.exists()
                and normalized_saved_path == normalized_path
            )
        except (OSError, RuntimeError):
            result["worktree_path_match"] = False
        if not result["worktree_path_match"]:
            blockers.append("saved state names another worktree")
        if not result["branch_match"]:
            blockers.append("worktree branch differs from saved state")
        if not result["contract_match"]:
            blockers.append("feature contract differs from saved state")
        if not result["changed_paths_match"]:
            blockers.append("changed paths differ from saved state")
        recovery_blockers = recovery_patch.verify_active_evidence(
            repo,
            feature_dir,
            saved,
            current_branch,
            current_head,
            changed_paths,
        )
        blockers.extend(recovery_blockers)
        result["recovery_evidence_valid"] = not recovery_blockers
        result["recovery_event_sequence"] = saved.recovery_event_sequence
        result["recovery_diff_digest"] = saved.recovery_diff_digest
        if saved.status == "complete":
            eligible_action = "reuse-completed-worktree"
            ancestor = (
                git_utils.run_git(
                    path,
                    ["merge-base", "--is-ancestor", saved.head_commit, current_head],
                    check=False,
                )
                if current_head
                else None
            )
            if ancestor is None or ancestor.returncode or changed_paths:
                blockers.append("completed worktree history or files changed")
        elif saved.status in {"running", "failed"}:
            eligible_action = "resume-existing-worktree"
            if saved.head_commit != current_head:
                blockers.append("worktree HEAD differs from saved state")
        else:
            blockers.append(f"state status {saved.status} is not resumable")
    result["resume_safe"] = not blockers
    if result["resume_safe"] and eligible_action is not None:
        result["worktree_action"] = eligible_action
    return result


@dataclass
class ReviewCallBudget:
    """Stateful total-call budget that reserves before reviewer execution."""

    limit: int
    used: int = 0

    def require_capacity(self) -> None:
        if self.used >= self.limit:
            raise ReviewBudgetExhausted(self.limit, self.used)

    def run(self, reviewer_call):
        self.require_capacity()
        self.used += 1
        return reviewer_call()


class ReviewBudgetExhausted(RuntimeError):
    """The bounded delivery-wide reviewer subprocess allowance is consumed."""

    def __init__(self, limit: int, used: int):
        self.limit = limit
        self.used = used
        super().__init__("Independent review call budget exhausted")


class ReviewResumeRequired(RuntimeError):
    """An explicit later delivery invocation is required to resume review."""


def deliver(
    repo: Path,
    feature: str,
    policy: RepositoryPolicy,
    work_function,
    github_factory=GitHubDelivery,
) -> dict:
    git_utils.ensure_safe_start(repo, policy.default_branch)
    feature_dir = resolve_feature(repo, feature)
    require_lint(feature_dir, policy)
    config = load_config(feature_dir, policy)
    tasks = parse_tasks(feature_dir / "tasks.md", set(config.commands))
    event_store = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
    existing_path = repo / ".agent-worktrees" / feature_dir.name
    inspection = inspect_delivery_worktree(
        repo, feature_dir, config, tasks, policy.default_branch
    )
    if not inspection["resume_safe"]:
        raise RuntimeError(
            "Delivery worktree is unsafe: " + "; ".join(inspection["blocking_reasons"])
        )
    resuming = inspection["worktree_exists"]
    if resuming:
        isolated = worktree.Worktree(existing_path, git_utils.branch(existing_path))
        saved = state.read_state(repo / ".agent-work" / feature_dir.name / "state.json")
        isolated_feature = resolve_feature(existing_path, feature_dir.name)
    else:
        isolated = worktree.create(repo, feature_dir.name, git_utils.branch(repo))
    try:
        if not (resuming and saved.status == "complete"):
            work_function(
                isolated.path, feature_dir.name, state_root=repo, resume_mode=resuming
            )
        isolated_feature = isolated.path / "specs" / feature_dir.name
        head_before_validation = git_utils.run_git(
            isolated.path, ["rev-parse", "HEAD"]
        ).stdout.strip()
        try:
            binding = evidence_snapshot.require_final_evidence(
                isolated.path,
                isolated_feature,
                event_store.read(),
                head_before_validation,
            )
        except ValueError:
            (isolated_feature / "validation-log.md").write_text(
                render_validation_log(
                    event_store.read(),
                    isolated_feature.name,
                    evidence_snapshot.contract_digest(isolated_feature),
                    evidence_snapshot.utc_now(),
                ),
                encoding="utf-8",
            )
            paths = git_utils.changed_paths(isolated.path)
            validation.validate_scope(paths, config)
            git_utils.diff_check(isolated.path)
            git_utils.commit(
                isolated.path,
                paths,
                f"docs({feature_dir.name}): finalize tracked evidence snapshot",
            )
            snapshot = evidence_snapshot.record_snapshot(
                event_store,
                repo=isolated.path,
                feature_dir=isolated_feature,
                repository=str(repo),
                branch=isolated.branch,
                worktree=str(isolated.path),
            )
            started_at = evidence_snapshot.utc_now()
            check = validation.run_named(isolated.path, config, "full")
            completed_at = evidence_snapshot.utc_now()
            attempt = evidence_snapshot.record_final_validation_attempt(
                event_store,
                repo=isolated.path,
                feature_dir=isolated_feature,
                repository=str(repo),
                branch=isolated.branch,
                worktree=str(isolated.path),
                snapshot=snapshot,
                result=check,
                started_at=started_at,
                completed_at=completed_at,
            )
            if not check.succeeded:
                raise RuntimeError("Post-evidence final validation failed") from None
            evidence_snapshot.record_final_validation_accepted(
                event_store,
                repo=isolated.path,
                feature_dir=isolated_feature,
                repository=str(repo),
                branch=isolated.branch,
                worktree=str(isolated.path),
                snapshot=snapshot,
                attempt=attempt,
            )
            current = git_utils.run_git(
                isolated.path, ["rev-parse", "HEAD"]
            ).stdout.strip()
            binding = evidence_snapshot.require_final_evidence(
                isolated.path, isolated_feature, event_store.read(), current
            )
        head_before_validation = binding.head_sha
        weakening_inspection = _inspect_and_record_current_weakening(
            isolated.path,
            event_store,
            feature=feature_dir.name,
            repository=str(repo),
            branch=isolated.branch,
            worktree=str(isolated.path),
            default_branch=policy.default_branch,
        )
        evidence = repo / ".agent-work" / feature_dir.name / "delivery"
        evidence.mkdir(parents=True, exist_ok=True)
        review_budget = ReviewCallBudget(policy.max_review_calls)

        def run_review_once():
            head = git_utils.run_git(
                isolated.path, ["rev-parse", "HEAD"]
            ).stdout.strip()
            current_binding = evidence_snapshot.require_final_evidence(
                isolated.path, isolated_feature, event_store.read(), head
            )
            _require_current_review_weakening(
                event_store,
                head_sha=head,
                feature=feature_dir.name,
                repository=str(repo),
                branch=isolated.branch,
                worktree=str(isolated.path),
                final_validation_accepted_event_sequence=(
                    current_binding.final_validation_accepted_event_sequence
                ),
            )
            shard_results = []
            chunk_events = []

            def obtain_prepared(shard, prepared):
                result, stderr, reused = obtain_cached_or_run_prepared_review(
                    isolated.path,
                    prepared,
                    review_budget,
                    config.max_review_attempts,
                    event_store=event_store,
                    feature=feature_dir.name,
                    repository=str(repo),
                    branch=isolated.branch,
                    worktree=str(isolated.path),
                    head_sha=head,
                    shard=shard,
                )
                if reused:
                    cached = review.reusable_gate_event(
                        event_store.read(), prepared.identity.digest
                    )
                    if cached is None:
                        raise RuntimeError("Reused review evidence is no longer valid")
                    chunk_events.append(cached)
                    return result
                prefix = f"review-{review_budget.used}-{shard}"
                (evidence / f"{prefix}-prompt-metadata.json").write_text(
                    json.dumps(
                        {
                            "identity_digest": prepared.identity.digest,
                            "runtime_evidence_digest": (
                                prepared.identity.runtime_evidence_digest
                            ),
                            "prompt_chars": len(prepared.prompt),
                            "prompt_digest": hashlib.sha256(
                                prepared.prompt.encode("utf-8")
                            ).hexdigest(),
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (evidence / f"{prefix}-stderr.txt").write_text(
                    redact(stderr, 4000), encoding="utf-8"
                )
                payload = redact_value(
                    {
                        "head_sha": head,
                        "shard": shard,
                        "identity_digest": prepared.identity.digest,
                        "identity": prepared.identity.payload(),
                        **result.evidence_fields(),
                    }
                )
                (evidence / f"{prefix}.json").write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
                )
                chunk_event = event_store.append(
                    feature=feature_dir.name,
                    repository=str(repo),
                    branch=isolated.branch,
                    worktree=str(isolated.path),
                    phase="review",
                    kind="review-shard",
                    result=result.result.upper(),
                    head_sha=head,
                    data={
                        **payload,
                        "attempt": review_budget.used,
                    },
                )
                chunk_events.append(chunk_event)
                return result

            def obtain(shard, context=None):
                prepared_items = review.prepare_reviews(
                    isolated.path,
                    isolated_feature,
                    shard,
                    review.render_runtime_evidence(event_store.read(), head),
                    current_binding.identity_fields(),
                )
                if context is not None:
                    prepared_items = tuple(
                        review.bind_context(item, context) for item in prepared_items
                    )
                chunk_start = len(chunk_events)
                chunk_results = [
                    obtain_prepared(shard, item) for item in prepared_items
                ]
                shard_chunk_events = chunk_events[chunk_start:]
                result, aggregate_data = review.aggregate_evidence_fields(
                    tuple(chunk_results),
                    tuple(item.identity.digest for item in prepared_items),
                    tuple(event.sequence for event in shard_chunk_events),
                )
                event_store.append(
                    feature=feature_dir.name,
                    repository=str(repo),
                    branch=isolated.branch,
                    worktree=str(isolated.path),
                    phase="review",
                    kind="review-shard",
                    result=result.result.upper(),
                    head_sha=head,
                    data={
                        "shard": shard,
                        "aggregate": True,
                        **aggregate_data,
                    },
                )
                return result

            for shard in review_shards.SHARDS:
                result = obtain(shard)
                shard_results.append(review_shards.ShardResult(shard, head, result))
            file_findings = tuple(
                finding for item in shard_results for finding in item.result.findings
            )
            if any(f.required for f in file_findings):
                return review.ReviewResult("fail", file_findings)
            if any(not item.result.gate_passed for item in shard_results):
                raise RuntimeError(
                    "Independent review file shard failed without structured findings"
                )
            integration = obtain(
                "integration",
                {
                    "file_shards": [
                        {
                            "shard": item.shard,
                            "result": item.result.result,
                            "gate_verdict": item.result.gate_verdict,
                            "signature": item.result.signature(),
                        }
                        for item in shard_results
                    ]
                },
            )
            shard_results.append(
                review_shards.ShardResult("integration", head, integration)
            )
            if not integration.gate_passed and not integration.required_findings:
                raise RuntimeError(
                    "Independent integration review failed without structured findings"
                )
            return review_shards.aggregate(shard_results, head)

        def repair_review(findings):
            detail = json.dumps([finding.__dict__ for finding in findings], indent=2)
            _repair_and_commit(
                isolated.path, isolated_feature, config, "REVIEW", detail
            )
            _finalize_and_record_weakening(
                isolated.path,
                isolated_feature,
                config,
                event_store,
                str(repo),
                isolated.branch,
                policy.default_branch,
            )

        review_result = review.review_with_repairs(
            run_review_once,
            repair_review,
            min(config.max_review_attempts, policy.max_review_attempts),
        )
        (evidence / "review.json").write_text(
            json.dumps(
                {
                    "result": review_result.result,
                    "findings": [f.__dict__ for f in review_result.findings],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if review_result.required_findings:
            raise RuntimeError("Independent review requires remediation")
        weakening_inspection = _inspect_and_record_current_weakening(
            isolated.path,
            event_store,
            feature=feature_dir.name,
            repository=str(repo),
            branch=isolated.branch,
            worktree=str(isolated.path),
            default_branch=policy.default_branch,
        )
        gated_head = git_utils.run_git(
            isolated.path, ["rev-parse", "HEAD"]
        ).stdout.strip()
        require_pre_push(
            isolated.path, isolated_feature, event_store.read(), gated_head
        )
        final_binding = evidence_snapshot.require_final_evidence(
            isolated.path, isolated_feature, event_store.read(), gated_head
        )
        review_identity_digest = review.identity_set_digest(
            [
                value
                for event in event_store.read()
                if event.kind == "review-shard"
                and event.result == "PASS"
                and event.head_sha == gated_head
                for value in ((event.data or {}).get("chunk_identities") or [])
            ]
        )
        paths = git_utils.run_git(
            isolated.path, ["diff", "--name-only", f"{policy.default_branch}...HEAD"]
        ).stdout.splitlines()
        assessment = assess(
            config.risk,
            paths,
            list(review_result.findings) + list(weakening_inspection.findings),
            policy,
            config.risk_domains,
        )
        if assessment.effective == "high":
            raise RuntimeError("High-risk delivery stops before push")
        try:
            github = github_factory(isolated.path, default_branch=policy.default_branch)
        except TypeError:
            github = github_factory(isolated.path)
        github.ensure_tools()
        github.push(isolated.branch)
        body = evidence / "pr-body.md"
        body.write_text(
            _pr_body(
                feature_dir.name,
                assessment,
                review_result,
                weakening_inspection.findings,
                event_store.read(),
                gated_head,
                final_binding,
                review_identity_digest,
            ),
            encoding="utf-8",
        )
        pr = github.ensure_pr(isolated.branch, f"Deliver {feature_dir.name}", body)
        write_outbox(
            repo / ".agent-work" / "outbox",
            notification_payload(
                "pr-created",
                feature_dir.name,
                "open",
                "PR created",
                git_utils.run_git(isolated.path, ["rev-parse", "HEAD"]).stdout.strip(),
                pr.url,
            ),
        )
        ci_repair_count = 0

        def repair_ci(failure):
            nonlocal ci_repair_count
            ci_repair_count += 1
            _repair_and_commit(
                isolated.path, isolated_feature, config, "CI", redact(failure, 8000)
            )
            _finalize_and_record_weakening(
                isolated.path,
                isolated_feature,
                config,
                event_store,
                str(repo),
                isolated.branch,
                policy.default_branch,
            )
            github.push(isolated.branch)

        checks_passed = checks_with_repairs(
            github,
            pr.number,
            repair_ci,
            min(config.max_ci_attempts, policy.max_ci_attempts),
        )
        if ci_repair_count:
            post_ci_review = run_review_once()
            if post_ci_review.required_findings:
                raise RuntimeError(
                    "Post-CI-repair independent review requires remediation"
                )
        gated_sha = git_utils.run_git(
            isolated.path, ["rev-parse", "HEAD"]
        ).stdout.strip()
        event_store.append(
            feature=feature_dir.name,
            repository=str(repo),
            branch=isolated.branch,
            worktree=str(isolated.path),
            phase="delivery",
            kind="review",
            result="PASS",
            head_sha=gated_sha,
            data={"shards": list(review_shards.SHARDS) + ["integration"]},
        )
        event_store.append(
            feature=feature_dir.name,
            repository=str(repo),
            branch=isolated.branch,
            worktree=str(isolated.path),
            phase="delivery",
            kind="ci",
            result="PASS" if checks_passed else "FAIL",
            head_sha=gated_sha,
            data={"pr": pr.url},
        )
        merged = False
        if merge_allowed(
            assessment,
            config.auto_merge,
            policy,
            checks_passed,
            review_result.result == "pass",
            list(weakening_inspection.findings),
        ):
            require_mergeable(event_store.read(), gated_sha)
            github.merge(pr.number)
            merged = True
        write_outbox(
            repo / ".agent-work" / "outbox",
            notification_payload(
                "merged" if merged else "completed",
                feature_dir.name,
                "merged" if merged else "ready",
                "Delivery gates passed",
                gated_sha,
                pr.url,
            ),
        )
        return {
            "pr": pr.url,
            "risk": assessment.effective,
            "checks_passed": checks_passed,
            "merged": merged,
            "completed_at": dt.datetime.now(dt.UTC).isoformat(),
        }
    finally:
        # Successful cleanup is intentionally left explicit; a delivery result
        # or failure must remain inspectable until the caller requests cleanup.
        pass


def _record_weakening_pass(
    event_store,
    inspection,
    *,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    final_validation_accepted_event_sequence: int,
    command_identity: str,
):
    data = {
        **inspection.event_data(),
        "final_validation_accepted_event_sequence": (
            final_validation_accepted_event_sequence
        ),
        "command_identity": command_identity,
    }
    for event in reversed(event_store.read()):
        if event.kind != "weakening" or event.head_sha != head_sha:
            continue
        if event.result == "PASS" and event.data == data:
            return event
        break
    return event_store.append(
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        phase="delivery",
        kind="weakening",
        result="PASS",
        head_sha=head_sha,
        data=data,
    )


def _inspect_and_record_current_weakening(
    repo: Path,
    event_store: EventStore,
    *,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    default_branch: str,
):
    head_sha = git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    patch = git_utils.run_git(
        repo, ["diff", f"{default_branch}...HEAD", "--no-ext-diff"]
    ).stdout
    inspection = weakening.inspect_patch(patch)
    if inspection.blocking_findings:
        raise RuntimeError("High-confidence test weakening detected")
    accepted = next(
        (
            event
            for event in reversed(event_store.read())
            if event.kind == "final-validation-accepted"
            and event.phase == "post-evidence"
            and event.result == "PASS"
            and event.head_sha == head_sha
            and event.feature == feature
            and event.repository == repository
            and event.branch == branch
            and event.worktree == worktree
        ),
        None,
    )
    if accepted is None:
        raise ValueError("Missing final-validation-accepted PASS for current HEAD")
    accepted_data = accepted.data or {}
    command_identity = accepted_data.get("command_identity")
    if (
        accepted_data.get("exact_head_sha") != head_sha
        or not isinstance(command_identity, str)
        or re.fullmatch(r"[0-9a-f]{64}", command_identity) is None
    ):
        raise ValueError("Final-validation acceptance identity mismatched")
    _record_weakening_pass(
        event_store,
        inspection,
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        head_sha=head_sha,
        final_validation_accepted_event_sequence=accepted.sequence,
        command_identity=command_identity,
    )
    return inspection


def _require_current_review_weakening(
    event_store: EventStore,
    *,
    head_sha: str,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    final_validation_accepted_event_sequence: int,
):
    return review.require_authoritative_weakening_event(
        event_store.read(),
        head_sha,
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        final_validation_accepted_event_sequence=(
            final_validation_accepted_event_sequence
        ),
    )


def _finalize_and_record_weakening(
    repo: Path,
    feature_dir: Path,
    config,
    event_store: EventStore,
    repository: str,
    branch: str,
    default_branch: str,
):
    _finalize_delivery_evidence(
        repo, feature_dir, config, event_store, repository, branch
    )
    return _inspect_and_record_current_weakening(
        repo,
        event_store,
        feature=feature_dir.name,
        repository=repository,
        branch=branch,
        worktree=str(repo),
        default_branch=default_branch,
    )


def _pr_body(
    feature: str,
    assessment,
    review_result,
    weakening_findings,
    events=(),
    validated_head: str = "",
    final_binding=None,
    review_identity_digest: str = "",
) -> str:
    validation_sequence = (
        final_binding.final_validation_accepted_event_sequence
        if final_binding
        else "missing"
    )
    log_cutoff = final_binding.included_event_sequence if final_binding else 0
    log_path = final_binding.log_path if final_binding else "missing"
    log_blob = final_binding.log_blob_sha if final_binding else "missing"
    snapshot_sequence = (
        final_binding.snapshot_event_sequence if final_binding else "missing"
    )
    result_digest = (
        final_binding.validation_result_digest if final_binding else "missing"
    )
    review_findings = "\n".join(
        f"- Finding {index}: severity={finding.severity}; "
        f"required={str(finding.required).lower()}; "
        f"category={finding.category}; file={finding.file}; "
        f"description={finding.description}"
        for index, finding in enumerate(review_result.findings, start=1)
    ) or "- None"
    return (
        f"## Feature\n\n`{feature}`\n\n## Risk\n\n{assessment.effective}: "
        f"{', '.join(assessment.reasons)}\n\n## Validation\n\n"
        "Mechanical validation passed.\n\n"
        f"Tracked validation log cutoff event: {log_cutoff}. "
        f"Tracked validation log: `{log_path}`; blob `{log_blob}`. "
        f"Snapshot event: {snapshot_sequence}. "
        f"Final validation event: {validation_sequence}. "
        f"Validation result digest: `{result_digest}`. "
        f"Validated HEAD: `{validated_head}`.\n\n"
        f"## Independent review\n\n{review_result.result}; "
        f"{len(review_result.findings)} findings.\n\n{review_findings}\n\n"
        f"Review identity digest: `{review_identity_digest}`.\n\n"
        f"## Test weakening\n\n{len(weakening_findings)} findings.\n"
    )


def _finalize_delivery_evidence(
    repo: Path,
    feature_dir: Path,
    config,
    event_store: EventStore,
    repository: str,
    branch: str,
):
    (feature_dir / "validation-log.md").write_text(
        render_validation_log(
            event_store.read(),
            feature_dir.name,
            evidence_snapshot.contract_digest(feature_dir),
            evidence_snapshot.utc_now(),
        ),
        encoding="utf-8",
    )
    paths = git_utils.changed_paths(repo)
    validation.validate_scope(paths, config)
    git_utils.diff_check(repo)
    git_utils.commit(
        repo, paths, f"docs({feature_dir.name}): finalize tracked evidence snapshot"
    )
    snapshot = evidence_snapshot.record_snapshot(
        event_store,
        repo=repo,
        feature_dir=feature_dir,
        repository=repository,
        branch=branch,
        worktree=str(repo),
    )
    started_at = evidence_snapshot.utc_now()
    result = validation.run_named(repo, config, "full")
    completed_at = evidence_snapshot.utc_now()
    attempt = evidence_snapshot.record_final_validation_attempt(
        event_store,
        repo=repo,
        feature_dir=feature_dir,
        repository=repository,
        branch=branch,
        worktree=str(repo),
        snapshot=snapshot,
        result=result,
        started_at=started_at,
        completed_at=completed_at,
    )
    if not result.succeeded:
        raise RuntimeError("Post-evidence final validation failed")
    evidence_snapshot.record_final_validation_accepted(
        event_store,
        repo=repo,
        feature_dir=feature_dir,
        repository=repository,
        branch=branch,
        worktree=str(repo),
        snapshot=snapshot,
        attempt=attempt,
    )
    return evidence_snapshot.require_final_evidence(
        repo,
        feature_dir,
        event_store.read(),
        git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip(),
    )


def _repair_and_commit(
    repo: Path, feature_dir: Path, config, repair_id: str, failure: str
) -> str:
    task = Task(repair_id, f"Repair {repair_id} findings", False, (), ("full",), -1)
    prompt = codex_runner.render_prompt(repo, feature_dir, task, failure)
    result = codex_runner.run(repo, prompt)
    if result.returncode:
        raise _safe_command_failure(f"{repair_id} repair Codex failed", result.stderr)
    paths = git_utils.changed_paths(repo)
    if not paths:
        raise RuntimeError(f"{repair_id} repair produced no changes")
    validation.validate_scope(paths, config)
    git_utils.diff_check(repo)
    check = validation.run_named(repo, config, "full")
    if not check.succeeded:
        raise _safe_command_failure(
            f"{repair_id} repair validation failed", check.stderr or check.stdout
        )
    git_utils.commit(repo, paths, f"fix: address {repair_id.lower()} findings")
    head = git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    exact = validation.run_named(repo, config, "full")
    if not exact.succeeded:
        raise _safe_command_failure(
            f"{repair_id} post-commit exact-HEAD validation failed",
            exact.stderr or exact.stdout,
        )
    if git_utils.changed_paths(repo):
        raise RuntimeError(f"{repair_id} validation changed tracked contents")
    if git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip() != head:
        raise RuntimeError(f"{repair_id} HEAD changed during validation")
    return head


def _record_delivery_evidence(
    repo: Path, feature_dir: Path, pr_url: str, checks_passed: bool, risk: str
) -> None:
    path = feature_dir / "validation-log.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Live E2E delivery not yet started.",
        "Live E2E delivery completed through PR and CI monitoring.",
    )
    replacements = {
        "- [ ] `make validate` passed": "- [x] `make validate` passed",
        "- [ ] Isolated worktree used": "- [x] Isolated worktree used",
        "- [ ] Independent review passed": "- [x] Independent review passed",
        "- [ ] Exactly one PR created": "- [x] Exactly one PR created",
        "- [ ] GitHub Actions passed": "- [x] GitHub Actions passed"
        if checks_passed
        else "- [ ] GitHub Actions passed",
        "- [ ] PR remained unmerged": "- [x] PR remained unmerged",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text += (
        f"\n| 1 | LIVE DELIVERY | PASS | worktree isolated; review passed; "
        f"PR={pr_url}; checks={'passed' if checks_passed else 'failed'}; "
        f"risk={risk}; unmerged |\n"
    )
    path.write_text(text, encoding="utf-8")
    paths = git_utils.changed_paths(repo)
    git_utils.commit(repo, paths, "docs: record live delivery evidence")


def _validate_delivery_evidence(repo: Path, feature_dir: Path, config) -> None:
    check = validation.run_named(repo, config, "full")
    if not check.succeeded:
        raise _safe_command_failure(
            "Delivery evidence validation failed", check.stderr or check.stdout
        )
    result, _, _ = review.run_review(repo, feature_dir)
    if result.result != "pass" or result.required_findings:
        raise RuntimeError("Delivery evidence independent review did not pass")


def _safe_command_failure(label: str, output: str) -> RuntimeError:
    """Build a diagnostic exception without exposing command output secrets."""
    return RuntimeError(f"{label}: {redact(output, 4000)}")


def record_review_failure_event(
    event_store: EventStore,
    *,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    shard: str,
    identity,
    attempt: int,
    error: Exception,
):
    is_timeout = isinstance(error, review.ReviewTimeout)
    is_budget_exhaustion = isinstance(error, ReviewBudgetExhausted)
    error_class = type(error).__name__
    safe_error = safe_error_detail(error) if is_timeout else error_class
    signature = safe_error[-1000:] if is_timeout else f"{shard}:{error_class}"
    diagnostic = {}
    if is_timeout:
        allowed = {
            "shard",
            "head_sha",
            "attempt",
            "configured_timeout",
            "elapsed_seconds",
            "command_id",
            "prompt_chars",
            "prompt_bytes",
            "input_digest",
            "stdout_tail",
            "stderr_tail",
            "process_status",
            "pid",
            "root_pid",
            "process_group_id",
            "termination",
            "process_group_terminated",
            "tracked_descendant_pids",
            "observed_descendant_pids",
            "term_targets",
            "kill_targets",
            "termination_confirmed",
            "known_survivors",
        }
        diagnostic = redact_value(
            {key: value for key, value in error.diagnostic.items() if key in allowed}
        )
    elif is_budget_exhaustion:
        diagnostic = {
            "limit": error.limit,
            "used": error.used,
            "retryable": False,
            "resume_boundary": "explicit-delivery-invocation",
        }
    return event_store.append(
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        phase="review",
        kind="review-shard",
        result=(
            "HUMAN_REQUIRED"
            if is_budget_exhaustion
            or (is_timeout and diagnostic.get("known_survivors"))
            else "TIMEOUT"
            if is_timeout
            else "INVALID"
        ),
        head_sha=head_sha,
        detail=safe_error,
        data={
            "shard": shard,
            "identity_digest": identity.digest,
            "failure_signature": signature,
            "attempt": attempt,
            "diagnostic": diagnostic,
            "error_class": error_class,
        },
    )


def require_review_capacity_or_stop(
    budget: ReviewCallBudget,
    *,
    event_store: EventStore,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    shard: str,
    identity,
    attempt: int,
) -> None:
    """Record one non-retryable stop before an over-budget reviewer call."""
    try:
        budget.require_capacity()
    except ReviewBudgetExhausted as error:
        record_review_failure_event(
            event_store,
            feature=feature,
            repository=repository,
            branch=branch,
            worktree=worktree,
            head_sha=head_sha,
            shard=shard,
            identity=identity,
            attempt=attempt,
            error=error,
        )
        raise ReviewResumeRequired(
            "Independent review call budget exhausted; "
            "explicit delivery resume required"
        ) from error


def run_prepared_review_with_retries(
    repo: Path,
    prepared,
    budget: ReviewCallBudget,
    max_attempts: int,
    *,
    event_store: EventStore,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    shard: str,
):
    """Run retryable reviewer failures while stopping exhaustion immediately."""
    last_error = None
    for shard_attempt in range(1, max_attempts + 1):
        require_review_capacity_or_stop(
            budget,
            event_store=event_store,
            feature=feature,
            repository=repository,
            branch=branch,
            worktree=worktree,
            head_sha=head_sha,
            shard=shard,
            identity=prepared.identity,
            attempt=shard_attempt,
        )
        try:
            return budget.run(
                lambda: review.run_prepared(
                    repo, prepared, attempt=shard_attempt
                )
            )
        except Exception as error:
            last_error = error
            failure_event = record_review_failure_event(
                event_store,
                feature=feature,
                repository=repository,
                branch=branch,
                worktree=worktree,
                head_sha=head_sha,
                shard=shard,
                identity=prepared.identity,
                attempt=shard_attempt,
                error=error,
            )
            signature = (failure_event.data or {})["failure_signature"]
            if failure_event.result == "HUMAN_REQUIRED":
                raise RuntimeError(
                    "Known reviewer processes survived timeout cleanup"
                ) from error
            if (
                review_shards.matching_failure_count(
                    event_store.read(), prepared.identity, signature
                )
                >= 2
            ):
                raise RuntimeError(
                    f"Independent review shard {shard} repeated identical failure"
                ) from error
    raise RuntimeError(
        f"Independent review shard {shard} retry budget exhausted"
    ) from last_error


def obtain_cached_or_run_prepared_review(
    repo: Path,
    prepared,
    budget: ReviewCallBudget,
    max_attempts: int,
    *,
    event_store: EventStore,
    feature: str,
    repository: str,
    branch: str,
    worktree: str,
    head_sha: str,
    shard: str,
):
    """Reuse one exact PASS or execute the pending prepared reviewer."""
    cached = review.reusable_gate_event(event_store.read(), prepared.identity.digest)
    if cached is not None:
        review_shards.record_reuse_decision(
            event_store,
            source=cached,
            feature=feature,
            repository=repository,
            branch=branch,
            worktree=worktree,
            head_sha=head_sha,
            shard=shard,
            identity_digest=prepared.identity.digest,
        )
        return review.result_from_chunk_event(cached, prepared.identity.digest), "", True
    result, stderr = run_prepared_review_with_retries(
        repo,
        prepared,
        budget,
        max_attempts,
        event_store=event_store,
        feature=feature,
        repository=repository,
        branch=branch,
        worktree=worktree,
        head_sha=head_sha,
        shard=shard,
    )
    return result, stderr, False
