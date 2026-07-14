# Feature specification: Post-repair weakening evidence ordering

## Status

Implemented

## Purpose

Require canonical weakening evidence for the current exact validated HEAD before
any independent reviewer runs, including after review and CI repair commits.

## Requirements

- REQ-001: Review requires current-HEAD snapshot, accepted final validation, and
  canonical weakening PASS evidence before consuming review-call budget.
- REQ-002: Evidence order is tracked log commit, snapshot, attempt, acceptance,
  weakening inspection/PASS, file shards, then integration.
- REQ-003: Review repair MUST regenerate final evidence and weakening evidence
  for its new HEAD before the next reviewer subprocess.
- REQ-004: Post-CI repair MUST apply the same evidence ordering before review.
- REQ-005: Missing, stale, failing, malformed, mismatched-feature, branch, or
  worktree weakening evidence MUST fail closed without a reviewer call.
- REQ-006: High-confidence blocking findings MUST stop before review; candidates
  MUST remain reviewable through canonical PASS evidence.
- REQ-007: Identical exact-HEAD PASS evidence MUST not be duplicated, while a
  changed HEAD receives new authoritative evidence.
- REQ-008: Append-only history, tracked-log snapshot semantics, and exact review
  identity/cache attribution MUST be preserved.
- REQ-009: Review calls remain capped at eight; exhaustion, shard execution,
  integration ordering, input limits, and all existing gates remain unchanged.

## Acceptance criteria

- [x] AC-001: Initial, review-repair, and post-CI review paths all record a
  current-HEAD weakening PASS after acceptance and before review.
- [x] AC-002: Missing, stale, malformed, failing, or identity-mismatched evidence
  prevents reviewer execution and consumes zero calls.
- [x] AC-003: Blocking findings prevent review; candidate-only inspection permits
  review and is present in its identity-bound runtime evidence.
- [x] AC-004: Duplicate same-HEAD evidence is avoided and changed-HEAD evidence
  is appended without rewriting history.
- [x] AC-005: Exact cached PASS reuse, eight-call exhaustion, all shards,
  integration order, and bounded inputs retain their behavior.
- [ ] AC-006: Targeted regressions, full validation, and every review shard pass.

## Clarifications

- The approved user prompt is the complete clarification record; no GitHub Issue
  or unresolved product decision exists.
- Weakening inspection is performed only after exact-HEAD final acceptance so the
  review input binds both gates to the same immutable HEAD.
- A precondition check is mechanical and does not consume review-call budget.
- The sample repository and Feature 003 runtime artifacts are read-only and out
  of implementation scope.

## Scope

Allowed: delivery/review weakening-order helpers, necessary weakening helper,
framework regressions, minimal documentation, and this Feature 016 directory.

Forbidden: sample changes, CI configuration, application source, secrets,
production configuration, review budget changes, shard omission, auto-pass,
runtime evidence rewriting, and gate weakening.
