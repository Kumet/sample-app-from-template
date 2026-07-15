# Feature specification: Canonical redacted review evidence

## Status

Approved

## Purpose

Bind review evidence digests to the exact recursively redacted payload that is
persisted, so defense-in-depth event redaction cannot invalidate otherwise
valid non-required review findings and no secret-shaped reviewer text reaches
events, evidence files, repair input, or pull-request summaries.

## Requirements

- REQ-001: Review evidence MUST recursively redact the structured reviewer
  result before canonical serialization and digest calculation.
- REQ-002: `findings`, `required_findings`, `non_required_findings`, and
  `review_payload_digest` MUST derive from one canonical redacted result and
  finding set.
- REQ-003: EventStore's second redaction pass MUST be idempotent, and a stored
  chunk MUST round-trip through exact-identity validation with the same digest.
- REQ-004: Raw reviewer FAIL with only explicit non-required findings MUST
  retain reviewer FAIL and redacted findings while receiving gate PASS; any
  required finding MUST remain blocking.
- REQ-005: Aggregate findings and `aggregate_digest` MUST use canonical redacted
  findings and remain verifiable after EventStore persistence.
- REQ-006: Review evidence files, events, review repair detail, PR body, and
  outbox-visible text MUST NOT contain pre-redaction secret-shaped finding text.
- REQ-007: Digest, finding, identity, schema, chunk, or aggregate tampering MUST
  continue to fail closed; prior mismatched evidence MUST NOT gain a permissive
  compatibility path.
- REQ-008: Review identity semantics MUST be versioned so prior identities and
  caches cannot be reused under the new canonicalization rules.
- REQ-009: Existing exact-HEAD, shard completeness, integration ordering,
  accepted-to-weakening-to-review ordering, input limit, eight-call budget, and
  approval gates MUST remain unchanged.
- REQ-010: Existing password, token, secret, API key, bearer credential,
  GitHub-token, and OpenAI-key redaction patterns MUST remain effective and
  repeated redaction MUST not change canonical output.
- REQ-011: A review-repair scope violation MUST preserve the patch, atomically
  transition runtime state to `failed/scope`, and append a normalized
  `scope-request/HUMAN_REQUIRED` event so the existing worktree can use the
  formal scope-approval and re-attribution workflow.

## Acceptance criteria

- [x] AC-001: Secret-shaped finding text is redacted before digesting and is
  absent from event/evidence/PR/repair outputs.
- [x] AC-002: Persisted non-required raw FAIL evidence round-trips with gate
  PASS, while required findings remain gate FAIL.
- [x] AC-003: Chunk and aggregate digests validate after EventStore redaction,
  and payload/digest tampering is rejected.
- [x] AC-004: The identity version changes and old or malformed evidence is not
  reused.
- [ ] AC-005: Related regressions, full validation, exact-HEAD review, CI, and
  post-merge validation pass with no gate weakening.
- [ ] AC-006: Review-repair scope failures are resumable only after a matching
  formal scope approval; event append failure restores the previous state.

## Clarifications

- The approved human prompt is authoritative; no GitHub Issue is required.
- Canonicalization binds the persisted redacted representation. No raw payload
  or raw-payload digest is persisted as a compatibility aid.
- Reviewer output is parsed and schema-validated before redaction. Redaction
  changes string content only and never repairs malformed structure.
- EventStore remains a final defense-in-depth redaction boundary and is not
  modified by this Feature unless an unanticipated requirement is approved.
- Old digest-mismatched events remain unusable; a new exact-identity reviewer
  result is required.
- The sample repository and Feature 020 evidence are read-only and out of scope.

## Scope

### Allowed changes

Allowed: review canonicalization and identity, delivery output redaction,
review-repair scope failure attribution, direct review/redaction/delivery
regressions, this Feature directory, the approved review prompt, and minimal
repository-neutral documentation.

Necessary existing identity regressions in production-readiness, validation
evidence, and weakening-evidence suites are included because they intentionally
pin the current review identity schema version.

- `prompts/review-feature.md`

- `scripts/agent/scope_approval.py`

### Forbidden changes

Forbidden: EventStore or gate relaxation, raw secret persistence, compatibility
bypasses, reviewer/budget/limit changes, sample changes, and unrelated files.

## Definition of done

Canonical redacted chunk and aggregate evidence round-trip through persistence
and exact-identity gates, all output surfaces are redacted, old caches are
invalidated, all approved tests and review shards pass, and the branch is merged
through a successful pull request.
