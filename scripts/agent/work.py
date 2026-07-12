from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent import (
        adapters,
        codex_runner,
        contract_migration,
        delivery,
        evidence_snapshot,
        git_utils,
        qualification,
        recovery,
        validation,
    )
    from agent import (
        doctor as doctor_module,
    )
    from agent import (
        release as release_module,
    )
    from agent import (
        worktree as worktree_module,
    )
    from agent.budget import Budget
    from agent.events import EventStore, render_validation_log
    from agent.evidence import redact
    from agent.notifications import payload as notification_payload
    from agent.notifications import write_outbox
    from agent.parser import (
        ContractError,
        Task,
        load_config,
        mark_complete,
        parse_tasks,
        resolve_feature,
    )
    from agent.policy import load_policy
    from agent.quality import validate as validate_quality
    from agent.queue import Queue
    from agent.scope_approval import (
        apply as apply_scope,
    )
    from agent.scope_approval import (
        preview as preview_scope,
    )
    from agent.scope_approval import (
        preview_request as preview_scope_request,
    )
    from agent.scope_approval import (
        request as request_scope,
    )
    from agent.spec_lint import lint_feature, require_lint
    from agent.state import (
        RunState,
        contract_digest,
        read_state,
        verify_resume,
        write_state,
    )
    from agent.state import (
        abort as abort_state,
    )
else:
    from . import (
        adapters,
        codex_runner,
        contract_migration,
        delivery,
        evidence_snapshot,
        git_utils,
        qualification,
        recovery,
        validation,
    )
    from . import (
        doctor as doctor_module,
    )
    from . import (
        release as release_module,
    )
    from . import (
        worktree as worktree_module,
    )
    from .budget import Budget
    from .events import EventStore, render_validation_log
    from .evidence import redact
    from .notifications import payload as notification_payload
    from .notifications import write_outbox
    from .parser import (
        ContractError,
        Task,
        load_config,
        mark_complete,
        parse_tasks,
        resolve_feature,
    )
    from .policy import load_policy
    from .quality import validate as validate_quality
    from .queue import Queue
    from .scope_approval import (
        apply as apply_scope,
    )
    from .scope_approval import (
        preview as preview_scope,
    )
    from .scope_approval import (
        preview_request as preview_scope_request,
    )
    from .scope_approval import (
        request as request_scope,
    )
    from .spec_lint import lint_feature, require_lint
    from .state import (
        RunState,
        contract_digest,
        read_state,
        verify_resume,
        write_state,
    )
    from .state import (
        abort as abort_state,
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def feature_context(repo: Path, feature: str):
    feature_dir = resolve_feature(repo, feature)
    policy = load_policy(repo) if (repo / ".agent-policy.toml").is_file() else None
    config = load_config(feature_dir, policy)
    if config.version == 2 and policy:
        require_lint(feature_dir, policy)
    tasks = parse_tasks(feature_dir / "tasks.md", set(config.commands))
    return feature_dir, config, tasks


def spec_lint(repo: Path, feature: str) -> int:
    feature_dir = resolve_feature(repo, feature)
    report = lint_feature(feature_dir, load_policy(repo))
    print(
        json.dumps(
            {
                "feature": feature_dir.name,
                "passed": report.passed,
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
        )
    )
    return 0 if report.passed else 1


def resume(repo: Path, feature: str) -> int:
    feature_dir = resolve_feature(repo, feature)
    path = repo / ".agent-work" / feature_dir.name / "state.json"
    state = read_state(path)
    work_repo = Path(state.worktree)
    work_feature = resolve_feature(work_repo, feature_dir.name)
    verify_resume(
        state,
        git_utils.branch(work_repo),
        git_utils.run_git(work_repo, ["rev-parse", "HEAD"]).stdout.strip(),
        contract_digest(work_feature),
        git_utils.changed_paths(work_repo),
    )
    return work(work_repo, feature, resume_mode=True, state_root=repo)


def abort(repo: Path, feature: str) -> int:
    feature_dir = resolve_feature(repo, feature)
    path = repo / ".agent-work" / feature_dir.name / "state.json"
    result = abort_state(path, dt.datetime.now(dt.UTC).isoformat())
    print(json.dumps({"feature": result.feature, "status": result.status}, indent=2))
    return 0


def dry_run(repo: Path, feature: str) -> int:
    feature_dir, config, tasks = feature_context(repo, feature)
    pending = [task for task in tasks if not task.completed]
    payload = {
        "feature": feature_dir.name,
        "branch": git_utils.branch(repo),
        "completed_tasks": [task.task_id for task in tasks if task.completed],
        "incomplete_tasks": [task.task_id for task in pending],
        "next_task": pending[0].task_id if pending else None,
        "planned_commands": [
            list(config.commands[name]) for name in pending[0].validations
        ]
        if pending
        else [["make", "validate"]],
    }
    print(json.dumps(payload, indent=2))
    return 0


def status(repo: Path, feature: str) -> int:
    feature_dir, _, tasks = feature_context(repo, feature)
    pending = [task for task in tasks if not task.completed]
    run_root = repo / ".agent-work" / feature_dir.name
    latest = (
        sorted(run_root.iterdir())[-1].name
        if run_root.is_dir() and list(run_root.iterdir())
        else None
    )
    payload = {
        "branch": git_utils.branch(repo),
        "feature": feature_dir.name,
        "completion_percent": round(100 * (len(tasks) - len(pending)) / len(tasks)),
        "next_task": pending[0].task_id if pending else None,
        "latest_log": latest,
        "git_state": "clean" if not git_utils.changed_paths(repo) else "dirty",
    }
    print(json.dumps(payload, indent=2))
    return 0


def work(
    repo: Path,
    feature: str,
    *,
    resume_mode: bool = False,
    state_root: Path | None = None,
) -> int:
    feature_dir, config, tasks = feature_context(repo, feature)
    if not resume_mode:
        git_utils.ensure_safe_start(repo)
    policy = load_policy(repo) if (repo / ".agent-policy.toml").is_file() else None
    budget = Budget((policy.max_elapsed_minutes if policy else 120) * 60)
    pending = [task for task in tasks if not task.completed]
    if len(pending) > config.max_tasks:
        raise ContractError(
            f"Incomplete task count {len(pending)} exceeds max_tasks {config.max_tasks}"
        )
    evidence_repo = state_root or repo
    run_dir = _new_run_dir(evidence_repo, feature_dir.name)
    event_store = EventStore(
        evidence_repo / ".agent-work" / feature_dir.name / "events.jsonl"
    )
    state_path = evidence_repo / ".agent-work" / feature_dir.name / "state.json"
    base = git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    for task in pending:
        budget.check()
        current = RunState(
            1,
            feature_dir.name,
            git_utils.branch(repo),
            base,
            git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip(),
            contract_digest(feature_dir),
            task.task_id,
            0,
            "implement",
            None,
            tuple(git_utils.changed_paths(repo)),
            "running",
            str(repo),
            dt.datetime.now(dt.UTC).isoformat(),
        )
        write_state(state_path, current)
        try:
            _execute_task(repo, feature_dir, config, task, run_dir)
            event_store.append(
                feature=feature_dir.name,
                repository=str(evidence_repo),
                branch=git_utils.branch(repo),
                worktree=str(repo),
                phase="task",
                kind="task-complete",
                result="PASS",
                head_sha=git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip(),
                detail=task.task_id,
            )
        except Exception as error:
            failure_class = recovery.classify("work", 1, str(error))
            failed = RunState(
                **{
                    **current.__dict__,
                    "status": "failed",
                    "failure_class": failure_class,
                    "changed_paths": tuple(git_utils.changed_paths(repo)),
                    "updated_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            )
            write_state(state_path, failed)
            kind = "scope-request" if failure_class == "scope" else "failure"
            scope_paths = _scope_paths(error) if failure_class == "scope" else ()
            event_store.append(
                feature=feature_dir.name,
                repository=str(evidence_repo),
                branch=git_utils.branch(repo),
                worktree=str(repo),
                phase="task",
                kind=kind,
                result="FAIL",
                head_sha=git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip(),
                detail=str(error),
                data={"task": task.task_id, "paths": list(scope_paths)},
            )
            write_outbox(
                evidence_repo / ".agent-work" / "outbox",
                notification_payload(
                    "human-required",
                    feature_dir.name,
                    "stopped",
                    str(error),
                    failed.head_commit,
                ),
            )
            raise
        tasks = parse_tasks(feature_dir / "tasks.md", set(config.commands))
    _final_validation(
        repo, feature_dir, config, tasks, run_dir, event_store, evidence_repo
    )
    budget.check()
    completed = RunState(
        1,
        feature_dir.name,
        git_utils.branch(repo),
        base,
        git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip(),
        contract_digest(feature_dir),
        None,
        0,
        "complete",
        None,
        (),
        "complete",
        str(repo),
        dt.datetime.now(dt.UTC).isoformat(),
    )
    write_state(state_path, completed)
    print(f"Feature complete: {feature_dir.name}")
    return 0


def _execute_task(
    repo: Path, feature_dir: Path, config, task: Task, run_dir: Path
) -> None:
    previous_failure: str | None = None
    previous_signature: str | None = None
    skip_codex = False
    for attempt in range(1, config.max_attempts_per_task + 1):
        attempt_dir = run_dir / f"{task.task_id}-attempt-{attempt}"
        attempt_dir.mkdir(parents=True)
        prompt = codex_runner.render_prompt(repo, feature_dir, task, previous_failure)
        (attempt_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (attempt_dir / "task.txt").write_text(
            f"{task.task_id}: {task.title}\n", encoding="utf-8"
        )
        result = (
            codex_runner.CodexResult(0, "Codex retry skipped by recovery policy", "")
            if skip_codex
            else codex_runner.run(repo, prompt)
        )
        skip_codex = False
        (attempt_dir / "stdout.txt").write_text(redact(result.stdout), encoding="utf-8")
        (attempt_dir / "stderr.txt").write_text(redact(result.stderr), encoding="utf-8")
        (attempt_dir / "exit-code.txt").write_text(
            str(result.returncode), encoding="utf-8"
        )
        (attempt_dir / "telemetry.json").write_text(
            json.dumps(
                {
                    "duration_seconds": result.duration_seconds,
                    "tokens_used": result.tokens_used,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            changed = git_utils.changed_paths(repo)
            if changed:
                validation.validate_scope(changed, config)
            if result.returncode:
                raise RuntimeError(
                    f"Codex exited {result.returncode}: "
                    f"{(result.stderr or result.stdout)[-4000:]}"
                )
            results = validation.validate_task(repo, config, task.validations)
            _write_validation(attempt_dir, results)
            mark_complete(feature_dir / "tasks.md", task)
            _append_log(
                feature_dir, task.task_id, attempt, "PASS", "task validation passed"
            )
            paths = git_utils.changed_paths(repo)
            validation.validate_scope(paths, config)
            commit_hash = git_utils.commit(
                repo, paths, f"feat({feature_dir.name}): complete {task.task_id}"
            )
            (attempt_dir / "commit-hash.txt").write_text(
                commit_hash + "\n", encoding="utf-8"
            )
            return
        except (RuntimeError, ValueError, git_utils.GitError) as error:
            failure = str(error)
            failure_class = recovery.classify(
                task.validations[0] if task.validations else "codex",
                result.returncode,
                failure,
            )
            recovery_policy = recovery.policy_for(
                failure_class, config.max_attempts_per_task
            )
            signature = failure[-4000:]
            _append_log(
                feature_dir,
                task.task_id,
                attempt,
                "FAIL",
                f"class={failure_class} strategy={recovery_policy.strategy} {failure}",
            )
            (attempt_dir / "validation.txt").write_text(
                failure + "\n", encoding="utf-8"
            )
            if not recovery_policy.retryable:
                raise RuntimeError(
                    f"Unsafe {failure_class} failure requires human review: {failure}"
                ) from error
            if signature == previous_signature:
                raise RuntimeError(
                    f"Identical failure repeated for {task.task_id}: {failure}"
                ) from error
            previous_failure, previous_signature = failure, signature
            if attempt >= recovery_policy.max_attempts:
                break
            if recovery_policy.strategy == "rerun-without-change":
                skip_codex = True
            elif recovery_policy.strategy == "run-allowlisted-setup-once":
                setup = subprocess.run(
                    ["make", "setup"],
                    cwd=repo,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=900,
                )
                if setup.returncode:
                    raise RuntimeError(
                        "Allowlisted setup failed: "
                        f"{(setup.stderr or setup.stdout)[-4000:]}"
                    ) from error
    raise RuntimeError(f"Retry limit reached for {task.task_id}")


def _final_validation(
    repo: Path,
    feature_dir: Path,
    config,
    tasks: list[Task],
    run_dir: Path,
    event_store: EventStore | None = None,
    evidence_repo: Path | None = None,
) -> str:
    if any(not task.completed for task in tasks):
        raise RuntimeError("Final validation requires all tasks to be complete")
    previous_signature = None
    repair_task = Task(
        "FINAL", "Repair project-wide validation", False, (), ("full",), -1
    )
    for attempt in range(1, config.max_final_validation_attempts + 1):
        result = validation.run_named(repo, config, "full")
        final_dir = run_dir / f"final-attempt-{attempt}"
        final_dir.mkdir()
        _write_validation(final_dir, [result])
        _append_log(
            feature_dir,
            "FINAL",
            attempt,
            "PASS" if result.succeeded else "FAIL",
            (result.stderr or result.stdout)[-4000:],
        )
        if result.succeeded:
            if event_store is not None:
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
            if paths:
                validation.validate_scope(paths, config)
                commit_hash = git_utils.commit(
                    repo, paths, f"fix({feature_dir.name}): pass final validation"
                )
                (final_dir / "commit-hash.txt").write_text(
                    commit_hash + "\n", encoding="utf-8"
                )
            validated_head = git_utils.run_git(
                repo, ["rev-parse", "HEAD"]
            ).stdout.strip()
            snapshot = None
            if event_store is not None:
                snapshot = evidence_snapshot.record_snapshot(
                    event_store,
                    repo=repo,
                    feature_dir=feature_dir,
                    repository=str(evidence_repo or repo),
                    branch=git_utils.branch(repo),
                    worktree=str(repo),
                )
            started_at = evidence_snapshot.utc_now()
            exact = validation.run_named(repo, config, "full")
            completed_at = evidence_snapshot.utc_now()
            _write_validation(final_dir, [exact])
            if event_store is not None and snapshot is not None:
                evidence_snapshot.record_final_validation(
                    event_store,
                    repo=repo,
                    feature_dir=feature_dir,
                    repository=str(evidence_repo or repo),
                    branch=git_utils.branch(repo),
                    worktree=str(repo),
                    snapshot=snapshot,
                    result=exact,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            if not exact.succeeded:
                raise RuntimeError(
                    "Post-evidence exact-HEAD validation failed: "
                    f"{(exact.stderr or exact.stdout)[-4000:]}"
                )
            if git_utils.changed_paths(repo):
                raise RuntimeError(
                    "Final validation changed tracked repository contents"
                )
            if (
                git_utils.run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
                != validated_head
            ):
                raise RuntimeError("HEAD changed during final validation")
            return validated_head
        signature = result.signature()
        if signature == previous_signature:
            raise RuntimeError("Identical final validation failure repeated")
        previous_signature = signature
        if attempt < config.max_final_validation_attempts:
            failure = (
                f"{result.name} exited {result.returncode}: "
                f"{(result.stderr or result.stdout)[-8000:]}"
            )
            prompt = codex_runner.render_prompt(repo, feature_dir, repair_task, failure)
            (final_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            repair = codex_runner.run(repo, prompt)
            (final_dir / "stdout.txt").write_text(
                redact(repair.stdout), encoding="utf-8"
            )
            (final_dir / "stderr.txt").write_text(
                redact(repair.stderr), encoding="utf-8"
            )
            (final_dir / "exit-code.txt").write_text(
                str(repair.returncode), encoding="utf-8"
            )
            paths = git_utils.changed_paths(repo)
            if paths:
                validation.validate_scope(paths, config)
                git_utils.diff_check(repo)
            if repair.returncode:
                raise RuntimeError(
                    f"Final repair Codex invocation failed: {repair.stderr[-4000:]}"
                )
    raise RuntimeError("Final validation failed; human review is required")


def _new_run_dir(repo: Path, feature: str) -> Path:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    path = repo / ".agent-work" / feature / stamp
    path.mkdir(parents=True)
    return path


def _write_validation(directory: Path, results) -> None:
    text = "\n\n".join(
        f"[{r.name}] {' '.join(r.command)}\nexit={r.returncode}\n{r.stdout}\n{r.stderr}"
        for r in results
    )
    (directory / "validation.txt").write_text(redact(text), encoding="utf-8")


def _append_log(
    feature_dir: Path, task: str, loop: int, result: str, notes: str
) -> None:
    path = feature_dir / "validation-log.md"
    safe_notes = " ".join(redact(notes, 500).replace("|", "\\|").split())[-500:]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"| {loop} | {task} | {result} | {safe_notes} |\n")


def _scope_paths(error: BaseException) -> tuple[str, ...]:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, validation.ScopeViolation):
            return current.paths
        current = current.__cause__ or current.__context__
    return ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Developer automation framework")
    parser.add_argument(
        "command",
        choices=(
            "run",
            "dry-run",
            "status",
            "spec-lint",
            "resume",
            "abort",
            "deliver",
            "deliver-dry-run",
            "detect-stack",
            "init-stack",
            "cleanup-worktree",
            "doctor",
            "approve-scope",
            "approve-scope-dry-run",
            "request-scope",
            "request-scope-dry-run",
            "migrate-contract",
            "migrate-contract-dry-run",
            "queue-add",
            "queue-status",
            "queue-cancel",
            "qualify-stacks",
            "release-check",
            "render-validation-log",
            "quality-check",
            "queue-run",
        ),
    )
    parser.add_argument("--feature")
    parser.add_argument("--stack")
    parser.add_argument("--path")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    repo = repository_root()
    try:
        if (
            args.command
            in {
                "run",
                "dry-run",
                "status",
                "spec-lint",
                "resume",
                "abort",
                "deliver",
                "deliver-dry-run",
                "cleanup-worktree",
                "approve-scope",
                "approve-scope-dry-run",
                "request-scope",
                "request-scope-dry-run",
                "migrate-contract",
                "migrate-contract-dry-run",
                "queue-add",
                "queue-cancel",
                "render-validation-log",
            }
            and not args.feature
        ):
            parser.error("--feature is required")
        if args.command == "run":
            return work(repo, args.feature)
        if args.command == "dry-run":
            return dry_run(repo, args.feature)
        if args.command == "status":
            return status(repo, args.feature)
        if args.command == "spec-lint":
            return spec_lint(repo, args.feature)
        if args.command == "resume":
            return resume(repo, args.feature)
        if args.command == "abort":
            return abort(repo, args.feature)
        if args.command == "deliver-dry-run":
            print(
                json.dumps(
                    delivery.dry_run(repo, args.feature, load_policy(repo)), indent=2
                )
            )
            return 0
        if args.command == "deliver":
            print(
                json.dumps(
                    delivery.deliver(repo, args.feature, load_policy(repo), work),
                    indent=2,
                )
            )
            return 0
        if args.command == "cleanup-worktree":
            feature_dir = resolve_feature(repo, args.feature)
            path = repo / ".agent-worktrees" / feature_dir.name
            worktree_module.remove_after_success(
                repo, worktree_module.Worktree(path, git_utils.branch(path))
            )
            print(json.dumps({"removed": str(path)}, indent=2))
            return 0
        if args.command == "doctor":
            policy = load_policy(repo)
            checks = doctor_module.run(repo, policy.quality)
            print(
                json.dumps(
                    {
                        "checks": [check.__dict__ for check in checks],
                        "readiness": doctor_module.readiness(
                            checks, policy.auto_merge_low_risk
                        ),
                    },
                    indent=2,
                )
            )
            return 1 if any(check.status == "FAIL" for check in checks) else 0
        if args.command == "quality-check":
            errors = validate_quality(load_policy(repo).quality or {})
            print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
            return 0 if not errors else 1
        if args.command in {"approve-scope", "approve-scope-dry-run"}:
            if not args.path or not args.reason:
                parser.error("--path and --reason are required")
            feature_dir = resolve_feature(repo, args.feature)
            store = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
            function = (
                preview_scope if args.command.endswith("dry-run") else apply_scope
            )
            state_path = repo / ".agent-work" / feature_dir.name / "state.json"
            call = (
                function(feature_dir, args.path, args.reason, store)
                if function is preview_scope
                else function(feature_dir, args.path, args.reason, store, state_path)
            )
            print(json.dumps(call, indent=2))
            return 0
        if args.command in {"request-scope", "request-scope-dry-run"}:
            if not args.path or not args.reason:
                parser.error("--path and --reason are required")
            feature_dir = resolve_feature(repo, args.feature)
            store = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
            state_path = repo / ".agent-work" / feature_dir.name / "state.json"
            function = (
                preview_scope_request
                if args.command.endswith("dry-run")
                else request_scope
            )
            print(
                json.dumps(
                    function(feature_dir, args.path, args.reason, store, state_path),
                    indent=2,
                )
            )
            return 0
        if args.command in {"migrate-contract", "migrate-contract-dry-run"}:
            feature_dir = resolve_feature(repo, args.feature)
            policy = load_policy(repo)
            report = contract_migration.preview(
                feature_dir, set(policy.allowed_make_targets)
            )
            print(json.dumps(report, indent=2))
            if args.command == "migrate-contract" and report["safe"]:
                (feature_dir / "validation.toml").write_text(
                    contract_migration.render_v2(
                        feature_dir, set(policy.allowed_make_targets)
                    ),
                    encoding="utf-8",
                )
            return 0 if report["safe"] else 1
        queue = Queue(repo / ".agent-work" / "queue.json")
        if args.command == "queue-add":
            print(
                json.dumps([job.__dict__ for job in queue.add(args.feature)], indent=2)
            )
            return 0
        if args.command == "queue-status":
            print(json.dumps([job.__dict__ for job in queue.read()], indent=2))
            return 0
        if args.command == "queue-cancel":
            print(
                json.dumps(
                    [job.__dict__ for job in queue.update(args.feature, "cancelled")],
                    indent=2,
                )
            )
            return 0
        if args.command == "queue-run":
            queue.acquire()
            results = []
            try:
                for job in queue.read():
                    if job.status != "queued":
                        continue
                    queue.update(job.feature, "running")
                    try:
                        result = delivery.deliver(
                            repo, job.feature, load_policy(repo), work
                        )
                        queue.update(job.feature, "completed")
                        results.append({"feature": job.feature, "result": result})
                    except Exception as error:
                        queue.update(job.feature, "parked")
                        results.append({"feature": job.feature, "error": str(error)})
            finally:
                queue.release()
            print(json.dumps(results, indent=2))
            return 0
        if args.command == "qualify-stacks":
            print(json.dumps(qualification.qualify(repo), indent=2))
            return 0
        if args.command == "release-check":
            errors = release_module.check(repo)
            print(json.dumps({"passed": not errors, "errors": errors}, indent=2))
            return 0 if not errors else 1
        if args.command == "render-validation-log":
            feature_dir = resolve_feature(repo, args.feature)
            store = EventStore(repo / ".agent-work" / feature_dir.name / "events.jsonl")
            (feature_dir / "validation-log.md").write_text(
                render_validation_log(store.read(), feature_dir.name), encoding="utf-8"
            )
            return 0
        available = adapters.load_adapters(repo)
        if args.command == "detect-stack":
            selected, evidence = adapters.detect(repo, available)
            print(
                json.dumps(
                    {
                        "stack": selected.name,
                        "evidence": evidence,
                        "fallback": selected.fallback,
                    },
                    indent=2,
                )
            )
            return 0
        selected = next((item for item in available if item.name == args.stack), None)
        if selected is None:
            raise ValueError("--stack must name an available adapter")
        print(adapters.write_proposal(repo, selected))
        return 0
    except (ContractError, git_utils.GitError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
