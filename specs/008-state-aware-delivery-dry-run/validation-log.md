# Validation log: State-aware delivery dry-run

## Investigation

- Existing delivery dry-run used a fixed mutation list and did not inspect the
  existing worktree or state.
- The repository root had no `.agent-worktree-owned` file during inspection.
- The Feature 001 worktree marker contains `001-project-crud`, is untracked, and
  was created and last modified at 2026-07-12 16:24:28 +0900.
- The only marker writer found was `worktree.create`; no evidence shows dry-run
  created a root marker.

## Runs

- `make spec-lint FEATURE=008-state-aware-delivery-dry-run`: PASS.
- Targeted delivery tests: PASS (11 tests in temporary repositories; no Feature
  001 worktree or runtime mutation).
- `make validate`: PASS (88 framework tests, 4 application tests, 2 integration
  tests, secret check, Ruff, mypy, and build).
- Root marker remained absent before and after testing.
- Feature 001 worktree remained at
  `80da5e559a6652dc69453121800aedaa2463d956` with only its existing untracked
  ownership marker.
- Framework review loop 1 found that an ordinary directory could mimic an
  existing worktree and an unreadable marker could escape structured reporting.
  Loop 2 now requires registered linked-worktree identity and converts marker
  decoding/read failures into fail-closed blockers; 12 targeted tests pass.
- Framework review loop 2 found misleading create output for an existing blocked
  path and an unguarded contract-digest read. Loop 3 initializes existing paths
  as blocked and guards digest computation so malformed contracts remain
  structured fail-closed results.
- Framework review loop 3 found a stale Git worktree registration whose directory
  was missing. Loop 4 checks registration before the missing-path create decision
  and reports the stale registration as a blocker.
- Framework review loop 4 identified Git's optional index refresh during status.
  Loop 5 runs inspection status with `GIT_OPTIONAL_LOCKS=0` and verifies linked
  worktree index bytes and modification time remain unchanged.
- The prior cycle stopped at its five-loop limit on HEAD `ff4cf3c`. Human approval
  opened a new cycle limited to shared root safe-start inspection and structured
  normalized worktree path matching, including `scripts/agent/git_utils.py` scope.
- New cycle loop 1 preserved the existing runtime-directory exclusions in the
  shared porcelain parser, then passed 28 targeted safe-start/delivery tests.
- `make spec-lint FEATURE=008-state-aware-delivery-dry-run`: PASS after the new
  cycle implementation.
- `make validate`: PASS (96 framework tests, 4 application tests, 2 integration
  tests, secret check, Ruff, mypy, and build).
- New cycle review loop 1: spec-scope PASS; security found symlink-alias marker
  acceptance and runtime-directory dirty filtering. Loop 2 rejects expected-path
  symlinks and applies no runtime exclusions to root safe-start inspection.
- After loop 2, `make validate` passed with 97 framework tests, 4 application
  tests, 2 integration tests, static checks, secret check, and build.
- New cycle review loop 2: spec-scope PASS; security found marker symlink
  following during creation and inspection. Loop 3 uses exclusive no-follow
  creation and reads only regular non-symlink marker files.
- New cycle review loop 3: spec-scope PASS; security returned FAIL without
  required findings for container symlinks and marker hardlinks/races. Loop 4
  confines the container and reads a bounded, single-link marker via one no-follow
  file descriptor.

## Template port

- Source range: `3c0dec5^..5d09cf9`; source final HEAD
  `5d09cf9ba05f709236c8dffd69f9a4dfbd8e7093`.
- Template base: `4b782cbe1f85d5c944f2b889990ee78fcc9f67b4`.
- All 18 commits were ported in order without conflicts. Scope inspection found
  only the approved framework, tests, documentation, and Feature 008 artifacts;
  no application, CI, secret, runtime evidence, or Feature 001 files changed.
- `make spec-lint` passed for Features 006, 007, and 008.
- `python3.11 -m py_compile` passed for delivery, worktree, work, and Git helpers.
- The 30 targeted safety/delivery tests passed in temporary repositories.
- `make validate` passed with 98 template framework tests and the secret check.
- The frozen sample Feature 001 and its worktree were read-only and unchanged.
- Template review loop 1 exposed that a newly created registered worktree's own
  valid `.agent-worktree-owned` marker was rejected by safe-start before work
  began. Safe-start now ignores that marker only when the caller proves the
  worktree is registered and the bounded marker identifies the same feature;
  root and unverified markers remain blocking. The 31 targeted tests and all 99
  framework tests passed after this correction.
- Human-approved review remediation loop 1 expanded scope only to
  `scripts/agent/review.py`, made spec/scope review receive the complete feature
  diff, and normalized displayed expected/current/saved worktree paths. The
  first targeted run exposed one obsolete raw-path assertion; after updating it
  to the canonical resolved path, 41 targeted tests and all 99 framework tests
  passed without weakening coverage.
- Review remediation loop 2 documented intentional read-only spec/scope overlap,
  centralized verified-marker ownership in `worktree.py`, strengthened focused
  shard partition assertions, and proved dry-run preserves existing file bytes,
  HEAD, branch, and all mocked execution/remote boundaries. The 42 targeted
  tests and all 100 framework tests passed.
- Review remediation loop 3 applied the human-approved final policy: high-risk
  remote operations are listed as deferred behind the pre-push gate, and saved
  worktree identity rejects external aliases even when they resolve to the
  managed path. The 42 targeted tests and all 100 framework tests passed.
- Human approval opened a new bounded cycle limited to the two remaining test
  review findings. Loop 1 now exercises public `dry_run()` against a registered
  resumable linked worktree and proves exact preservation of root Git metadata,
  linked-worktree files and Git metadata, state, events, marker, HEAD, and branch.
  It also proves public `dry_run()` and `deliver()` both consume the shared
  `inspect_delivery_worktree()` result and fail closed before worktree creation,
  task execution, validation, review, or GitHub delivery when inspection blocks.
- New-cycle targeted validation: PASS (34 delivery and safety tests, including
  the three focused dry-run/entrypoint tests).
- `make spec-lint FEATURE=008-state-aware-delivery-dry-run`: PASS.
- New-cycle `make validate`: PASS (102 framework tests, quality checks, secret
  filename check, Python version check, and template build targets).

## Sample synchronization attempt

- Source HEAD `b8703aa2625d4faee3a7d963d42138542f71d3b5` was fetched and
  verified as the clean template `main` Feature 008 merge commit.
- The human-approved 14 framework paths were selectively restored onto
  `fix/008-template-state-aware-delivery`; no unrelated-history merge was used.
- Scope inspection found only the approved 14 paths, with no application,
  Feature 001, CI, Makefile, package, or runtime-evidence changes.
- Feature 006, 007, and 008 specification lint passed.
- Feature 001 specification lint stopped safely with `Feature not found`
  because the sample `main` branch does not contain the unmerged
  `specs/001-project-crud/**` artifacts. Those artifacts remain on
  `feature/001-project-crud` and were not copied into this framework sync branch.
- Targeted tests, full validation, commit, push, PR, CI, merge, and Feature 001
  resume were not run after this scope/branch-boundary mismatch.
- Human approval confirmed that Feature 001 specification lint is deferred until
  updated `main` is merged into `feature/001-project-crud`, where its unmerged
  specification artifacts exist; the framework sync branch must not copy them.
- `python3.11 -m py_compile` passed for all five synchronized framework modules.
- Targeted framework validation passed: 58 tests across agent safety,
  autonomous core, and autonomous delivery.
- `make validate` passed with 102 framework tests, 4 application tests, and 2
  integration tests. Ruff formatting/lint, mypy, secret filename inspection,
  Python version verification, and package build also passed.
- Feature 001 remained frozen at
  `80da5e559a6652dc69453121800aedaa2463d956`; its worktree, state, events,
  application code, and specification were not changed or resumed.
