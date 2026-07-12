# Implementation plan: Scope request normalization

## Status

Implemented

## Summary

Introduce a structured scope exception and a shared path validator, preserve
that structure across work-runner exception wrapping, and emit canonical
`data.paths` evidence. Extend scope approval with an explicit request preview
and append operation bound to the current failed scope state. Expose both via
the existing CLI and Makefile, then document safe recovery.

## Existing code investigation

`validation.validate_scope` currently raises plain `ValueError`. `_execute_task`
wraps it in `RuntimeError`, and `work` parses the wrapped string at its first
colon. `scope_approval.preview` only matches `data.path` exactly and has no
supported request-creation interface. Events already provide append-only,
timestamped evidence, and state already records failure class and worktree.

## Affected files

| Area | Change | Risk |
|---|---|---|
| `scripts/agent/validation.py` | Structured scope violation | High |
| `scripts/agent/scope_approval.py` | Safe request creation and canonical matching | High |
| `scripts/agent/work.py` | Preserve paths and expose commands | High |
| `tests/**` | Regression and safety coverage | Medium |
| `Makefile`, docs | Operator interface | Medium |

## Design

`ScopeViolation` carries immutable normalized paths and violation type. A helper
walks exception causes to find it after safety wrapping. Canonical new events
use `data.paths`, while approval reads valid `data.path` for compatibility.
Request creation requires the feature's current failed scope state and appends a
new HUMAN_REQUIRED event; preview returns the intended mutation without writing.
Approval only matches pending requests belonging to the same feature.

## Test strategy

- Unit-test path normalization and structured exception propagation.
- Unit-test legacy/canonical request matching and malformed event rejection.
- Unit-test request preview/apply, duplicates, failed-state binding, and approval.
- Exercise CLI parsing through existing interface tests.
- Run `make spec-lint FEATURE=005-scope-request-normalization` and `make validate`.

## Security considerations

Reject absolute paths, traversal, control characters, repository-wide globs,
unsafe syntax, forbidden paths, mismatched features, and non-scope states.
Never mutate prior events or turn a request into an approval implicitly.

## Rollback strategy

Revert the feature commits. Existing event files remain readable because valid
legacy `data.path` support is retained and the new schema is additive.

## Open questions

- None blocking implementation.
