# Validation log: Owned marker clean validation

## Approved scope

- Human approval received for the final-evidence ownership-marker consistency fix.
- The sample repository and Feature 001 worktree, state, and events remain read-only.

## Runs

- Loop 1 implemented read-only evidence cleanliness through the shared Git status
  parser and the existing bounded/no-follow registered-worktree ownership check.
- A registered isolated worktree whose marker is missing or cannot be verified is
  explicitly dirty even when Git reports no changed path.
- Positive regression: a valid marker permits final-validation acceptance and
  final-evidence lookup without changing marker bytes or linked-worktree index
  bytes/modification time.
- Fail-closed regressions cover root marker, missing marker, feature mismatch,
  symlink, hardlink, oversized content, invalid UTF-8, unrelated untracked files,
  and tracked modifications.
- `python3.11 -m py_compile` for evidence, Git, and worktree helpers: PASS.
- Targeted evidence, safety, and delivery tests: PASS (49 tests).
- `make spec-lint FEATURE=009-owned-marker-clean-validation`: PASS.
- `make validate`: PASS (108 framework tests, quality check, secret filename
  check, Python version check, and template build targets).
- No tests, exact-HEAD gates, review gates, or approval gates were weakened.
- The sample repository and Feature 001 worktree/state/events were not changed.
- Review loop 1: spec-scope, security, and maintainability passed. Tests required
  a direct acceptance-time regression for a valid marker plus an unrelated
  untracked file. Loop 2 adds that exact public-gate assertion without changing
  implementation behavior or weakening any check.
- Review loop 2: spec-scope, security, and maintainability passed. Tests required
  explicit final-evidence lookup rejection after marker corruption, a directory
  absent from the source repository's Git worktree registry, and an injected
  marker-read permission failure. Loop 3 adds these fail-closed regressions using
  public evidence gates and the shared ownership helper.

## Sample synchronization

- Source merge commit:
  `eba5fd4f830ceac3ba00fec1a6600393ea4aeb75` from template `main`.
- Selectively ported only the approved nine Feature 009 paths because the
  template and sample repositories do not share Git ancestry.
- Conflict result: none. Scope inspection found no application, Feature 001,
  Feature 006/007/008, CI, Makefile, package, or runtime-evidence changes.
- Feature 008 and Feature 009 specification lint: PASS. Feature 001 lint remains
  deferred to its feature branch because its unmerged specification is absent
  from sample `main`, under the existing human-approved branch-boundary rule.
- `python3.11 -m py_compile` passed for evidence snapshot, Git, and worktree
  helpers.
- Targeted evidence, safety, and delivery tests: PASS (49 tests).
- `make validate`: PASS with 108 framework tests, 4 application tests, and 2
  integration tests; secret check, Ruff, mypy, Python version check, and package
  build also passed.
- Feature 001 worktree remained at
  `132b67c54bb207d48de7c02cedb2bbb7e40ac6e2`; its state and event sequences
  15 through 17 were not changed during framework synchronization validation.
