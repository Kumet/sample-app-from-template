from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import (
    codex_runner,
    git_utils,
    review,
    review_shards,
    state,
    validation,
    weakening,
    worktree,
)
from .events import EventStore
from .evidence import redact
from .gates import require_mergeable
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
    return {
        "feature": feature_dir.name,
        "risk": config.risk,
        "auto_merge_requested": config.auto_merge,
        "spec_warnings": list(report.warnings),
        "pending_tasks": [t.task_id for t in tasks if not t.completed],
        "planned_mutations": [
            "create isolated worktree",
            "run Codex tasks",
            "local commits",
            "push feature branch",
            "create/update PR",
            "monitor CI",
            "merge only when low-risk policy permits",
        ],
    }


def deliver(
    repo: Path,
    feature: str,
    policy: RepositoryPolicy,
    work_function,
    github_factory=GitHubDelivery,
) -> dict:
    git_utils.ensure_safe_start(repo)
    feature_dir = resolve_feature(repo, feature)
    require_lint(feature_dir, policy)
    config = load_config(feature_dir, policy)
    event_store = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
    existing_path = repo / ".agent-worktrees" / feature_dir.name
    resuming = existing_path.exists()
    if resuming:
        marker = existing_path / ".agent-worktree-owned"
        if (
            not marker.is_file()
            or marker.read_text(encoding="utf-8").strip() != feature_dir.name
        ):
            raise RuntimeError("Existing worktree is not framework-owned")
        isolated = worktree.Worktree(existing_path, git_utils.branch(existing_path))
        saved = state.read_state(repo / ".agent-work" / feature_dir.name / "state.json")
        isolated_feature = resolve_feature(existing_path, feature_dir.name)
        current_head = git_utils.run_git(
            existing_path, ["rev-parse", "HEAD"]
        ).stdout.strip()
        if saved.status == "complete":
            if (
                saved.branch != isolated.branch
                or saved.contract_digest != state.contract_digest(isolated_feature)
            ):
                raise RuntimeError("Completed worktree branch or contract changed")
            ancestor = git_utils.run_git(
                existing_path,
                ["merge-base", "--is-ancestor", saved.head_commit, current_head],
                check=False,
            )
            if ancestor.returncode or git_utils.changed_paths(existing_path):
                raise RuntimeError(
                    "Completed worktree has unrelated history or changes"
                )
        else:
            state.verify_resume(
                saved,
                isolated.branch,
                current_head,
                state.contract_digest(isolated_feature),
                git_utils.changed_paths(existing_path),
            )
    else:
        isolated = worktree.create(repo, feature_dir.name, git_utils.branch(repo))
    try:
        if not (resuming and saved.status == "complete"):
            work_function(
                isolated.path, feature_dir.name, state_root=repo, resume_mode=resuming
            )
        isolated_feature = isolated.path / "specs" / feature_dir.name
        patch = git_utils.run_git(
            isolated.path, ["diff", f"{policy.default_branch}...HEAD", "--no-ext-diff"]
        ).stdout
        weakening_findings = weakening.inspect_patch(patch)
        if any(f.required for f in weakening_findings):
            raise RuntimeError("High-confidence test weakening detected")
        evidence = repo / ".agent-work" / feature_dir.name / "delivery"
        evidence.mkdir(parents=True, exist_ok=True)
        review_counter = 0
        review_calls = 0

        def run_review_once():
            nonlocal review_counter, review_calls
            head = git_utils.run_git(
                isolated.path, ["rev-parse", "HEAD"]
            ).stdout.strip()
            shard_results = []

            def obtain(shard, context=None):
                nonlocal review_counter, review_calls
                prepared = review.prepare_review(isolated.path, isolated_feature, shard)
                if context is not None:
                    prepared = review.bind_context(prepared, context)
                cached = review_shards.reusable_event(
                    event_store.read(), prepared.identity.digest
                )
                if cached is not None:
                    event_store.append(
                        feature=feature_dir.name,
                        repository=str(repo),
                        branch=isolated.branch,
                        worktree=str(isolated.path),
                        phase="review",
                        kind="review-reused",
                        result="PASS",
                        head_sha=head,
                        data={
                            "shard": shard,
                            "identity_digest": prepared.identity.digest,
                            "source_sequence": cached.sequence,
                        },
                    )
                    return review_shards.result_from_event(cached)
                last_error = None
                for shard_attempt in range(1, config.max_review_attempts + 1):
                    if review_calls >= policy.max_review_calls:
                        raise RuntimeError("Independent review call budget exhausted")
                    review_calls += 1
                    review_counter += 1
                    try:
                        result, stderr = review.run_prepared(
                            isolated.path, prepared, attempt=shard_attempt
                        )
                        break
                    except Exception as error:
                        last_error = error
                        signature = f"{type(error).__name__}:{str(error)[-1000:]}"
                        diagnostic = (
                            error.diagnostic
                            if isinstance(error, review.ReviewTimeout)
                            else {}
                        )
                        event_store.append(
                            feature=feature_dir.name,
                            repository=str(repo),
                            branch=isolated.branch,
                            worktree=str(isolated.path),
                            phase="review",
                            kind="review-shard",
                            result="TIMEOUT" if diagnostic else "INVALID",
                            head_sha=head,
                            detail=str(error),
                            data={
                                "shard": shard,
                                "identity_digest": prepared.identity.digest,
                                "identity": prepared.identity.payload(),
                                "failure_signature": signature,
                                "attempt": shard_attempt,
                                "diagnostic": diagnostic,
                            },
                        )
                        if (
                            review_shards.matching_failure_count(
                                event_store.read(), prepared.identity, signature
                            )
                            >= 2
                        ):
                            raise RuntimeError(
                                "Independent review shard "
                                f"{shard} repeated identical failure"
                            ) from error
                else:
                    raise RuntimeError(
                        f"Independent review shard {shard} retry budget exhausted"
                    ) from last_error
                prefix = f"review-{review_counter}-{shard}"
                (evidence / f"{prefix}-prompt.txt").write_text(
                    prepared.prompt, encoding="utf-8"
                )
                (evidence / f"{prefix}-stderr.txt").write_text(
                    redact(stderr, 4000), encoding="utf-8"
                )
                payload = {
                    "head_sha": head,
                    "shard": shard,
                    "identity_digest": prepared.identity.digest,
                    "result": result.result,
                    "findings": [f.__dict__ for f in result.findings],
                }
                (evidence / f"{prefix}.json").write_text(
                    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
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
                        **payload,
                        "identity": prepared.identity.payload(),
                        "attempt": review_calls,
                    },
                )
                return result

            for shard in review_shards.SHARDS:
                result = obtain(shard)
                shard_results.append(review_shards.ShardResult(shard, head, result))
            file_findings = tuple(
                finding for item in shard_results for finding in item.result.findings
            )
            if any(f.required and f.severity == "high" for f in file_findings):
                return review.ReviewResult("fail", file_findings)
            integration = obtain(
                "integration",
                {
                    "file_shards": [
                        {
                            "shard": item.shard,
                            "result": item.result.result,
                            "signature": item.result.signature(),
                        }
                        for item in shard_results
                    ]
                },
            )
            shard_results.append(
                review_shards.ShardResult("integration", head, integration)
            )
            return review_shards.aggregate(shard_results, head)

        def repair_review(findings):
            detail = json.dumps([finding.__dict__ for finding in findings], indent=2)
            _repair_and_commit(
                isolated.path, isolated_feature, config, "REVIEW", detail
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
        patch = git_utils.run_git(
            isolated.path, ["diff", f"{policy.default_branch}...HEAD", "--no-ext-diff"]
        ).stdout
        weakening_findings = weakening.inspect_patch(patch)
        if any(f.required for f in weakening_findings):
            raise RuntimeError(
                "High-confidence test weakening detected after review repair"
            )
        paths = git_utils.run_git(
            isolated.path, ["diff", "--name-only", f"{policy.default_branch}...HEAD"]
        ).stdout.splitlines()
        assessment = assess(
            config.risk,
            paths,
            list(review_result.findings) + weakening_findings,
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
            _pr_body(feature_dir.name, assessment, review_result, weakening_findings),
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
        for kind in ("validation", "weakening", "review"):
            event_store.append(
                feature=feature_dir.name,
                repository=str(repo),
                branch=isolated.branch,
                worktree=str(isolated.path),
                phase="delivery",
                kind=kind,
                result="PASS",
                head_sha=gated_sha,
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
            weakening_findings,
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


def _pr_body(feature: str, assessment, review_result, weakening_findings) -> str:
    return (
        f"## Feature\n\n`{feature}`\n\n## Risk\n\n{assessment.effective}: "
        f"{', '.join(assessment.reasons)}\n\n## Validation\n\n"
        "Mechanical validation passed.\n\n"
        f"## Independent review\n\n{review_result.result}; "
        f"{len(review_result.findings)} findings.\n\n"
        f"## Test weakening\n\n{len(weakening_findings)} findings.\n"
    )


def _repair_and_commit(
    repo: Path, feature_dir: Path, config, repair_id: str, failure: str
) -> None:
    task = Task(repair_id, f"Repair {repair_id} findings", False, (), ("full",), -1)
    prompt = codex_runner.render_prompt(repo, feature_dir, task, failure)
    result = codex_runner.run(repo, prompt)
    if result.returncode:
        raise RuntimeError(f"{repair_id} repair Codex failed: {result.stderr[-4000:]}")
    paths = git_utils.changed_paths(repo)
    if not paths:
        raise RuntimeError(f"{repair_id} repair produced no changes")
    validation.validate_scope(paths, config)
    git_utils.diff_check(repo)
    check = validation.run_named(repo, config, "full")
    if not check.succeeded:
        raise RuntimeError(
            f"{repair_id} repair validation failed: "
            f"{(check.stderr or check.stdout)[-4000:]}"
        )
    git_utils.commit(repo, paths, f"fix: address {repair_id.lower()} findings")


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
        raise RuntimeError(
            "Delivery evidence validation failed: "
            f"{(check.stderr or check.stdout)[-4000:]}"
        )
    result, _, _ = review.run_review(repo, feature_dir)
    if result.result != "pass" or result.required_findings:
        raise RuntimeError("Delivery evidence independent review did not pass")
