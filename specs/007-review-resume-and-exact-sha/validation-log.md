# Validation log: Review resume and exact-SHA validation

## Summary

Implementation and tracked evidence through the last pre-final validation are
complete. Feature 001 runtime evidence and stopped worktree were not changed.
The final exact-HEAD validation for the commit containing this log is recorded
only in append-only runtime evidence supplied to review, avoiding self-reference.

## Runs

| Loop | HEAD SHA | Phase | Command | Result | Notes |
|---:|---|---|---|---|---|
| 0 | `e51ca16` | Baseline | Investigation | Passed | Preserved Feature 006 timeout commit; identified missing shard identity/resume and post-evidence exact-HEAD validation. |
| 1 | `fd728612b3f5b7ec386a07e5e8578dc0b02f8b8e` | T001 | Unit tests | Passed | Canonical identity includes HEAD, shard, versions, command/model settings, reviewed files, and complete input digest; PASS reuse is event-backed. |
| 1 | `ad32939de47e54fef3385b69b6a56186ad3fd3b9` | T002 | Unit tests | Passed | Missing/failed shard retry is bounded; integration runs after file shards and includes their decision context. |
| 1 | `22adf70729285fee400abcc1f87e7b7a711c05c9` | T003 | Local subprocess tests | Passed | TERM and KILL paths terminate controlled parent/child process groups; diagnostics are redacted and identity-bound. |
| 1 | `6787d977f62c8f86808d0bde778e1e528c5b1eb8` | T004 | Framework regression tests | Passed | Exact-HEAD validation is rerun after evidence commit and required before review/push/merge gates. |
| 1 | Pre-evidence commit | T005 | `make validate` | Passed | 59 framework tests, 4 app tests, 2 integration tests, Ruff, mypy, secrets check, sdist, and wheel passed. |
| 2 | `a11d270b289c8138f89fecfe6fb98671ced81d5a` | Review repair | `make validate` | Passed | Pinned `gpt-5.4-mini` in the command and review identity after the default reviewer repeatedly timed out. Required review findings are addressed in the following evidence commit; its final validation event remains runtime-only. |
| 3 | `ec2b6ec0342967b8702f9d499c03b08a95aa1492` | Independent review | Required shards | Stopped safely | Exact-HEAD attribution, non-timeout redaction, and complete identity mutation coverage remained required. Exact-HEAD attribution repeated twice, triggering the bounded-loop stop. |
| 0 | `ec2b6ec0342967b8702f9d499c03b08a95aa1492` | Human approval | Four-finding repair cycle | Approved | New cycle is limited to tracked snapshot attribution, dedicated post-evidence validation, centralized exception redaction, and identity-field mutation tests. Gates and tests remain unchanged in strength. |
