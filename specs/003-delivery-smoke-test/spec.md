# Feature specification: Delivery smoke test

## Status

Approved

## Background

The autonomous delivery framework is covered by local tests and GitHub command
stubs, but it has not yet completed a live, disposable feature through Codex,
an isolated worktree, independent review, branch push, pull request creation,
and GitHub Actions monitoring.

## Goals

- Exercise the real `make deliver FEATURE=003-delivery-smoke-test` workflow.
- Add a short README section recording how to run a delivery smoke test.
- Collect live evidence without enabling automatic merge.
- Identify and fix framework defects exposed by the live run, within the
  approved framework files only.

## Non-goals

- Enabling automatic merge.
- Changing application logic, security policy, or repository settings.
- Installing dependencies or changing the technology stack.
- Testing high-risk delivery behavior against the live repository.

## Users

Maintainers validating this development template before wider autonomous use.

## Requirements

### Functional requirements

- REQ-001: README MUST contain a concise "Delivery smoke test" section with
  the spec-lint, deliver-dry-run, deliver, and cleanup commands.
- REQ-002: The live workflow MUST use an isolated framework-owned Git worktree.
- REQ-003: The live workflow MUST run mechanical validation and independent
  structured review before pushing.
- REQ-004: The live workflow MUST create or update one pull request and monitor
  GitHub Actions to completion.
- REQ-005: Because the feature is medium risk, the framework MUST NOT merge the
  pull request automatically.
- REQ-006: Any framework defect discovered by the live run MAY be fixed only
  inside the allowed scope and MUST receive regression coverage.

### Non-functional requirements

- NFR-001: No credentials or token-like values may appear in committed files,
  prompts, or durable execution logs.
- NFR-002: Retries must remain within repository and feature limits.
- NFR-003: Existing version 1 and version 2 tests must remain green.

## Acceptance criteria

- [ ] AC-001: README documents the four smoke-test commands in execution order.
- [ ] AC-002: Delivery evidence identifies an isolated worktree and successful
  task validation.
- [ ] AC-003: Independent review returns a valid passing structured result.
- [ ] AC-004: Exactly one live pull request exists for the delivery branch and
  its required GitHub Actions checks pass.
- [ ] AC-005: The pull request remains unmerged when `make deliver` finishes.
- [ ] AC-006: `make validate` passes after the smoke-test implementation and any
  in-scope framework repairs.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| What risk level is used? | Medium. | 2026-07-12 |
| Is automatic merge enabled? | No. | 2026-07-12 |
| What is the implementation change? | Add one concise README section with smoke-test commands. | 2026-07-12 |
| May live-run framework defects be fixed? | Yes, only within the approved framework/test/docs scope and with regression tests. | 2026-07-12 |
| Who merges the resulting PR? | A human or a separate explicitly authorized operation after evidence review. | 2026-07-12 |

## Scope

### Allowed changes

- `README.md`
- `prompts/**`
- `scripts/agent/**`
- `tests/**`
- `specs/003-delivery-smoke-test/**`
- `docs/ai-operation.md`
- `docs/architecture.md`

### Forbidden changes

- `.agent-policy.toml`
- `.github/**`
- Authentication, authorization, billing, deployment, migration, or production
  configuration.
- GitHub repository settings, secrets, or branch protection.

## Security and privacy

- GitHub authentication remains outside Codex.
- `.env`, credentials, tokens, keys, and production configuration are not read.
- Logs are inspected by filename and redaction behavior, never by opening
  forbidden secret files.
- Any scope, secret, or high-risk finding stops the workflow.
