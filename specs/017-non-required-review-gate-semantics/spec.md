# Feature specification: Non-required review finding gate semantics

## Status

Implemented

## Purpose

Preserve a reviewer's raw result while giving chunk aggregation and pre-push
gates one fail-closed, exact-identity definition of whether review evidence is
safe to accept.

## Requirements

- REQ-001: New review chunk evidence MUST preserve the raw reviewer result and
  distinguish it from a mechanically derived gate verdict.
- REQ-002: Valid non-required findings MUST remain visible while permitting a
  PASS gate verdict; any required finding MUST produce a FAIL gate verdict.
- REQ-003: Reviewer errors, timeouts, invalid schemas, unknown or unexplained
  FAIL results, missing required flags, and incomplete identities MUST fail
  closed.
- REQ-004: Aggregate evidence MUST reference the complete exact-identity chunk
  set, preserve required and non-required findings, and use chunk gate verdicts.
- REQ-005: Pre-push MUST validate every expected chunk and aggregate rather than
  trusting aggregate PASS or raw reviewer PASS alone.
- REQ-006: Integration MUST run only after every file-shard gate verdict passes.
- REQ-007: Exact-identity reuse MUST accept only validated gate-PASS chunks and
  reject different HEAD, prompt, schema, paths, or runtime evidence.
- REQ-008: PR summaries and stored evidence MUST retain non-required findings
  without upgrading, deleting, or hiding them.
- REQ-009: Review limits, input limits, Feature 016 evidence ordering, validation,
  weakening, risk, scope, and approval gates MUST remain unchanged.

## Acceptance criteria

- [x] AC-001: Raw FAIL with only valid non-required findings is stored as raw
  FAIL with gate PASS and can satisfy aggregate and pre-push review gates.
- [x] AC-002: Required findings and malformed or unexplained failures stop
  aggregate and pre-push processing fail-closed.
- [x] AC-003: Chunk completeness, exact identity, aggregate membership, and
  integration ordering are mechanically verified.
- [x] AC-004: Non-required findings remain in runtime evidence, final review
  results, and PR summaries.
- [x] AC-005: Exact cache reuse requires a gate-PASS exact-identity event.
- [ ] AC-006: Targeted regressions, full validation, and all review shards pass.

## Clarifications

- The approved human prompt is the complete clarification record; no GitHub
  Issue or unresolved product decision was supplied.
- `reviewer_result` is the parsed subprocess result and is never rewritten.
- `gate_verdict` is derived only after schema validation: PASS requires no
  required findings and either reviewer PASS or at least one structured
  non-required finding explaining reviewer FAIL.
- A reviewer FAIL with no finding is unexplained and therefore gate FAIL.
- Existing append-only events remain untouched. An old identity-bound raw PASS
  remains compatible, but an old raw FAIL is never promoted to gate PASS
  without the new explicit verdict and finding partition.
- The sample repository and Feature 003 runtime artifacts are read-only and out
  of implementation scope.

## Scope

Allowed: review, delivery, and gate semantics; framework regressions; minimal
documentation; and this Feature 017 directory.

Forbidden: sample changes, application source, CI configuration, secrets,
production configuration, review budget changes, shard omission, auto-pass,
runtime evidence rewriting, or weakening any existing gate.
