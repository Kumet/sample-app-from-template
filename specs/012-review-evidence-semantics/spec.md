# Feature specification: Review evidence semantics

## Status

Implemented

## Purpose

Give independent reviewers an explicit, identity-bound interpretation of the
tracked pre-final validation snapshot and the append-only post-evidence runtime
events, without changing the exact-HEAD evidence model or its fail-closed gates.

## Requirements

- REQ-001: The review prompt states that validation-log is a tracked snapshot
  only through its included-event watermark.
- REQ-002: Snapshot and later post-evidence events are expected to remain outside
  the tracked log to prevent a self-referential commit loop.
- REQ-003: The prompt identifies the tracked snapshot, accepted attempt, accepted
  event, log blob, exact HEAD, and validation result digest.
- REQ-004: Absence of post-watermark runtime events from validation-log alone is
  not a stale-evidence finding.
- REQ-005: A stale/attribution finding remains valid for actual watermark, blob,
  contract, HEAD, snapshot reference, attempt reference, or result mismatches.
- REQ-006: Only `final-validation-accepted/PASS` bound to a PASS attempt and
  snapshot opens the final-validation gate.
- REQ-007: Rejected, ordinary validation, attempt-only, and legacy events never
  open the gate.
- REQ-008: Post-evidence events are not written back into validation-log.
- REQ-009: The prompt version changes and old review identities are not reusable.
- REQ-010: Review shards still execute and require reviewer PASS.
- REQ-011: The eight-call budget, shard ordering, integration ordering, and input
  limit remain unchanged.

## Acceptance criteria

- [x] AC-001: A watermark-40, snapshot-41, attempt-42, accepted-43 example is
  rendered as mechanically verified, non-stale evidence.
- [x] AC-002: The prompt contains the normative tracked/runtime interpretation.
- [x] AC-003: Every evidence reference mismatch remains fail-closed.
- [x] AC-004: Prompt version changes invalidate otherwise identical identities.
- [x] AC-005: All review and delivery gates remain required and bounded.
- [x] AC-006: Targeted and full validation pass.

## Clarifications

- Risk is high because reviewer evidence interpretation affects delivery approval.
- This feature clarifies the existing Feature 007 model; it does not alter event
  persistence, validation-log rendering, or accepted-evidence authority.
- Sample Feature 001 and sequences 18 through 43 are out of scope.

## Scope

Allowed: the review prompt, review preparation, evidence semantics projection,
review/evidence tests, documentation, and this feature directory.

Forbidden: sample files, Feature 001, runtime state/events, worktrees, CI config,
secrets, credentials, and production configuration.
