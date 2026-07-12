# Feature specification: Autonomous Delivery Framework

## Status

Implemented

## Background

The template can implement fixed-format tasks with bounded validation, but it
still requires humans to diagnose many failures, resume stopped runs, review
changes, publish pull requests, monitor CI, select stack commands, and decide
whether a change may merge. The next version should automate those activities
while retaining deterministic safety stops for high-risk work.

This feature implements the ten improvements approved in the project roadmap:
spec linting, executable allowlists, resumable state, classified recovery,
test-weakening detection, independent review, PR/CI delivery, risk-gated merge,
Git worktree isolation, and stack adapters.

## Goals

- Reduce human involvement for low-risk, mechanically verifiable changes.
- Provide one delivery entrypoint from approved specification to merged PR.
- Make every autonomous decision reproducible and auditable.
- Improve recovery success without permitting unbounded loops.
- Keep high-risk, subjective, or security-sensitive decisions human-gated.
- Preserve stack independence in the orchestration core.

## Non-goals

- Automatically approving or rewriting an unapproved specification.
- Automatically merging medium- or high-risk changes.
- Bypassing branch protection, required reviews, CI, or repository policies.
- Reading repository secrets, credentials, tokens, or production configuration.
- Deploying, applying production migrations, or changing repository settings.
- Proving subjective product quality without an explicit automated evaluator.
- Running multiple Codex agents concurrently in the first implementation.

## Users

- Developers operating specification-driven AI development repositories.
- Maintainers configuring stack adapters and repository delivery policy.
- Reviewers auditing automated implementation and delivery evidence.

## Requirements

### 1. Specification linting and traceability

- FR-101: `make spec-lint FEATURE=<feature>` MUST validate required artifacts,
  approved status, unique requirement/acceptance/task IDs, task validations,
  task dependencies, dependency cycles, scope contradictions, configured
  limits, and subjective acceptance criteria.
- FR-102: Every requirement MUST map to at least one acceptance criterion and
  task; every task MUST map to at least one requirement and validation.
- FR-103: Machine-readable traceability MUST be declared in
  `validation.toml`, not inferred from arbitrary prose.
- FR-104: `make work` and `make deliver` MUST pass spec lint before invoking
  Codex.

### 2. Executable allowlist

- FR-201: External feature contracts MUST NOT declare arbitrary executable
  argument arrays.
- FR-202: Feature validations MUST reference Make target names matching a
  constrained identifier grammar.
- FR-203: Repository policy MUST define the complete allowlist of executable
  Make targets and fixed framework Git/GitHub operations.
- FR-204: Commands not present in the allowlist MUST fail before execution.

### 3. Resumable state

- FR-301: Every mutating run MUST maintain versioned atomic state below
  `.agent-work/<feature>/state.json`.
- FR-302: State MUST record repository, feature, branch, base/head commits,
  task, attempt, phase, failure class, changed paths, timestamps, and status.
- FR-303: `make work-resume FEATURE=<feature>` MUST verify branch, HEAD, feature
  contract digest, and changed-path consistency before resuming.
- FR-304: `make work-abort FEATURE=<feature>` MUST mark the run aborted without
  deleting or reverting work.

### 4. Failure classification and recovery

- FR-401: Failures MUST be classified as compile, lint, typecheck, unit-test,
  integration-test, timeout, dependency, Codex, scope, secret, contract,
  Git/GitHub, CI, flaky, or unknown.
- FR-402: Recovery policies MUST be finite and selected by failure class.
- FR-403: Scope, secret, contract, and high-risk failures MUST stop without an
  automated bypass attempt.
- FR-404: Potential flaky failures MAY be rerun at most twice and MUST stop if
  outcomes are inconsistent.
- FR-405: Failure signatures and selected recovery strategies MUST be logged.

### 5. Test-weakening detection

- FR-501: The framework MUST inspect Git path/diff metadata for deleted tests,
  added skip/disable markers, removed assertions, reduced validation targets,
  lowered coverage thresholds, and CI condition weakening.
- FR-502: Detection MUST not claim semantic certainty; findings MUST be emitted
  as structured risk evidence.
- FR-503: High-confidence weakening MUST stop delivery; lower-confidence
  findings MUST be supplied to independent review.

### 6. Independent automated review

- FR-601: After mechanical validation, a fresh Codex session MUST review spec,
  plan, tasks, diff, tests, and validation evidence.
- FR-602: Review output MUST conform to a local JSON Schema and contain result,
  severity, category, file, description, and required-remediation fields.
- FR-603: Required high-severity findings MUST enter a bounded repair and
  re-review loop.
- FR-604: Invalid review output, repeated findings, or exhausted limits MUST
  stop delivery.

### 7. PR creation and CI repair

- FR-701: `make deliver FEATURE=<feature>` MUST run spec lint, isolated work,
  final validation, independent review, push the feature branch, and create or
  update a pull request.
- FR-702: GitHub operations MUST use argument-array `gh`/Git commands without
  shell execution and MUST never expose credentials in prompts or logs.
- FR-703: Delivery MUST monitor required PR checks, retrieve failed GitHub
  Actions logs, classify failures, and perform bounded repair/push cycles.
- FR-704: Existing PRs MUST be detected and updated rather than duplicated.
- FR-705: PR bodies MUST summarize specification, changes, risk, validation,
  review findings, and residual risks.

### 8. Risk-gated automatic merge

- FR-801: Features MUST declare `risk = "low" | "medium" | "high"` and affected
  risk domains in `validation.toml`.
- FR-802: Risk MUST be escalated automatically when changed paths or review
  findings match authentication, authorization, billing, migration,
  deployment, CI/CD, security, production, or personal-data domains.
- FR-803: Low-risk PRs MAY merge only when the specification permits auto-merge,
  the worktree is clean, all required checks pass, independent review passes,
  no weakening finding exists, and repository branch protection permits it.
- FR-804: Medium-risk delivery MUST stop after a ready-for-review PR. High-risk
  delivery MUST stop before push unless explicitly approved for that run.
- FR-805: Merge MUST occur through the PR using GitHub's normal protection
  rules; direct pushes to the default branch are forbidden.

### 9. Git worktree isolation

- FR-901: Mutating autonomous work MUST run in a dedicated Git worktree under
  an ignored framework-controlled directory.
- FR-902: Worktree branch and path MUST be derived from validated identifiers.
- FR-903: Existing user worktrees MUST never be removed or reset.
- FR-904: Framework worktree cleanup MUST be explicit, safe, limited to
  framework-owned clean worktrees, and disabled after failed runs by default.
- FR-905: State/status commands MUST identify the active isolated worktree.

### 10. Stack adapters

- FR-1001: Stack-specific initialization MUST live outside the orchestration
  core in declarative adapters.
- FR-1002: Built-in adapters MUST cover generic Make, Python, Node.js, Go, and
  Rust projects; Android/JVM detection MAY map to the generic adapter initially.
- FR-1003: `make detect-stack` MUST report evidence and selected adapter without
  changes.
- FR-1004: `make init-stack STACK=<name>` MUST generate proposed Make command
  mappings without installing dependencies or overwriting customized commands.
- FR-1005: Automatic delivery MUST use only commands exposed by the selected
  adapter and repository policy.

### Cross-cutting requirements

- FR-1101: `make deliver-dry-run` MUST display all planned local and GitHub
  mutations without changing repository or remote state.
- FR-1102: All retry, task, review, CI, and elapsed-time budgets MUST have hard
  maximums enforced by the framework.
- FR-1103: Every phase transition, decision, command, result, commit, push, PR,
  check, and merge MUST be recorded as structured evidence.
- FR-1104: Existing `make work`, dry-run, and status contracts MUST remain
  backward compatible or fail with an actionable migration error.

### Non-functional requirements

- NFR-001: Runtime code MUST use Python 3.11+ standard library only.
- NFR-002: Runtime subprocesses MUST use argument arrays and `shell=False`.
- NFR-003: Tests MUST use `unittest`, temporary repositories, and controlled
  Codex/GitHub stubs; tests MUST NOT mutate real remotes.
- NFR-004: Core modules MUST remain stack-independent.
- NFR-005: JSON/TOML state writes MUST be atomic and recoverable after process
  interruption.
- NFR-006: Logs and prompts MUST bound output size and redact token-like values.
- NFR-007: macOS, Linux, and GitHub Actions MUST be supported.

## Acceptance criteria

- [ ] AC-101: Spec lint tests cover missing traceability, cycles, subjective
  criteria, unapproved specs, and valid contracts.
- [ ] AC-201: Arbitrary executables and unapproved Make targets are rejected.
- [ ] AC-301: Interrupted work can resume only when state, branch, HEAD,
  contract digest, and diff agree; abort never deletes changes.
- [ ] AC-401: Every failure class selects the documented bounded policy and
  identical or unsafe failures stop.
- [ ] AC-501: Representative test and CI weakening diffs generate structured
  findings and high-confidence findings stop delivery.
- [ ] AC-601: Stubbed independent review validates JSON output and exercises
  pass, repair, repeated-finding, invalid-output, and limit paths.
- [ ] AC-701: Stubbed delivery creates one PR, reuses it on resume, handles CI
  success, and performs bounded CI repair without touching a real remote.
- [ ] AC-801: Low risk can merge through a PR only after all gates; medium stops
  at PR; high stops before push; direct default-branch push never occurs.
- [ ] AC-901: Worktree tests prove isolation, collision handling, and protection
  of user-owned or dirty worktrees.
- [ ] AC-1001: Stack detection and initialization tests cover generic, Python,
  Node.js, Go, Rust, ambiguity, and customized Make targets.
- [ ] AC-1101: `make deliver-dry-run` causes no local or remote mutation.
- [ ] AC-1102: `make validate` passes and validation evidence is recorded.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| May the framework merge automatically? | Only low-risk PRs after all mechanical, independent-review, CI, and branch-protection gates. | 2026-07-12 |
| What happens to medium and high risk? | Medium stops at a ready PR; high stops before push unless a human explicitly authorizes that run. | 2026-07-12 |
| May adapters install dependencies? | No. They detect and propose command mappings; project setup remains an explicit allowlisted command. | 2026-07-12 |
| May worktrees be deleted automatically? | Only framework-owned clean worktrees after success; failed or dirty worktrees are preserved. | 2026-07-12 |
| May GitHub credentials enter Codex prompts? | No. GitHub commands run outside Codex and token-like output is redacted. | 2026-07-12 |
| Is Android a first-class adapter in this feature? | No. Android/JVM may be detected but initially uses generic Make mappings. | 2026-07-12 |
| Should multiple features run concurrently? | No. Isolation is implemented now; concurrency scheduling is deferred. | 2026-07-12 |

## Scope

### Allowed changes

- `scripts/agent/**`
- `prompts/**`
- `schemas/**`
- `adapters/**`
- `tests/**`
- `specs/002-autonomous-delivery/**`
- `specs/_template/**`
- `Makefile`
- `.gitignore`
- `README.md`
- `docs/**`
- `.github/workflows/ci.yml`

### Forbidden changes

- Authentication, authorization, billing, or production application logic.
- Production configuration, deployment logic, or database migrations.
- GitHub repository settings, Actions secrets, or branch protection settings.
- Direct pushes to `main` or `master`.
- Destructive reset, clean, forced push, or removal of user-owned worktrees.

## Security and privacy

- Secret and production files MUST not be read, copied, logged, or prompted.
- Automatic merge MUST default off and require both repository policy and a
  low-risk feature declaration.
- GitHub authentication remains owned by `git`/`gh` and outside Codex.
- High-risk detection can escalate risk but can never lower declared risk.
- Any security, scope, contract, or credential anomaly requires human review.
