# Feature specification: Weakening evidence semantics

## Status

Approved

## Purpose

Prevent low-confidence test-weakening candidates from being presented as
established blocking findings while preserving mechanical fail-closed stops and
independent review of genuine test-strength regressions.

## Requirements

- REQ-001: Weakening inspection MUST distinguish high-confidence blocking
  findings from low-confidence review candidates in its public result model.
- REQ-002: A removed assertion line MUST remain a review candidate and MUST NOT
  become a blocking finding merely because the removed line exists.
- REQ-003: A newly written weakening event MUST state its mechanical verdict and
  store `blocking_findings` and `review_candidates` separately; it MUST NOT use
  an ambiguous findings-only payload.
- REQ-004: Any high-confidence test deletion, skip/disable marker, or CI failure
  condition weakening MUST continue to stop delivery fail closed.
- REQ-005: Independent review MUST treat review candidates as hypotheses and
  require concrete support from the current exact-HEAD diff before reporting a
  required weakening finding.
- REQ-006: Replacement or strengthening assertions that cover an updated
  expectation MUST not be reported as weakening solely because the old
  assertion appears as a removed diff line.
- REQ-007: Assertion removal without replacement MUST remain visible to the
  tests shard for independent evaluation.
- REQ-008: Low-confidence test candidates belong to the tests shard. Other file
  shards MUST NOT report a blocking finding solely from such a candidate;
  integration MAY verify gate composition and attribution.
- REQ-009: Review input MUST select one unambiguous authoritative weakening
  event for the current exact HEAD and MUST NOT mix events from another HEAD.
- REQ-010: Conflicting, failing, malformed, or unattributable weakening evidence
  MUST fail closed rather than being hidden by a later prompt instruction.
- REQ-011: A prompt or identity version change MUST invalidate reviews created
  with the old weakening semantics.
- REQ-012: The eight-call review budget, all review shards, integration order,
  bounded input, validation, scope, risk, exact-HEAD, and approval gates MUST
  remain unchanged.

## Acceptance criteria

- [ ] AC-001: Assertion expectation replacement and added assertions produce no
  mechanical blocking finding while low-confidence removal candidates remain
  available to tests review.
- [ ] AC-002: New PASS events expose an empty `blocking_findings` list and a
  separate `review_candidates` list with an explicit mechanical verdict.
- [ ] AC-003: Test deletion, skip/disable addition, and CI weakening retain their
  high-confidence fail-closed behavior.
- [ ] AC-004: Reviewer guidance requires current-diff corroboration, recognizes
  replacement/strengthening assertions, and confines candidate evaluation to
  the proper shard.
- [ ] AC-005: Runtime review evidence contains one authoritative current-HEAD
  weakening record and rejects ambiguous or invalid evidence.
- [ ] AC-006: Prompt identity changes invalidate old review results while the
  call budget, shard execution, integration ordering, and size limit remain.
- [ ] AC-007: Targeted regressions, full validation, and every independent
  review shard pass without weakening existing gates.

## Clarifications

- The approved user requirements are the clarification record; no unresolved
  product or implementation choice remains.
- `blocking_findings` are mechanically high-confidence and stop delivery before
  independent review. `review_candidates` are bounded risk evidence, not a
  mechanical verdict that weakening occurred.
- Review candidates are not hidden or auto-passed. The tests shard receives
  them together with the current diff and must make an independent judgment.
- Append-only runtime events are not rewritten. The review projection chooses
  the latest valid event for the current exact HEAD and treats contradictory
  current-HEAD evidence as invalid.
- The sample repository and Feature 002 worktree, state, and events are outside
  this implementation and validation scope.

## Scope

Allowed: weakening model/detection, delivery event construction, bounded review
evidence projection and guidance, review prompt, framework regression tests,
minimal framework documentation, and this feature directory.

Forbidden: sample repository content, Feature 002, runtime worktrees or events,
CI configuration, application source, secrets, production configuration,
review budget increases, shard omission, auto-pass behavior, and gate weakening.
