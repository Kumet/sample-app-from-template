# Validation log: Approved recovery patch re-attribution
<!-- validation-snapshot: {"event_schema_version":1,"feature":"014-approved-recovery-patch-reattribution","generated_at":"2026-07-14T13:00:00+09:00","included_event_sequence":0,"snapshot_format_version":2,"validation_contract_digest":"736ff21eee69bc00fa58a2c041549e12442c30c7276e453d57b0fe3542d47340"} -->

This tracked log is the pre-final snapshot through event sequence 0. The
append-only runtime snapshot, exact-HEAD validation attempt, acceptance, and
review events are intentionally not written back into this file.

## Approved scope

- Human approval received for Feature 014 specification, implementation,
  regression tests, validation, independent review, push, PR, CI, and main
  merge in the template repository.
- The sample repository and Feature 002 worktree/state/events are excluded.

## Runs

- 2026-07-14 — Feature 014 spec-lint passed with no errors or warnings.
- 2026-07-14 — Python compilation passed for all framework modules.
- 2026-07-14 — Targeted recovery-patch suite passed: 12 tests.
- 2026-07-14 — Full framework test suite passed: 127 tests.
- 2026-07-14 — `make validate` passed: quality policy, secret filename check,
  lint/typecheck adapters, and all framework tests.
- 2026-07-14 — Scope audit passed for 9 approved paths; `git diff --check`
  passed.
- Dry-run fingerprints prove unchanged HEAD, branch, status, state, events,
  ownership marker, and Git index.
- Apply records approval and application events, re-attributed state, canonical
  HEAD/index/worktree digest, complete paths, contract, branch, and ownership.
- Missing or tampered evidence, post-approval content/index mutation, HEAD or
  contract change, scope violation, unapproved paths, and invalid ownership all
  fail closed.
- The sample repository and Feature 002 worktree/state/events were not accessed
  or changed.

## Review remediation loops

- Loop 1 — security review required explicit approval-reason redaction at the
  recovery boundary and independent ownership validation before active evidence
  reads the saved worktree. Added defense-in-depth redaction, exact registered
  worktree/marker revalidation in both active evidence and `work-resume`, and a
  regression proving a tampered state path is rejected before diff inspection.
- Loop 2 — tests review required full worktree-file dry-run fingerprints,
  command-path rejection of secret/runtime paths, and a TOCTOU regression
  between approval evidence and state mutation. Apply now repeats the complete
  inspection after appending approval evidence and refuses state mutation if any
  binding or digest changed; the new tests prove the state remains byte-identical.
- Loop 3 — spec-scope review found runtime path-name rejection only covered the
  repository root. Path validation now rejects `.agent-work`,
  `.agent-worktrees`, and `.agent-worktree-owned` as components at every depth,
  with nested-path regressions.
- Loop 4 — security review required secret-path admission to be independent of
  each feature's forbidden globs. Recovery path parsing now rejects environment
  files, key/certificate containers, credential/secret files, and common
  SSH/cloud credential directories at every depth before any file content read.
- New limited cycle 1 — the repeated security finding identified non-hidden
  confidential directory components such as `credentials/` and `secrets/`.
  Path admission now rejects credential, secret, private-key, API-key, and token
  directory components at every depth before scope or diff code can read files;
  regressions cover hidden and non-hidden variants.
- New limited cycle 2 — spec-scope review found that deleting both recovery
  binding fields made the state appear legacy. Active verification now checks
  append-only applied evidence for the exact state `updated_at`: matching
  evidence with absent fields fails closed, while an event-free legacy state and
  a later formally timestamped state remain accepted. The first full-suite run
  exposed a legacy event-schema fixture; binding-absent inspection now scans
  valid JSON only for the matching recovery event, while active bindings retain
  strict current-schema EventStore verification.
- New test-only cycle 1 — security review questioned whether sensitive paths
  already present in saved/current changes could reach digest I/O. A mock-only
  regression injects a credential-directory path without creating that file and
  proves both direct digest and full inspection reject it before recovery Git
  diff, sensitive-path `lstat`, or sensitive-path `open`; production code was
  unchanged.
