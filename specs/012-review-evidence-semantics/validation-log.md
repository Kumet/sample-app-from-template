# Validation log: Review evidence semantics
<!-- validation-snapshot: {"event_schema_version":1,"feature":"012-review-evidence-semantics","generated_at":"2026-07-13T00:00:00+09:00","included_event_sequence":0,"snapshot_format_version":2,"validation_contract_digest":"3f94399a4e3ff9b5ca100629e2361899d91a9b2dce706bff43e107a252345242"} -->

## Approved scope

- Human approval received for structured reviewer evidence interpretation without
  changing persistence or gate authority.
- Sample Feature 001 worktree, state, and sequences 18 through 43 remain read-only.

## Runs

- 2026-07-13 — Specification lint passed before implementation.
- 2026-07-13 — Python compilation passed for `review.py` and
  `evidence_snapshot.py`.
- 2026-07-13 — Targeted review/evidence/production regression suite passed:
  65 tests.
- 2026-07-13 — `git diff --check` passed.
- 2026-07-13 — `make spec-lint FEATURE=012-review-evidence-semantics`
  passed with no errors or warnings.
- 2026-07-13 — `make validate` passed with 113 framework tests.
- Unit-test fixture: the synthetic watermark 40, snapshot 41, attempt 42,
  accepted 43 lifecycle is mechanically verified without treating post-evidence
  events as stale. These fixture sequence numbers are not this branch's runtime
  evidence and do not supersede the metadata watermark on line 2.
- Watermark, validation-log blob, exact HEAD, snapshot/attempt references,
  result digest, and contract digest mismatches fail closed.
- Prompt version is 3; otherwise identical version-2 review identities do not
  match.
- Review subprocess execution, reviewer PASS, eight-call budget, file-shard
  ordering, integration ordering, and the 100,000-character limit are unchanged.
- No sample repository, Feature 001 worktree/state/events, or runtime sequence
  18 through 43 was changed.

## Review remediation loops

- Loop 1 — tests shard returned FAIL with no required blocker because the
  Feature 012 diff did not directly demonstrate that ordinary, legacy,
  attempt-only, and rejected events cannot open the final-evidence gate. Added
  an explicit table-driven gate regression without changing gate behavior.
- Loop 2 — security shard found that duplicate runtime event sequences could be
  collapsed by a sequence-keyed lookup. Lifecycle evidence now rejects missing,
  non-integer, boolean, non-positive, and duplicate sequences before lookup; a
  forged duplicate regression was added.
- Loop 3 — spec-scope found that the 40→43 unit-test fixture was not explicitly
  distinguished from this branch's runtime evidence. The run entry now labels it
  as synthetic fixture data and points to the authoritative line-2 watermark.
- Loop 4 — tests shard correctly required a positive control alongside the four
  non-authoritative gate cases. The same regression now records a correctly
  bound accepted/PASS event and proves that it opens final evidence authority.
- Loop 5 — tests shard found two final coverage gaps: accepted-event exact HEAD
  mismatch was not mutated directly, and four non-authoritative kinds shared an
  accumulating event store. Added the accepted HEAD mutation and isolated every
  negative kind in its own event store so no earlier rejection can mask it.

## Approved follow-up cycles

- Test-construction cycle — copied the authoritative tracked snapshot into each
  isolated negative event store; the two focused regressions, 65 related tests,
  and all 113 framework tests passed before the missing-lifecycle implementation.
- Missing-lifecycle cycle — security review found that `status: no-lifecycle`
  allowed review preparation without gate-defining evidence. Removed that path,
  made absent and partial lifecycles fail closed, and converted review fixtures
  to complete snapshot/attempt/accepted evidence. Targeted and full validation
  passed before this tracked pre-final snapshot. The post-snapshot accepted event,
  rather than this tracked log, binds those results to the review's exact HEAD;
  writing that runtime event back here would recreate the prohibited commit loop.
- Follow-up review loop 2 — tests review required an explicitly named legacy
  negative event and field-specific mismatch assertions. Added an independent
  legacy event store case and exact expected mismatch labels for all nine
  watermark/blob/HEAD/reference/digest mutations.
- Follow-up review loop 3 — tests review required direct attempt-stage mismatch
  coverage and an accepted/FAIL negative control. Added attempt blob, contract,
  and result-digest mutations plus a fully linked accepted event whose FAIL result
  remains non-authoritative.

## Sample repository synchronization

- 2026-07-13 — Selectively synchronized the ten approved Feature 012 paths from
  template merge commit `e936b2003ff2199f2366aa98425ede3a4eb45972`
  (Feature HEAD `bda8d05caaefc97ecf45782e05f083b79e926f66`) onto sample
  main `b09d147dfcc344456c8071a6a152ae4380a0877d`; no conflicts occurred.
- Scope audit passed: no application source, app/integration test, CI, Makefile,
  package configuration, Feature 001 specification, runtime state/event, or
  worktree path was changed.
- Feature 012, 011, and 010 specification lint passed. Feature 001 is not present
  on sample main and is therefore linted only after the framework synchronization
  is merged into its feature branch.
- Python compilation passed for `review.py` and `evidence_snapshot.py`.
- The targeted review/evidence/production regression suite passed: 65 tests.
- `make validate` passed with 113 framework tests, 4 sample app tests, and 2
  sample integration tests; secret check, Ruff, mypy, and build passed.
- Feature 001 branch, saved worktree, state, and append-only events through
  sequence 50 remained unchanged during synchronization validation.
