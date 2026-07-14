# Validation log: Approved recovery patch re-attribution

## Approved scope

- Human approval received for Feature 014 specification, implementation,
  regression tests, validation, independent review, push, PR, CI, and main
  merge in the template repository.
- The sample repository and Feature 002 worktree/state/events are excluded.

## Runs

- 2026-07-14 — Feature 014 spec-lint passed with no errors or warnings.
- 2026-07-14 — Python compilation passed for all framework modules.
- 2026-07-14 — Targeted recovery-patch suite passed: 7 tests.
- 2026-07-14 — Full framework test suite passed: 122 tests.
- 2026-07-14 — `make validate` passed: quality policy, secret filename check,
  lint/typecheck adapters, and all framework tests.
- 2026-07-14 — Scope audit passed for 9 approved paths; `git diff --check`
  passed.
- Dry-run fingerprints prove unchanged HEAD, branch, status, state, events,
  ownership marker, and Git index.
- Apply records approval and application events, re-attributed state, canonical
  HEAD/index/worktree digest, complete paths, contract, branch, and ownership.
- Missing or tampered evidence, post-approval content/index mutation, HEAD or
  contract change, scope violation, unapproved paths, and invalid ownership all
  fail closed.
- The sample repository and Feature 002 worktree/state/events were not accessed
  or changed.

## Review remediation loops

- None.
