# Feature specification: Empty review shard input

## Status

Implemented

## Purpose

Preserve an explicitly empty focused-review path selection as an empty code diff
instead of accidentally expanding it to the entire feature diff. The shard must
still execute against its fixed specification and evidence inputs.

## Requirements

- REQ-001: `prepare_review(..., review_paths=())` produces an empty `diff_text`.
- REQ-002: Explicit empty paths never execute `git diff BASE HEAD --` with an
  empty pathspec and never expand to the feature diff.
- REQ-003: The shard is still prepared and executed; it is not skipped or auto-passed.
- REQ-004: Spec, plan, tasks, validation contract, validation log, runtime
  evidence, prompt, and schema inputs remain present and identity-bound.
- REQ-005: No changed code path is added to `reviewed_files` for an empty selection.
- REQ-006: Fixed artifact, prompt, and schema paths remain in `reviewed_files`.
- REQ-007: Empty-diff reviewer execution consumes one normal review call.
- REQ-008: A non-empty explicit selection includes only its selected paths.
- REQ-009: `review_paths=None` retains the complete non-feature-artifact diff behavior.
- REQ-010: Input-size limits remain unchanged and oversized fixed input fails closed.
- REQ-011: File shards and integration remain required; integration runs only
  after all file shards pass.
- REQ-012: Existing review cache, identity, validation, and approval gates are
  not weakened.

## Acceptance criteria

- [x] AC-001: Empty focused selection yields one prepared review with an empty
  code diff.
- [x] AC-002: Its prompt and identity retain every fixed artifact and evidence input.
- [x] AC-003: The reviewer is invoked and its PASS/FAIL result remains authoritative.
- [x] AC-004: Explicit non-empty and implicit complete selections retain prior behavior.
- [x] AC-005: Oversized input and ordering violations still fail closed.
- [x] AC-006: Targeted and full validation pass without gate weakening.

## Clarifications

- Risk is high because this changes required independent-review input construction.
- Empty code relevance is valid for a focused shard; it is not evidence that the
  shard passed.
- Sample Feature 001 and runtime sequences 18 through 27 are out of scope.

## Scope

Allowed: `scripts/agent/review.py`, review/delivery regression tests, `README.md`,
`docs/**`, and this feature directory.

Forbidden: sample files, Feature 001, runtime state/events, worktrees, CI config,
secrets, credentials, and production configuration.
