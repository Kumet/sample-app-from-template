# Feature specification: Production-ready autonomous template

## Status

Implemented

## Background

The template has completed a live medium-risk delivery through specification
lint, isolated implementation, validation, independent repair/review, PR, CI,
and human-approved merge. The live run also exposed operational gaps: evidence
can be split across worktrees, gates need stronger commit identity, scope
approval requires manual state repair, legacy contracts remain permissive,
quality targets may be placeholders, reviews do not scale to large changes,
and there is no doctor, notification, queue, cost budget, or release process.

This feature completes the fourteen approved improvement areas required for a
versioned, work-ready template.

## Goals

- Bind every validation, review, CI result, and merge decision to an exact SHA.
- Use one append-only event stream as the authoritative execution record.
- Automate human-approved scope expansion without destructive state changes.
- Make repository readiness mechanically diagnosable.
- Reject accidentally unconfigured quality gates.
- Track CI runs from PR head SHA to workflow/job logs.
- Scale independent review through complete, fail-closed review shards.
- Remove unsafe legacy execution or provide an explicit migration path.
- Provide useful stack-specific command profiles without overwriting projects.
- Emit structured notifications for human-required states.
- Queue multiple approved features safely with locks and bounded concurrency.
- Enforce and report time, call, retry, and token budgets.
- Validate the framework across representative stack fixtures.
- Establish semantic versioning, changelog, migration, and release readiness.

## Non-goals

- Deploying applications or applying production migrations.
- Changing GitHub repository settings, branch protection, or secrets.
- Automatically approving high-risk work.
- Sending real Slack, Teams, or email messages in tests.
- Installing project dependencies without an explicit allowlisted setup command.
- Running concurrent Codex work by default; concurrency remains opt-in and
  repository locked.
- Guaranteeing subjective product quality without an evaluator contract.

## Users

- Teams creating production repositories from this template.
- Developers operating autonomous low- and medium-risk delivery.
- Reviewers and auditors verifying exact-commit evidence.
- Maintainers releasing compatible versions of the template contract.

## Requirements

### 1. Commit-bound evidence

- REQ-101: Every mutating or evaluative event MUST record repository, feature,
  branch, worktree, phase, command or decision, started/completed timestamps,
  result, and exact HEAD SHA.
- REQ-102: Validation, weakening inspection, independent review, CI, and merge
  eligibility MUST all refer to the same PR HEAD SHA.
- REQ-103: A new commit MUST invalidate earlier SHA-bound gates and force the
  required gates to rerun.
- REQ-104: Merge MUST fail closed if PR HEAD differs from the fully gated SHA.

### 2. Authoritative event log

- REQ-201: `.agent-work/<feature>/events.jsonl` MUST be the append-only source
  of truth for attempts, decisions, approvals, commands, gates, commits, PRs,
  checks, failures, and merge results.
- REQ-202: Event appends MUST be atomic, versioned, ordered, redacted, and
  resilient to a truncated final record.
- REQ-203: `validation-log.md` MUST be generated deterministically from events;
  manually maintained summaries MUST not overwrite richer history.
- REQ-204: Root and isolated worktree commands MUST write to the same event log.

### 3. Scope approval and safe resume

- REQ-301: `make approve-scope FEATURE=<feature> PATH=<glob> REASON=<text>` MUST
  require an existing human-required scope event and a safe glob.
- REQ-302: Approval MUST update spec, validation contract, contract digest,
  root/worktree state, event history, and approval commit without destructive
  reset, clean, or user-worktree deletion.
- REQ-303: Approved scope can only expand allowed paths; it cannot remove
  forbidden paths or lower risk automatically.
- REQ-304: `approve-scope` dry-run MUST show all changes without mutation.

### 4. Repository doctor

- REQ-401: `make doctor` MUST report JSON and readable status for Python, Git,
  Make, Codex, Codex authentication, gh, GitHub authentication, remote, default
  branch, policy, adapter, quality gates, secret checker, CI workflow, ignored
  runtime paths, and merge configuration.
- REQ-402: Doctor MUST distinguish PASS, WARN, FAIL, NOT_APPLICABLE, and MUST
  report readiness separately for local work, medium delivery, and low-risk
  auto-merge.
- REQ-403: Doctor MUST not read secret files or expose authentication output.

### 5. Quality gate initialization

- REQ-501: Placeholder lint, typecheck, test, build, or validate targets MUST
  not silently pass in a project declared ready.
- REQ-502: A disabled quality gate MUST have an explicit reason in repository
  policy and doctor MUST report it.
- REQ-503: `make validate` MUST fail when a required gate remains unconfigured.
- REQ-504: This documentation/template repository MAY explicitly disable
  inapplicable gates with a recorded reason.

### 6. SHA-scoped GitHub Actions

- REQ-601: CI discovery MUST resolve PR number → PR head SHA → workflow run ID →
  job/check IDs and logs.
- REQ-602: CI logs from another SHA or unrelated workflow MUST never enter a
  repair prompt.
- REQ-603: Pending registration, queued, in-progress, success, skipped,
  cancelled, timed-out, and failed states MUST be distinguished.
- REQ-604: CI repair MUST push a new SHA, invalidate old gates, and rerun
  validation/review/CI for the new head.

### 7. Sharded independent review

- REQ-701: Independent review MUST run separate spec/scope, security,
  test-quality/weakening, and maintainability/documentation shards.
- REQ-702: Each shard MUST receive complete relevant artifacts and complete
  assigned diff content; input over limits MUST split further or fail closed.
- REQ-703: File shards MUST be followed by a cross-file integration review.
- REQ-704: Results MUST conform to schemas, carry SHA and shard identity, and be
  aggregated deterministically.
- REQ-705: Review repair MUST invalidate all affected review shards.

### 8. Contract v1 migration

- REQ-801: Autonomous and ordinary work MUST reject version 1 contracts by
  default; arbitrary executable arrays MUST not run.
- REQ-802: `make migrate-contract FEATURE=<feature>` MUST convert known safe
  `make <target>` arrays to version 2 named targets and preserve scope/limits.
- REQ-803: Unknown executables MUST produce a human-required migration report,
  not an executable contract.
- REQ-804: A temporary legacy override, if retained, MUST be explicit,
  repository-policy controlled, logged, and disabled by default.

### 9. Stack adapters

- REQ-901: Adapters MUST detect existing project configuration before proposing
  commands for Python, Node.js, Go, Rust, Android/JVM, and generic Make.
- REQ-902: Proposals MUST include setup, format-check, lint, typecheck where
  applicable, test, build, and validate mappings using detected tools.
- REQ-903: Adapters MUST not install dependencies or overwrite customized
  commands; ambiguity produces a reviewable proposal.
- REQ-904: Fixture repositories MUST validate generated adapter behavior without
  requiring network package installation.

### 10. Notifications

- REQ-1001: Human-required, failed, completed, PR-created, CI-failed, and merged
  events MUST produce a structured notification payload.
- REQ-1002: Built-in sinks MUST include stdout JSON, GitHub PR/Issue comment,
  and a generic executable-free file outbox.
- REQ-1003: Slack, Teams, and email MUST be optional adapters that write an
  outbox payload unless an externally supplied connector performs delivery.
- REQ-1004: Notification failure MUST be logged but MUST not bypass a safety
  stop or change the delivery result.

### 11. Queue and locking

- REQ-1101: `make queue-add FEATURE=<feature>`, `queue-status`, `queue-run`, and
  `queue-cancel` MUST manage approved feature jobs.
- REQ-1102: Queue state MUST be atomic and recoverable with repository and
  feature locks preventing duplicate mutation.
- REQ-1103: Default concurrency MUST be one; configured concurrency MUST respect
  repository, Codex-call, and cost budgets.
- REQ-1104: Human-required jobs MUST be parked while later independent jobs may
  proceed; cancellation MUST not delete diffs or worktrees.

### 12. Budgets and telemetry

- REQ-1201: Policy MUST define hard maxima for elapsed time, Codex calls,
  implementation attempts, review calls, CI repairs, queue concurrency, and
  optionally input/output tokens.
- REQ-1202: Every Codex result MUST record duration and token usage when the CLI
  exposes it, without parsing secrets.
- REQ-1203: `make work-status` and queue status MUST report consumed and
  remaining budgets.
- REQ-1204: Budget exhaustion MUST stop safely with a human-required event.

### 13. Cross-stack qualification

- REQ-1301: Local offline fixtures MUST exercise spec lint, dry-run, adapter,
  worktree, validation, review aggregation, and delivery simulation for at least
  Python, Node.js, and Go.
- REQ-1302: CI MUST run the core suite plus fixture qualification.
- REQ-1303: Live remote delivery is required only for this template repository;
  fixtures MUST never push or mutate a real remote.

### 14. Release management

- REQ-1401: The repository MUST contain `VERSION`, `CHANGELOG.md`, a migration
  guide, compatibility policy, and release checklist.
- REQ-1402: Contract, policy, state, event, and review schema versions MUST be
  documented with supported migrations.
- REQ-1403: `make release-check` MUST verify clean tree, main branch, synced
  remote, version consistency, docs, migrations, full validation, and no
  unreleased blocking items without creating tags or releases.
- REQ-1404: Tag creation and GitHub release publication remain explicit human
  operations outside `release-check`.

### Cross-cutting requirements

- REQ-1501: Runtime implementation MUST remain Python 3.11+ standard library
  only and subprocesses MUST use argument arrays with `shell=False`.
- REQ-1502: Dry-run/status/doctor/migration-preview/approval-preview commands
  MUST not mutate local or remote state.
- REQ-1503: All new remote behavior MUST use controlled stubs in tests.
- REQ-1504: `make validate` MUST pass and no existing safety gate may be
  weakened.

## Acceptance criteria

- [ ] AC-101: Tests prove mismatched validation/review/CI/PR SHAs prevent merge
  and new commits invalidate prior gates.
- [ ] AC-201: A truncated event tail recovers safely and generated validation
  logs contain root and worktree failures in order.
- [ ] AC-301: Approved scope expansion updates both contracts and state, while
  unsafe globs, forbidden removal, and unrequested expansion fail.
- [ ] AC-401: Doctor fixtures distinguish readiness levels and redact auth
  output without opening secret files.
- [ ] AC-501: Required placeholder gates fail; explicitly disabled gates with
  reasons are reported and handled according to policy.
- [ ] AC-601: CI tests select only workflow/job logs belonging to the exact PR
  head SHA and invalidate gates after repair push.
- [ ] AC-701: Small and oversized diffs complete all review shards without
  truncation; invalid/duplicate/repaired shards stop or rerun correctly.
- [ ] AC-801: Version 1 work is rejected by default; safe Make-only migration
  succeeds; unknown executables remain non-executable.
- [ ] AC-901: Python, Node.js, Go, Rust, Android/JVM, and generic adapter fixtures
  detect tools and never overwrite existing Make targets.
- [ ] AC-1001: All notification event types produce schema-valid stdout/outbox
  payloads and remote sinks are stubbed.
- [ ] AC-1101: Queue tests cover ordering, locks, duplicate jobs, parked jobs,
  cancellation, recovery, and bounded concurrency.
- [ ] AC-1201: Time/call/retry/token budgets stop deterministically and status
  reports remaining allowance.
- [ ] AC-1301: Offline Python, Node.js, and Go fixture qualification passes in CI.
- [ ] AC-1401: `make release-check` passes on a simulated clean synced main and
  rejects dirty, wrong-branch, inconsistent-version, or failing-validation cases.
- [ ] AC-1501: Existing framework tests remain green and `make validate` passes.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| What release level is targeted? | `v1.0.0` readiness; this feature creates release artifacts and checks but does not create the tag or GitHub release. | 2026-07-12 |
| Are real external notifications sent? | No by default. Stdout/outbox are real; GitHub/Slack/Teams/email delivery requires an explicit configured connector and is stubbed in tests. | 2026-07-12 |
| Is concurrency enabled by default? | No. Queue concurrency defaults to one; higher values require policy and locks. | 2026-07-12 |
| What happens to version 1? | Rejected by default with a safe migration command; no arbitrary executable array is run. | 2026-07-12 |
| May setup install dependencies? | Only when an existing project explicitly maps and allowlists setup; adapters themselves never install. | 2026-07-12 |
| Does release-check tag or publish? | No. Tag and GitHub release remain explicit human operations. | 2026-07-12 |
| Which live E2E runs are required now? | Template repository medium-risk delivery remains the live proof; Python/Node/Go use offline fixtures to avoid external repositories and package installs. | 2026-07-12 |

## Scope

### Allowed changes

- `.agent-policy.toml`
- `.github/workflows/ci.yml`
- `.gitignore`
- `AGENTS.md`
- `Makefile`
- `README.md`
- `VERSION`
- `CHANGELOG.md`
- `adapters/**`
- `docs/**`
- `fixtures/**`
- `prompts/**`
- `schemas/**`
- `scripts/agent/**`
- `scripts/validate-spec.sh`
- `specs/004-production-ready-template/**`
- `specs/_template/**`
- `specs/README.md`
- `tests/**`

### Forbidden changes

- Authentication, authorization, billing, production application logic,
  deployment, or database migrations.
- GitHub repository settings, branch protection, Actions secrets, or tokens.
- Direct pushes to `main` or `master`.
- Forced push, destructive reset/clean, or removal of user-owned/dirty worktrees.
- Real external notification delivery during tests.
- Automatic tag or GitHub release creation.

## Security and privacy

- Secret files are never opened, copied, prompted, logged, or used as fixtures.
- SHA mismatch, unsafe migration, event corruption beyond a truncated tail,
  lock conflict, budget exhaustion, notification anomaly, or scope expansion
  requires a fail-closed result.
- GitHub and notification credentials remain outside Codex prompts and evidence.
- Event and notification payloads use central redaction before persistence.
- Risk may escalate but cannot be lowered automatically.
