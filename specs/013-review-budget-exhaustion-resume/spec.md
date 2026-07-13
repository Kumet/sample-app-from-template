# Feature specification: Review budget exhaustion resume

## Status

Implemented

## Purpose

Stop review delivery safely and resumably when the configured total reviewer-call
budget is exhausted, without retrying the exhaustion as a shard failure or
weakening the eight-call limit and exact-identity review gates.

## Requirements

- REQ-001: Review call exhaustion has a dedicated typed failure distinct from a
  reviewer subprocess, timeout, parsing, or finding failure.
- REQ-002: Delivery detects exhaustion before starting another reviewer call.
- REQ-003: Exhaustion appends exactly one bounded, redacted `HUMAN_REQUIRED`
  review event for the blocked shard in the current delivery invocation.
- REQ-004: Exhaustion is not retried through the per-shard attempt loop and does
  not trigger the identical-failure-twice path.
- REQ-005: The current delivery invocation does not replenish or exceed the
  configured total call limit of eight.
- REQ-006: A later explicitly invoked delivery cycle receives a fresh bounded
  budget and may reuse only exact-identity PASS shard events.
- REQ-007: Cached PASS shards do not consume the fresh call budget; pending
  shards continue to require reviewer subprocess PASS.
- REQ-008: Changed HEAD, prompt, evidence, model, settings, or any other identity
  field continues to invalidate reuse.
- REQ-009: Integration review still runs only after all file shards pass.
- REQ-010: Validation, review, input-size, risk, and approval gates are unchanged.

## Acceptance criteria

- [x] AC-001: Calls one through eight run and call nine raises the typed exhaustion
  without starting the reviewer.
- [x] AC-002: One exhaustion produces one `HUMAN_REQUIRED` event and no retry.
- [x] AC-003: A fresh cycle reuses an exact PASS and spends calls only on pending
  identities.
- [x] AC-004: Identity changes cannot reuse the prior PASS.
- [x] AC-005: The configured limit remains eight and all existing gates remain
  fail-closed.
- [x] AC-006: Targeted and full validation and all independent review shards pass.

## Clarifications

- Risk is high because this changes control flow around a required review gate.
- An explicit new `make deliver` invocation is the human-approved resume boundary;
  the exhausted invocation never resets itself.
- Runtime state, events, and completed exact-identity review results remain
  append-only and are not manually edited.
- Sample Feature 001 and its worktree/state/events are out of scope.

## Scope

Allowed: delivery review-budget control, its delivery regression tests, minimal
documentation, and this feature directory.

Forbidden: policy limit changes, review omission, sample repository content,
Feature 001, runtime evidence, worktrees, CI configuration, secrets, credentials,
and production configuration.
