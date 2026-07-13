# Validation log: Empty review shard input

## Approved scope

- Human approval received for explicit empty review path handling and regressions.
- Sample Feature 001 worktree, state, and sequences 18 through 27 remain read-only.

## Runs

- Loop 1 treats only an explicitly empty `review_paths` tuple as an empty code
  diff and avoids the ambiguous empty Git pathspec invocation.
- The empty focused selection still produces one prepared shard containing spec,
  plan, tasks, validation contract/log, runtime evidence, prompt, and schema.
- Empty identity contains no changed code path and retains all fixed artifact paths.
- Reviewer execution returns the reviewer result and consumes one
  `ReviewCallBudget` call; no skip or auto-pass path was added.
- Explicit `("src/a.py",)` includes only that diff, while `None` retains the
  complete non-feature-artifact diff behavior.
- Oversized fixed input still fails before reviewer execution.
- Existing integration ordering and exact-identity gate regressions remain active.
- `python3.11 -m py_compile scripts/agent/review.py`: PASS.
- Targeted core, delivery, and production-ready tests: PASS (70 tests).
- `make spec-lint FEATURE=011-empty-review-shard-input`: PASS.
- `make validate`: PASS (112 framework tests, quality check, secret filename
  check, Python version check, and template build targets).
- Review, validation, exact-HEAD, input-size, and approval gates were not weakened.
- The sample repository and Feature 001 sequences 18 through 27 were not changed.
- Review loop 1: spec-scope, security, and maintainability passed. Tests returned
  a non-required finding that prompt inspection alone did not prove the ambiguous
  Git content-diff command was avoided. Loop 2 spies on real subprocess calls and
  asserts zero `git diff --no-ext-diff` invocations for the explicit empty
  `prepare_review()` selection while retaining required changed-file discovery.
- The repeated test-strength finding triggered the bounded stop rule. Human
  approval opened a new cycle limited to that finding. The strengthened assertion
  captures every `git diff` argv, requires exactly one `--name-only` discovery
  command, and rejects trailing `--`, `--no-ext-diff`, or any second diff command;
  the rendered code diff must also remain empty.

## Sample synchronization

- Source merge commit:
  `09e466aa376d9155f0dc3f32ee9bc10d52346468` from template `main`.
- Selectively ported only the approved seven Feature 011 paths because the
  template and sample repositories do not share Git ancestry.
- Conflict result: none. Scope inspection found no application, Feature 001,
  Feature 006 through 010, CI, Makefile, package, policy, or runtime-evidence
  changes.
- Feature 010 and Feature 011 specification lint: PASS. Feature 001 lint remains
  deferred to its feature branch under the existing human-approved
  branch-boundary rule.
- `python3.11 -m py_compile scripts/agent/review.py`: PASS.
- Targeted core, delivery, and production-ready tests: PASS (70 tests).
- `make validate`: PASS with 112 framework tests, 4 application tests, and 2
  integration tests; secret check, Ruff, mypy, Python version check, and package
  build also passed.
- Feature 001 worktree remained at
  `6efb06511d40efc52f636c1a1cbf622c3569b803`; event sequences 18 through 27
  were not changed during framework synchronization validation.
