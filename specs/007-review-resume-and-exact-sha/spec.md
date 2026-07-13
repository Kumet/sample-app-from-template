# Feature specification: Review resume and exact-SHA validation

## Status

Approved

## Background

Feature 001 review repeatedly restarted all shards, left a timed-out Codex
process insufficiently diagnosed, and could not distinguish a validated code
commit from a later tracked evidence commit. The 600-second ceiling from Feature
006 is retained, but timeout extension alone is not a remedy.

## Goals

- Resume only identity-matched successful review shards.
- Retry failed or missing shards within bounded budgets and fail closed.
- terminate timed-out reviewer process groups and preserve redacted diagnostics.
- Bind validation and all delivery gates to one exact HEAD without creating a
  validation-log self-reference loop.

## Non-goals

- Weakening, skipping, or auto-approving review or validation gates.
- Changing Feature 001 application code, specification, runtime state, or events.
- Increasing the review timeout beyond 600 seconds.

## Requirements

### Functional requirements

- REQ-001: Review identity binds feature, exact HEAD, shard, schema version,
  prompt/reviewer version, command/model settings, reviewed files, and complete
  input digest, plus a distinct digest of the allowlisted runtime evidence.
- REQ-002: A PASS shard is reusable only when its complete identity matches.
- REQ-003: HEAD, diff, specification artifacts, contract, prompt, schema, model,
  or command changes invalidate reuse.
- REQ-004: FAIL, TIMEOUT, CANCELLED, INVALID, missing, and parse-failed results
  are never reusable.
- REQ-005: Resume retries only missing or unsuccessful shards.
- REQ-006: Limited retries obey max review attempts and the review-call budget.
- REQ-007: The same shard and failure signature twice stops safely.
- REQ-008: Every required file shard and integration review must PASS for the
  same HEAD and review contract before the review gate passes.
- REQ-009: Integration review runs only after every required file shard passes.
- REQ-010: Re-executing a file shard invalidates an earlier integration result.
- REQ-011: Cache decisions use append-only runtime events; old events are not
  rewritten.
- REQ-012: A reuse decision appends an event referencing its source sequence.
- REQ-013: Timeout diagnostics record shard, HEAD, attempt, timeout, elapsed,
  safe command identity, prompt size, input digest, redacted output tails,
  process status, PID, and termination result.
- REQ-014: Timeout terminates the framework-started process group and every
  controlled descendant PID observed with a matching process-start identity.
- REQ-015: Termination sends TERM, waits briefly, then sends KILL only if needed.
- REQ-016: Process-group termination outcome is stored in an append-only event.
- REQ-017: Known survivors fail closed; OS-independent termination of unknown
  descendants that escape before observation is not guaranteed.
- REQ-018: 600 seconds remains the maximum; tests may inject shorter timeouts.
- REQ-019: Oversized review input fails closed before reviewer execution.
- REQ-020: Identity material is canonicalized once and shard prompts contain
  only the complete information required for that focus.
- REQ-021: A validation PASS event is bound only to the HEAD actually validated.
- REQ-022: Any later tracked commit invalidates an earlier validation PASS.
- REQ-023: After committing tracked evidence, final validation runs on the new HEAD.
- REQ-024: Final validation changes no tracked files and records its result only
  in append-only runtime evidence.
- REQ-025: validation-log may deterministically render pre-final events and be
  committed before final validation; it is not regenerated afterward.
- REQ-026: PR summary identifies the log cutoff event, final validation event,
  and validated HEAD.
- REQ-027: Review requires a PASS validation event for the current HEAD.
- REQ-028: A tracked change after review invalidates validation and all reviews.
- REQ-029: Validation, weakening, all reviews, integration, PR HEAD, and CI must
  identify one SHA before push/merge gates pass.
- REQ-030: The tracked validation log is a deterministic snapshot with feature,
  event/snapshot schema versions, included sequence watermark, generated time,
  and validation-contract digest; it never embeds its own commit SHA.
- REQ-031: After the snapshot commit, a `tracked-evidence-snapshot` runtime event
  binds the exact HEAD, validation-log Git blob SHA, watermark, contract digest,
  and snapshot format version.
- REQ-032: Every exact-HEAD command run emits `final-validation-attempt`; only a
  subsequent `final-validation-accepted/PASS` may prove final validation.
- REQ-033: Accepted validation references its PASS attempt and snapshot and repeats
  the exact HEAD, log path/blob, contract digest, command identity, timestamps,
  and result digest. Failed or unattributable attempts remain append-only evidence.
- REQ-034: Review prerequisites validate the snapshot/attempt/accepted references,
  current Git blob, contract digest, clean worktree, and unchanged HEAD.
- REQ-035: Review identity has one canonical schema defining every required field,
  including artifact digests and snapshot/final-validation evidence fields.
- REQ-036: Every review subprocess exception crosses one centralized redaction
  boundary before persistence; EventStore redaction remains defense in depth.
- REQ-037: Process diagnostics record root PID, process-group ID, observed PID
  identities, TERM/KILL targets, confirmation results, and known survivors;
  survivors produce HUMAN_REQUIRED without claiming kernel containment.
- REQ-038: Acceptance failures append `final-validation-rejected`; legacy
  final-validation, ordinary validation, and attempt events never open gates.

## Acceptance criteria

- [x] AC-001: Canonical review identity and digest cover every REQ-001 field.
- [x] AC-002: Only matching PASS shards are reused and reuse emits a source-linked event.
- [x] AC-003: Missing/failed shards retry within both budgets; duplicate failures stop.
- [x] AC-004: Integration runs last and is invalidated after any file-shard execution.
- [x] AC-005: Timeout diagnostics are redacted; known process-group/descendant survivors fail closed.
- [x] AC-006: Oversized inputs fail before spawning Codex and timeout never exceeds 600 seconds.
- [x] AC-007: Final validation runs after evidence commit, records every attempt, and accepts only fully attributed PASS attempts.
- [x] AC-008: Review refuses a HEAD without matching validation PASS evidence.
- [x] AC-009: Tracked changes invalidate prior validation/review results.
- [x] AC-010: Merge gating rejects every validation/review/PR/CI SHA mismatch.
- [x] AC-011: validation-log rendering terminates without a self-referential commit loop.
- [x] AC-012: Existing framework, delivery, scope, safety, application, and build validation pass.
- [x] AC-013: A tracked snapshot event binds current HEAD, log blob, watermark, and contract digest.
- [x] AC-014: A dedicated final-validation-accepted PASS references its exact attempt and snapshot.
- [x] AC-015: Review refuses ordinary validation, missing/mismatched snapshots, dirty worktrees, and changed HEADs.
- [x] AC-016: Every canonical identity field independently invalidates reuse; malformed identities fail closed.
- [x] AC-017: Timeout and non-timeout exception persistence is centrally redacted and length bounded.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| Risk domain | `security`; review and approval integrity are fail-closed security controls. | 2026-07-13 |
| Timeout | Keep 600 seconds as a hard maximum; inject shorter values only in tests. | 2026-07-13 |
| Cache authority | Append-only runtime events, never mutable evidence files alone. | 2026-07-13 |
| Final log | Commit deterministic pre-final history, then record final PASS only in runtime events. | 2026-07-13 |
| Tracked snapshot attribution | The log records only its watermark and digests; its commit/blob attribution lives in append-only runtime evidence. | 2026-07-13 |
| Final validation kinds | Attempts audit every command result; only `final-validation-accepted/PASS` opens gates, while rejected and legacy events never do. | 2026-07-13 |
| Approved repair cycle | Human approved fixes limited to snapshot attribution, dedicated final validation, centralized redaction, and identity mutation tests. | 2026-07-13 |
| Process-group verification cycle | Human approved verification that reviewer children and grandchildren are gone after timeout, without extending the timeout or weakening gates. | 2026-07-13 |
| Escaped-descendant recovery cycle | Human approved retained PID tracking for descendants that leave the original process group, explicit runtime-evidence identity binding, separated snapshot/finalization phases, and append-only diagnostic persistence tests. | 2026-07-13 |
| Process isolation boundary | Guarantee the framework process group and observed controlled descendants with matching PID start identity; unknown pre-observation escapes are outside the portable guarantee and kernel containment is a future optional adapter. | 2026-07-13 |
| Controlled descendant | A descendant PID observed by the framework and bound to its process-start identity, preventing PID-reuse termination. Known survivors require human review. | 2026-07-13 |
| Accepted validation cycle | Human approved the attempt/accepted/rejected event model and a new bounded repair cycle after HEAD `6f97f320`; events 175 and 176 remain immutable legacy evidence. | 2026-07-13 |

## Scope

### Allowed changes

- `scripts/agent/**`, `tests/**`, `Makefile`, `README.md`, `docs/**`
- `specs/006-review-timeout-recovery/**`
- `specs/007-review-resume-and-exact-sha/**`
- required review schema or prompt version files, specifically
  `schemas/review-result.schema.json` and `prompts/review-feature.md`

### Forbidden changes

- Secrets, credentials, repository settings, and CI/CD secrets
- Feature 001 application code, `specs/001-project-crud/**`, state, events, and evidence
- Removal or weakening of review, validation, exact-SHA, scope, or approval gates
- Review timeout greater than 600 seconds

## Security and privacy

Diagnostics are allowlisted metadata plus redacted output tails. Prompts and
full command arguments are not copied into timeout events.
