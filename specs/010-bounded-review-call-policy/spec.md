# Feature specification: Bounded review call policy

## Status

Implemented

## Purpose

Complete the repository-policy contract for the independent-review call budget.
The configured finite value must be parsed into the typed policy and enforced
before each reviewer subprocess call.

## Requirements

- REQ-001: `RepositoryPolicy` exposes typed integer `max_review_calls`.
- REQ-002: `load_policy()` requires `max_review_calls` in policy version 1.
- REQ-003: Only non-boolean integers from 1 through 100 are accepted.
- REQ-004: Missing, boolean, string, zero, negative, and values above 100 fail closed.
- REQ-005: The configured template value remains 8.
- REQ-006: The review-call budget is independent from per-shard
  `max_review_attempts` and the task-oriented `max_codex_calls` budget.
- REQ-007: Delivery permits calls while usage is below the configured limit and
  raises before starting a call once the limit is exhausted.
- REQ-008: Review, validation, exact-HEAD, and approval gates are not weakened.

## Acceptance criteria

- [x] AC-001: Loading the repository policy returns `max_review_calls == 8`.
- [x] AC-002: Every invalid or missing form is rejected by the policy loader.
- [x] AC-003: A bounded budget test permits calls 1 through 8 and rejects call 9.
- [x] AC-004: Changing other budgets does not change the parsed review-call limit.
- [x] AC-005: Targeted and full validation pass with all gates intact.

## Clarifications

- Risk is high because review-call accounting protects a required delivery gate.
- There is no implicit default for a missing repository configuration value.
- `max_review_calls` is a total delivery review subprocess-call ceiling, not a
  replacement for per-shard retry limits.
- Sample Feature 001 and its runtime evidence are out of scope.

## Scope

Allowed: `scripts/agent/policy.py`, `scripts/agent/delivery.py` only as needed,
policy and delivery regression tests, `README.md`, `docs/**`, and this feature
directory.

Forbidden: sample repository content, Feature 001 files, runtime evidence,
worktrees, CI configuration, secrets, credentials, and production configuration.
