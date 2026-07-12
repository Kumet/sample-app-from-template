# Validation log: Review resume and exact-SHA validation

## Summary

Implementation and tracked evidence are complete. Feature 001 runtime evidence
and stopped worktree were not changed. The final exact-HEAD validation is
recorded externally after this tracked evidence commit to avoid self-reference.

## Runs

| Loop | HEAD SHA | Phase | Command | Result | Notes |
|---:|---|---|---|---|---|
| 0 | `e51ca16` | Baseline | Investigation | Passed | Preserved Feature 006 timeout commit; identified missing shard identity/resume and post-evidence exact-HEAD validation. |
| 1 | `fd728612b3f5b7ec386a07e5e8578dc0b02f8b8e` | T001 | Unit tests | Passed | Canonical identity includes HEAD, shard, versions, command/model settings, reviewed files, and complete input digest; PASS reuse is event-backed. |
| 1 | `ad32939de47e54fef3385b69b6a56186ad3fd3b9` | T002 | Unit tests | Passed | Missing/failed shard retry is bounded; integration runs after file shards and includes their decision context. |
| 1 | `22adf70729285fee400abcc1f87e7b7a711c05c9` | T003 | Local subprocess tests | Passed | TERM and KILL paths terminate controlled parent/child process groups; diagnostics are redacted and identity-bound. |
| 1 | `6787d977f62c8f86808d0bde778e1e528c5b1eb8` | T004 | Framework regression tests | Passed | Exact-HEAD validation is rerun after evidence commit and required before review/push/merge gates. |
| 1 | Pre-evidence commit | T005 | `make validate` | Passed | 59 framework tests, 4 app tests, 2 integration tests, Ruff, mypy, secrets check, sdist, and wheel passed. |
