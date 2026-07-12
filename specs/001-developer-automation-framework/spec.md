# Feature specification: Developer Automation Framework

## Status

Implemented

## Background

This repository is intended to be a reusable development template for projects
implemented with Codex. Feature specifications are prepared outside this
framework and placed in a fixed repository format. The framework must then
implement one task at a time, validate the result, retry bounded failures, and
stop safely when automated completion is not possible.

The framework itself must remain independent of application language and
framework. Project-specific setup, linting, testing, type checking, and build
commands are exposed through `make` targets.

## Goals

- Provide `make work FEATURE=<feature-id>` as the standard automation entrypoint.
- Execute exactly one incomplete task at a time with the Codex CLI.
- Validate every task mechanically and mark it complete only after success.
- Retry failed implementation or validation attempts within explicit limits.
- Run the project-wide `make validate` gate after all tasks are complete.
- Record reproducible execution, validation, and commit evidence.
- Prevent work on protected branches, dirty worktrees, forbidden files, and
  out-of-scope paths.
- Support macOS, Linux, and GitHub Actions without project-stack assumptions.

## Non-goals

- Creating, clarifying, or approving feature specifications.
- Pushing branches, merging changes, opening pull requests, or deploying.
- Applying production database migrations or modifying repository settings.
- Guaranteeing automatic completion of acceptance criteria that cannot be
  checked by commands.
- Supporting arbitrary shell commands embedded in task prose.
- Replacing human review for security-sensitive or scope-expanding work.

## Users

- Developers starting new projects from this template.
- AI coding agents implementing approved specifications.
- Reviewers auditing task history, validation results, and resulting commits.

## Requirements

### Functional requirements

- FR-001: `make work FEATURE=<feature-id>` MUST resolve exactly one feature
  directory under `specs/`.
- FR-002: A feature MUST contain `spec.md`, `plan.md`, `tasks.md`,
  `validation.toml`, and `validation-log.md` before execution.
- FR-003: Work MUST stop before invoking Codex when the current branch is
  `main` or `master`.
- FR-004: Work MUST stop before invoking Codex when the Git worktree contains
  changes, except for explicitly ignored runtime logs.
- FR-005: The task parser MUST select the first incomplete task and MUST NOT
  interpret task prose as executable shell input.
- FR-006: Each Codex invocation MUST receive only the selected task, relevant
  specification context, validation names, and scope constraints.
- FR-007: Codex MUST run non-interactively with workspace-write sandboxing and
  approval policy `never`.
- FR-008: Every task attempt MUST run configured task validations, Git diff
  checks, secret checks, forbidden-file checks, and allowed-scope checks.
- FR-009: A task checkbox MUST be updated only after all task gates succeed.
- FR-010: A successful task MUST be committed locally with a deterministic
  message that includes the feature ID and task ID.
- FR-011: Failed attempts MUST provide bounded diagnostic output to a repair
  Codex invocation until the configured retry limit or a stop condition is
  reached.
- FR-012: After all tasks complete, the framework MUST run `make validate` and
  MAY run bounded repair attempts when it fails.
- FR-013: Every invocation MUST write an execution record below
  `.agent-work/<feature>/<timestamp>/` containing prompt, task, stdout, stderr,
  exit code, validation results, and commit hash when present.
- FR-014: `validation-log.md` MUST record every validation or repair loop and
  the final result.
- FR-015: `make work-dry-run FEATURE=<feature-id>` MUST display feature,
  branch, completed tasks, incomplete tasks, next task, and planned commands
  without modifying the repository or invoking Codex.
- FR-016: `make work-status FEATURE=<feature-id>` MUST display branch, feature,
  completion percentage, next task, latest execution summary, and Git state
  without modifying the repository.
- FR-017: Automation MUST stop on protected branches, repeated identical
  failures, retry-limit exhaustion, task-limit exhaustion, scope expansion,
  security violations, or forbidden-file changes.
- FR-018: Runtime state MUST support a safe subsequent invocation after a
  stopped or failed run without silently skipping unfinished work.
- FR-019: Validation command names MUST map to argument arrays declared in
  `validation.toml`; task text MUST never be passed to a shell.
- FR-020: The implementation MUST provide actionable errors for malformed
  feature IDs, ambiguous features, malformed tasks, unknown validations, and
  missing tools.

### Non-functional requirements

- NFR-001: Runtime implementation MUST use the Python standard library only.
- NFR-002: Subprocesses MUST use argument arrays and MUST NOT use `shell=True`.
- NFR-003: Core orchestration MUST not contain Python-, Web-, Android-, AI-,
  CLI-, or other application-stack-specific behavior.
- NFR-004: Project-specific validation MUST be accessed through stable `make`
  targets or explicit argument arrays in `validation.toml`.
- NFR-005: Tests MUST use the standard-library `unittest` framework.
- NFR-006: Tests MUST isolate Git and Codex interactions with temporary
  repositories and controlled executable stubs.
- NFR-007: Log writes MUST avoid deliberately reading secret or forbidden
  files and SHOULD bound captured diagnostic output included in prompts.
- NFR-008: The default retry policy MUST be finite and configurable within
  safe framework-defined maximums.

## Acceptance criteria

- [ ] AC-001: Parser tests cover completed, incomplete, malformed, and empty
  task lists.
- [ ] AC-002: Feature resolution tests reject invalid, missing, and ambiguous
  feature identifiers.
- [ ] AC-003: Dry-run tests prove that no tracked or untracked files are
  created or changed.
- [ ] AC-004: Work refuses to run on `main` and `master` before Codex is called.
- [ ] AC-005: Work refuses to run with a dirty worktree before Codex is called.
- [ ] AC-006: Forbidden and out-of-scope file changes fail the task and are not
  committed or marked complete.
- [ ] AC-007: A successful task is validated, marked complete, logged, and
  committed exactly once.
- [ ] AC-008: A failed validation is retried within the configured limit and
  an identical repeated failure stops the loop.
- [ ] AC-009: Maximum task and final-validation attempt limits prevent infinite
  loops.
- [ ] AC-010: All completed tasks trigger `make validate`, update the validation
  log, and report success without push or merge operations.
- [ ] AC-011: `make work-status` reports completion and Git state without
  modifying the repository.
- [ ] AC-012: The test suite uses only the Python standard library and passes on
  supported macOS and Linux environments.
- [ ] AC-013: `make validate` passes and its result is recorded in this
  feature's `validation-log.md`.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| Is specification generation part of this framework? | No. Specifications are produced separately and consumed in a fixed format. | 2026-07-12 |
| How are project stacks abstracted? | The core is stack-independent; projects expose validation through Make targets and `validation.toml`. | 2026-07-12 |
| Should retries be unlimited until success? | No. Retries are bounded, and identical repeated failures or safety violations stop execution. | 2026-07-12 |
| What Python baseline may the template require? | Python 3.11 or newer; `validation.toml` is parsed with `tomllib`. | 2026-07-12 |
| May task validation commands be supplied directly in task prose? | No. Tasks reference named commands declared as argument arrays in `validation.toml`. | 2026-07-12 |
| Should every successful task create a commit, including changes to `tasks.md` and the validation log? | Yes. Successful implementation, task state, and validation evidence form one atomic local commit. | 2026-07-12 |
| How should dirty state created by a failed Codex attempt be handled before retry or resume? | Preserve the diff, retry repair against it, and stop for human review at the limit; never perform destructive automatic rollback. | 2026-07-12 |
| Is automatic execution of arbitrary commands from an externally produced spec trusted? | No. Only configured validation names and constrained argument-array commands are executable. | 2026-07-12 |

## Scope

### Allowed changes

- `scripts/agent/**`
- `prompts/**`
- `tests/**`
- `specs/001-developer-automation-framework/**`
- `specs/_template/**`
- `scripts/validate-spec.sh`
- `scripts/check-secrets.sh`
- `Makefile`
- `.gitignore`
- `README.md`
- `docs/ai-operation.md`
- `docs/project-context.md`
- `docs/architecture.md`
- `.github/workflows/ci.yml`

### Forbidden changes

- Authentication or authorization behavior.
- Production configuration or deployment behavior.
- Repository secrets or GitHub repository settings.
- Existing user files under `.history/`.
- Git push, merge, reset, clean, and destructive file deletion operations.

## Security and privacy

- The framework MUST NOT read `.env`, `local.properties`, signing keys, private
  keys, credentials, tokens, or production configuration.
- Forbidden file detection MUST operate from Git path metadata and configured
  patterns without opening forbidden files.
- Prompts and logs MUST not intentionally include secret-file contents.
- Codex MUST receive workspace-write sandboxing rather than unrestricted host
  access.
- Scope or security violations require a stopped run and human review; they
  MUST NOT trigger an automated attempt to bypass the restriction.
