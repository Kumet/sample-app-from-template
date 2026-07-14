# Validation log: Weakening evidence semantics

## Approved scope

- Human approval covers Feature 015 specification, implementation, regression
  tests, full validation, independent review, push, PR, CI, and main merge in
  the template repository.
- The sample repository and Feature 002 worktree/state/events are excluded.

## Clarification

- Blocking findings remain high-confidence mechanical stops.
- Assertion-removal candidates remain visible to tests review but require
  corroboration from the current exact-HEAD diff.
- Review calls remain bounded at eight and no shard or gate may be weakened.

## Runs

- 2026-07-14 — Feature 015 spec-lint passed with no errors or warnings.
- 2026-07-14 — Python compilation passed for weakening, delivery, review, and
  the Feature 015 regression module.
- 2026-07-14 — Targeted weakening/review/gate suite passed: 14 tests.
- 2026-07-14 — Full framework test suite passed: 139 tests.
- 2026-07-14 — `make validate` passed: quality policy, secret filename check,
  lint/typecheck adapters, and all framework tests.
- 2026-07-14 — Scope audit and `git diff --check` passed for the approved
  implementation, tests, documentation, prompt, and Feature 015 artifacts.
- Review call policy remains `max_review_calls = 8`; the prompt version changed
  from 3 to 4, invalidating old review identities without changing the identity
  schema.
- Identical canonical weakening PASS evidence for one exact HEAD is reused
  rather than appended again, keeping resumable review identity stable.

## Validation loops

- Loop 1 — an optional `make format-check` probe failed because the generic
  template intentionally has no such target. No code or gate was changed in
  response; the repository-defined `make validate` command was used and passed.
- Loop 2 — bumping the identity schema exposed five legacy fixtures that
  intentionally construct schema version 4 identities. The schema bump was not
  required because prompt version is already identity-bound; identity schema 4
  was retained and prompt version 4 provides correct cache invalidation. The
  full suite then passed.
- Loop 3 — the first delivery weakening gate correctly stopped because detector
  regression fixtures placed literal skip and CI-weakening patterns in newly
  added test-source diff lines. The test constructs those same input patches by
  concatenating literals, preserving high-confidence production detection while
  preventing the fixture source itself from masquerading as a real weakening.
- Loop 4 — clean worktree cleanup retained the framework-created agent branch,
  so a fresh delivery could not recreate the fixed branch name. The old branch
  was renamed to an archive namespace instead of force-deleted, preserving its
  failed-cycle evidence commit before a fresh isolated delivery.
