# Validation log: Review budget exhaustion resume
<!-- validation-snapshot: {"event_schema_version":1,"feature":"013-review-budget-exhaustion-resume","generated_at":"2026-07-13T00:00:00+09:00","included_event_sequence":0,"snapshot_format_version":2,"validation_contract_digest":"92a539c48debb8c7bbdbb370b8024e6febccc60a0650aee05bf5a1436e8bc8be"} -->

## Approved scope

- Human approval received for typed, non-retryable review-budget exhaustion and
  exact-identity resume behavior while retaining `max_review_calls = 8`.
- Sample repository, Feature 001, runtime events, and worktrees remain unchanged.

## Runs

- 2026-07-13 — Feature 013 spec-lint passed with no errors or warnings.
- 2026-07-13 — `delivery.py` Python compilation passed.
- 2026-07-13 — Targeted autonomous-delivery suite passed: 23 tests.
- 2026-07-13 — `make validate` passed: 115 framework tests.
- 2026-07-13 — `git diff --check` passed.
- Calls one through eight execute; call nine raises typed
  `ReviewBudgetExhausted` before reviewer invocation.
- Capacity exhaustion records one bounded `HUMAN_REQUIRED` event and raises
  `ReviewResumeRequired` outside the per-shard retry handler.
- A fresh budget reuses an exact-identity PASS without spending a call, does not
  reuse a changed identity, and spends one call on the pending reviewer.
- `.agent-policy.toml` remains `max_review_calls = 8`; review, integration,
  validation, input-size, risk, and approval gates were not weakened.
- Sample repository, Feature 001, runtime state/events, and worktrees were not
  changed.

## Review remediation loops

- Loop 1 — tests shard returned FAIL without required blockers because helper-only
  coverage did not execute the production retry loop and digest-only reuse did not
  demonstrate identity-field invalidation. Extracted the existing production
  attempt loop into a directly exercised function; the regression now proves the
  reviewer is not called, only one failure exists, and the twice-failure guard is
  not reached. Head, prompt version, runtime evidence, model, and settings changes
  each invalidate an otherwise exact reusable PASS.
- Loop 2 — tests shard required the production stop regression to use the actual
  8→9 boundary and reuse invalidation to cover every canonical identity field.
  The retry-path test now consumes all eight calls before the blocked ninth call;
  the fresh-cycle test mechanically mutates every identity field, while rejecting
  an unknown identity schema version fail-closed.
- Loop 3 — tests shard returned FAIL without required blockers because cache reuse
  and pending execution were still tested as separate primitives. Extracted the
  production cache-or-run decision into one shared function. The regression now
  drives that path: exact identity records reuse with zero calls, while every
  canonical identity mutation invokes the pending reviewer exactly once and
  consumes one fresh-budget call.
- Loop 4 — tests shard required explicit audit-side-effect assertions and an
  unknown-schema cache case through the production decision point. Exact reuse
  now proves one `review-reused` event binds the source sequence while the count
  of `review-shard/PASS` events remains one. A legacy unknown-schema PASS digest
  cannot satisfy the current prepared identity and causes one reviewer call.
- Loop 5 — tests shard required calls 1–8 to traverse the production attempt path,
  not pre-consume the budget primitive. The same fresh budget now runs eight
  distinct pending prepared reviews through `run_prepared_review_with_retries`,
  each once, then sends the ninth prepared review through that function and proves
  it records one stop without starting or retrying a ninth subprocess.

## Sample repository synchronization

- 2026-07-13 — Selectively synchronized Feature 013 from template merge commit
  `67fad7f5afe87a63db6ea1f1b7c69e6a26659a26` (Feature HEAD
  `5ceb1156a60b3d03e1afe0d8bdd6e48d20cc691a`) onto sample main
  `9eed2c6ae2bdc4c825f335b71945d1c7d23491e6`; no conflicts occurred.
- Adopted the template delivery implementation, delivery regressions, and five
  Feature 013 artifacts. The README was integrated as a seven-line focused
  paragraph so the sample application documentation remained intact.
- Scope audit passed: no application source, app/integration test, policy value,
  CI, package configuration, Feature 001 specification, runtime state/event, or
  worktree path was changed.
- Feature 013 and 012 specification lint passed. Feature 001 is absent from
  sample main and is linted after the synchronization is merged into its feature
  branch.
- Python compilation passed and the targeted autonomous-delivery suite passed:
  23 tests.
- `make validate` passed with 115 framework tests, 4 bootstrap app tests, and 2
  bootstrap integration tests; secret check, Ruff, mypy, and build passed.
- `.agent-policy.toml` remained unchanged with `max_review_calls = 8`.
- Feature 001 branch, saved worktree, state, and append-only events through
  sequence 73 remained unchanged during synchronization validation.
