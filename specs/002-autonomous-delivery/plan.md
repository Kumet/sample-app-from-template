# Implementation plan: Autonomous Delivery Framework

## Status

Implemented

## Summary

Extend the existing standard-library agent package with small modules for
contract linting, repository policy, atomic state, failure recovery, weakening
detection, structured review, GitHub delivery, worktree isolation, and stack
adapters. Keep orchestration boundaries injectable so all remote and Codex
behavior can be tested with local stubs.

## Existing code investigation

The current framework has feature/task parsing, safe subprocess arrays, Git
scope checks, Codex execution, evidence directories, bounded task loops,
dry-run/status, and 13 tests. Feature validation commands are arbitrary arrays,
state is implicit, final repair is not independently reviewed, GitHub delivery
is absent, and stack setup is manual.

## Affected files

| Area | Change | Risk |
|---|---|---|
| `scripts/agent/` | Add ten capabilities and integrate CLI | High |
| `schemas/`, `adapters/` | Add declarative contracts | Medium |
| `tests/` | Add isolated coverage for all gates | Low |
| `Makefile`, templates | Expose stable interfaces | Medium |
| docs | Explain autonomous policy and operation | Low |

## Design

Repository-wide trusted policy lives in `.agent-policy.toml`; feature-owned
`validation.toml` references allowlisted Make targets and declares risk and
traceability. State is atomically persisted as JSON. Delivery composes existing
work with independent review and a GitHub client; GitHub operations never enter
Codex prompts. Worktrees are created by a dedicated manager and adapters remain
declarative TOML.

## Data model impact

Versioned TOML contracts, JSON Schema review output, adapter TOML files, and
ignored runtime JSON evidence. No application database impact.

## API impact

Add `spec-lint`, `work-resume`, `work-abort`, `deliver`,
`deliver-dry-run`, `detect-stack`, and `init-stack` commands/Make targets.

## UI impact

JSON terminal output and generated PR Markdown only.

## Test strategy

- Unit: every parser, classifier, risk gate, state guard, and adapter.
- Integration: temporary Git repositories/worktrees and executable stubs.
- Remote simulation: injected GitHub command runner; never use a real remote.
- Regression: existing 13 tests remain green.

## Security considerations

Allowlist Make targets, redact evidence, never pass credentials to Codex,
escalate risk monotonically, preserve failed worktrees, and prohibit direct
default-branch pushes and forced/destructive Git operations.

## Rollback strategy

Revert feature commits. New runtime state and worktrees are ignored and are not
removed automatically after failure.

## Open questions

- None blocking implementation.
