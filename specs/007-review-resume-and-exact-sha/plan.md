# Implementation plan: Review resume and exact-SHA validation

## Status

Implemented

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
Descendant PIDs are retained while the reviewer runs so processes that later
leave the group can also be terminated. Runtime evidence has its own canonical
identity digest rather than relying only on the complete prompt digest.
The portable guarantee is limited to the framework-created process group and
observed descendants whose PID start identity still matches. Known survivors
fail closed; kernel containment and unknown pre-observation escapes are not
claimed and remain a future optional-adapter concern.

Tracked evidence is finalized and committed first. The resulting HEAD is
validated without tracked writes, producing a runtime PASS event. Review then
requires that event. Subsequent tracked changes fail the SHA gates.
Snapshot commit and post-evidence validation use separate helpers so interrupted
runs have an explicit recovery boundary.
Every final command run appends an attempt event. A separate accepted PASS is
emitted only after HEAD, snapshot, blob, contract, digest, and cleanliness checks;
failed attribution appends a rejected event and never opens a gate.

The tracked log is rendered as snapshot format version 2 with an included-event
watermark and contract digest. After its commit, Git object identity is captured
by a `tracked-evidence-snapshot` event. A separate post-evidence
`final-validation` event references that snapshot. Review prerequisites validate
both events against the current repository before constructing identities.

Review identity uses one validated canonical field schema rather than a loose
payload. Every artifact and evidence field has an independent digest component.
Timeout subprocess errors pass through `safe_error_detail` before persistence.
Non-timeout failures persist only allowlisted structured metadata (exception
class, shard, identity, attempt, and stable signature), never arbitrary exception
or reviewer text.

## Test strategy

- Unit: identity invalidation, cache eligibility, budgets, duplicate failures.
- Process integration: controlled local parent/child timeout with TERM/KILL.
- Delivery integration: evidence commit, exact validation, review ordering, SHA gates.
- Parameterized identity mutation and malformed-payload rejection tests.
- Fake-secret exception tests across event and diagnostic persistence.
- Regression: complete `make validate`.

## Security considerations

Diagnostics redact output and expose only a safe executable basename and hashed
input identity. No environment or secret-bearing command arguments are logged.

## Rollback strategy

Revert the framework PR; Feature 001 evidence remains untouched and inspectable.

## Open questions

- None within the approved scope.
