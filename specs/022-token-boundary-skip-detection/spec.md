# Feature specification: Token-boundary skip detection

## Status

Approved

## Purpose

Prevent the mechanical weakening gate from interpreting a test-disable token
that appears only as the suffix of another identifier, while preserving
fail-closed detection of actual skip and disable markers.

## Requirements

- REQ-001: `xit` and `xdescribe` call detection MUST require an identifier
  boundary and MUST NOT match a suffix of another identifier.
- REQ-002: Python termination calls including `SystemExit`, `exit`, and
  `sys.exit`, including case variants and identifier-prefixed near misses, MUST
  NOT produce a `test-skip` finding solely because they contain `xit`.
- REQ-003: Actual `xit(...)`, `xdescribe(...)`, `.skip(...)`, Python skip
  decorators, and `pytest.mark.skip` additions MUST remain high-severity,
  required, blocking `test-skip` findings.
- REQ-004: A patch containing only non-skip near misses MUST have no blocking
  findings or review candidates and MUST receive mechanical verdict `PASS`.
- REQ-005: A real skip marker MUST receive mechanical verdict `FAIL` before any
  reviewer subprocess is started.
- REQ-006: The correction MUST be generic token-boundary logic, not a
  `SystemExit` exception, path exclusion, or Feature-specific special case.
- REQ-007: Assertion replacement, test deletion, CI weakening, canonical
  weakening evidence, exact-HEAD ordering, review budgets, and approval gates
  MUST retain their existing behavior.
- REQ-008: Validation MUST cover the approved positive and negative matrix in a
  table-driven form and retain the existing fail-closed regressions.

## Acceptance criteria

- [x] AC-001: `SystemExit`, `exit`, `sys.exit`, and identifier-prefixed `xit`
  and `xdescribe` near misses produce no weakening finding.
- [x] AC-002: Standalone `xit`/`xdescribe`, JavaScript `.skip`, Python skip
  decorators, and `pytest.mark.skip` remain required blocking findings.
- [x] AC-003: Near-miss-only input is `PASS`, while real skip input is `FAIL`
  with category `test-skip`, severity `high`, and `required=true`.
- [x] AC-004: Blocking skip evidence prevents reviewer invocation and existing
  Feature 015/016/017 semantics remain covered.
- [ ] AC-005: Spec lint, targeted tests, full validation, exact-HEAD review, CI,
  and post-merge validation pass without unrelated changes.

## Clarifications

- The approved human prompt is the source of truth; no GitHub Issue is required.
- Matching remains conservative for actual disable markers. The correction is
  limited to preventing substring matches inside a larger identifier.
- Detection is not disabled for `scripts/operations/**` or any other path.
- Existing case-insensitive behavior may be retained provided identifier
  boundaries are correct for every approved near miss.
- The sample repository and Feature 020 runtime artifacts are read-only and out
  of scope until this template Feature has merged.

## Scope

Allowed: weakening token detection, its direct regression tests, this Feature
directory, and minimal repository-neutral documentation.

Forbidden: delivery/review/gate behavior changes, path-specific exclusions,
hard-coded application exceptions, sample changes, runtime evidence rewriting,
budget changes, or weakening any validation or approval gate.

## Definition of done

The generic identifier-boundary defect is fixed, the full approved positive and
negative matrix passes, existing weakening semantics remain intact, and the
reviewed branch is merged through a pull request with successful CI and final
main validation.
