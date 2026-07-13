# Validation log: Bounded review call policy

## Approved scope

- Human approval received for typed, bounded `max_review_calls` policy loading
  and enforcement.
- Sample Feature 001 worktree, state, and event sequences remain read-only.

## Runs

- Loop 1 added typed `RepositoryPolicy.max_review_calls` and requires the version-1
  loader to parse it as a non-boolean integer from 1 through 100.
- The template policy loads the configured value 8 independently from
  `max_review_attempts=1` and `max_codex_calls=99` in the focused fixture.
- Missing, boolean, string, zero, negative, and 101 values fail closed.
- Delivery reserves calls 1 through 8 and rejects call 9 before reviewer execution.
- `python3.11 -m py_compile` for policy and delivery modules: PASS.
- Targeted policy/core/delivery tests: PASS (47 tests).
- `make spec-lint FEATURE=010-bounded-review-call-policy`: PASS.
- `make validate`: PASS (111 framework tests, quality check, secret filename
  check, Python version check, and template build targets).
- Review, validation, exact-HEAD, and approval gates were not weakened.
- The sample repository and Feature 001 worktree/state/events were not changed.
- Review loop 1: security and maintainability passed; spec-scope found an
  unintended removal of the successful shard `return result` adjacent to the
  budget edit. Loop 2 restores the original control flow and retains only the
  approved pre-subprocess budget reservation change.
- Review loop 2: spec-scope, security, and maintainability passed. Tests required
  explicit `false` rejection and proof that exhaustion prevents reviewer process
  execution. Loop 3 uses the delivery-path `ReviewCallBudget.run()` to reserve
  state before invoking its callback and asserts the ninth callback is not called.
- Review loop 3: spec-scope, security, and maintainability passed. Tests required
  positive coverage at both accepted bounds. Loop 4 loads 1, 8, and 100 while
  preserving the independent per-shard and task Codex budget assertions.

## Sample synchronization

- Source merge commit:
  `459cab33dd32f80fa4038fae4e5d35b785ab8b0e` from template `main`.
- Selectively ported only the approved nine Feature 010 paths because the
  template and sample repositories do not share Git ancestry.
- Conflict result: none. Scope inspection found no application, Feature 001,
  Feature 006/007/008/009, CI, Makefile, package, policy-value, or runtime
  evidence changes.
- Feature 009 and Feature 010 specification lint: PASS. Feature 001 lint remains
  deferred to its feature branch under the existing human-approved
  branch-boundary rule.
- `python3.11 -m py_compile` passed for delivery and policy modules.
- Targeted autonomous core and delivery tests: PASS (47 tests).
- `make validate`: PASS with 111 framework tests, 4 application tests, and 2
  integration tests; secret check, Ruff, mypy, Python version check, and package
  build also passed.
- `.agent-policy.toml` remained unchanged with `max_review_calls = 8`,
  `max_review_attempts = 3`, and `max_codex_calls = 20` as independent limits.
- Feature 001 worktree remained at
  `817e8651d966ace281c6a7752099b52184578302`; event sequences 18 through 21
  were not changed during framework synchronization validation.
