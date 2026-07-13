# Feature specification: Owned marker clean validation

## Status

Implemented

## Purpose

Make exact-HEAD final-validation acceptance use the same verified ownership
decision as delivery safe-start. A framework-created marker in its registered
isolated worktree must not make an otherwise clean worktree dirty, while every
unverified marker and every unrelated change remains fail-closed.

## Requirements

- REQ-001: Final-validation acceptance and final-evidence lookup ignore the
  ownership marker only when the current path is a registered isolated worktree.
- REQ-002: The marker content must match the current feature identifier.
- REQ-003: Ownership verification reuses the bounded, no-follow, private regular
  file check shared by safe-start and delivery inspection.
- REQ-004: A marker at the repository root is dirty.
- REQ-005: A marker in an unregistered directory is dirty.
- REQ-006: Missing, mismatched, oversized, invalid, symlinked, hardlinked, or
  unreadable markers are dirty and fail closed.
- REQ-007: Any tracked change or any untracked path other than the single verified
  marker remains dirty.
- REQ-008: Clean inspection is read-only and does not refresh the Git index.
- REQ-009: Existing exact-HEAD, snapshot, digest, review, and approval gates remain
  unchanged and are not weakened.

## Acceptance criteria

- [x] AC-001: An otherwise clean registered worktree with its valid marker can
  record `final-validation-accepted/PASS` and load final evidence.
- [x] AC-002: Root, unregistered, mismatched, symlinked, hardlinked, and malformed
  markers are rejected.
- [x] AC-003: A valid marker plus another tracked or untracked change is rejected.
- [x] AC-004: Safe-start and final evidence use the same ownership helper and the
  shared Git status parser.
- [x] AC-005: Targeted and full framework validation pass without weakening tests.

## Clarifications

- Risk is high because final-validation acceptance is an approval-integrity gate.
- The marker is runtime ownership metadata and is never committed.
- A filename match alone never authorizes exclusion; registration and bounded
  marker verification are mandatory.
- The sample repository and Feature 001 runtime evidence are out of scope.

## Scope

Allowed: `scripts/agent/evidence_snapshot.py`, the necessary shared ownership or
safe-start helper under `scripts/agent/`,
`tests/test_delivery_evidence_snapshot.py`, necessary framework regression tests,
`README.md`, `docs/**`, and this feature directory.

Forbidden: `.github/**`, application `src/**`, Feature 001 files, runtime state or
events, worktree contents, secrets, credentials, and production configuration.
