# Implementation plan: Review resume and exact-SHA validation

## Status

Approved

## Summary

Introduce canonical review identities and an event-backed shard coordinator,
replace `subprocess.run` with process-group-aware execution, and finalize tracked
evidence before running an immutable exact-HEAD validation and review sequence.

## Existing code investigation

`delivery.run_review_once` restarts all shards and stores mutable JSON files only.
`review.run_review` has a fixed timeout without process-group cleanup. Final
validation can commit its own log after validation, while delivery does not
require a matching validation event before review.

## Affected files

| File | Change | Risk |
|---|---|---|
| `scripts/agent/review.py` | Identity, process-group runner, diagnostics | High |
| `scripts/agent/review_shards.py` | Event-backed resume coordinator | High |
| `scripts/agent/delivery.py` | exact-SHA sequencing and gate enforcement | High |
| `scripts/agent/events.py`, `gates.py`, `work.py` | evidence helpers and finalization | High |
| `tests/**` | failure, retry, process, and SHA regression coverage | Low |
| docs/specs | operator contract | Low |

## Design

Canonical JSON hashed with SHA-256 forms the review identity. PASS events embed
identity and result data; reuse requires a complete match and emits a new
`review-reused` decision referencing the source sequence. File shards run first;
integration is evaluated only after them. Timeout execution starts a new process
session, terminates its group with TERM/KILL, and returns structured diagnostics.

Tracked evidence is finalized and committed first. The resulting HEAD is
validated without tracked writes, producing a runtime PASS event. Review then
requires that event. Subsequent tracked changes fail the SHA gates.

## Test strategy

- Unit: identity invalidation, cache eligibility, budgets, duplicate failures.
- Process integration: controlled local parent/child timeout with TERM/KILL.
- Delivery integration: evidence commit, exact validation, review ordering, SHA gates.
- Regression: complete `make validate`.

## Security considerations

Diagnostics redact output and expose only a safe executable basename and hashed
input identity. No environment or secret-bearing command arguments are logged.

## Rollback strategy

Revert the framework PR; Feature 001 evidence remains untouched and inspectable.

## Open questions

- None within the approved scope.
