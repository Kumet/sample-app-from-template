# Validation log: 001-project-crud
<!-- validation-snapshot: {"event_schema_version":1,"feature":"001-project-crud","generated_at":"2026-07-13T07:43:54.689702+00:00","included_event_sequence":50,"snapshot_format_version":2,"validation_contract_digest":"d2c19736548721ae1265e97c035496c510a219ffbf60bb8431209d022a01244b"} -->

This tracked snapshot does not embed its own commit SHA. Its commit and blob are attributed by the append-only tracked-evidence-snapshot event.

## Summary

Final included event result: INVALID.

## Runs

| # | Event | Result | HEAD | Notes |
|---:|---|---|---|---|
| 1 | task/scope-request | FAIL | `c5bfeeaa1527` | Unsafe scope failure requires human review: Out-of-scope files changed: src/local_project_board.egg-info/ |
| 2 | approval/scope-request | HUMAN_REQUIRED | `c5bfeeaa1527` | Ignore setuptools-generated *.egg-info so build validation remains clean |
| 3 | approval/scope-approved | PASS | `` | Ignore setuptools-generated *.egg-info so build validation remains clean |
| 4 | task/scope-request | FAIL | `c5bfeeaa1527` | Unsafe scope failure requires human review: Out-of-scope files changed: src/local_project_board.egg-info |
| 5 | approval/scope-request | HUMAN_REQUIRED | `c5bfeeaa1527` | Synchronize approved gitignore repair after repeated generated egg-info scope failure |
| 6 | approval/scope-approved | PASS | `` | Synchronize approved gitignore repair after repeated generated egg-info scope failure |
| 7 | task/task-complete | PASS | `e5e944bfc9c1` | T001 |
| 8 | task/task-complete | PASS | `a2e35dd157ef` | T002 |
| 9 | task/task-complete | PASS | `f0264331f5e3` | T003 |
| 10 | task/task-complete | PASS | `b4267082ddff` | T004 |
| 11 | task/task-complete | PASS | `d62fea10e29f` | T005 |
| 12 | task/task-complete | PASS | `19ac10bd36fc` | T006 |
| 13 | task/task-complete | PASS | `3977e55cd70d` | T007 |
| 14 | final/validation | PASS | `b7a24e1a2bef` |  |
| 15 | evidence/tracked-evidence-snapshot | PASS | `132b67c54bb2` |  |
| 16 | post-evidence/final-validation-attempt | PASS | `132b67c54bb2` |  |
| 17 | post-evidence/final-validation-rejected | FAIL | `132b67c54bb2` | Final-validation acceptance requires a clean worktree |
| 18 | evidence/tracked-evidence-snapshot | PASS | `817e8651d966` |  |
| 19 | post-evidence/final-validation-attempt | PASS | `817e8651d966` |  |
| 20 | post-evidence/final-validation-accepted | PASS | `817e8651d966` |  |
| 21 | delivery/weakening | PASS | `817e8651d966` |  |
| 22 | evidence/tracked-evidence-snapshot | PASS | `6efb06511d40` |  |
| 23 | post-evidence/final-validation-attempt | PASS | `6efb06511d40` |  |
| 24 | post-evidence/final-validation-accepted | PASS | `6efb06511d40` |  |
| 25 | delivery/weakening | PASS | `6efb06511d40` |  |
| 26 | review/review-shard | FAIL | `6efb06511d40` |  |
| 27 | review/review-shard | FAIL | `6efb06511d40` |  |
| 28 | evidence/tracked-evidence-snapshot | PASS | `43d3c581465e` |  |
| 29 | post-evidence/final-validation-attempt | PASS | `43d3c581465e` |  |
| 30 | post-evidence/final-validation-accepted | PASS | `43d3c581465e` |  |
| 31 | delivery/weakening | PASS | `43d3c581465e` |  |
| 32 | review/review-shard | FAIL | `43d3c581465e` |  |
| 33 | review/review-shard | FAIL | `43d3c581465e` |  |
| 34 | review/review-shard | PASS | `43d3c581465e` |  |
| 35 | review/review-shard | PASS | `43d3c581465e` |  |
| 36 | review/review-shard | INVALID | `43d3c581465e` | ValueError |
| 37 | review/review-shard | FAIL | `43d3c581465e` |  |
| 38 | review/review-shard | FAIL | `43d3c581465e` |  |
| 39 | review/review-shard | FAIL | `43d3c581465e` |  |
| 40 | review/review-shard | FAIL | `43d3c581465e` |  |
| 41 | evidence/tracked-evidence-snapshot | PASS | `55a2ec554987` |  |
| 42 | post-evidence/final-validation-attempt | PASS | `55a2ec554987` |  |
| 43 | post-evidence/final-validation-accepted | PASS | `55a2ec554987` |  |
| 44 | review/review-shard | PASS | `55a2ec554987` |  |
| 45 | review/review-shard | FAIL | `55a2ec554987` |  |
| 46 | review/review-shard | FAIL | `55a2ec554987` |  |
| 47 | review/review-shard | PASS | `55a2ec554987` |  |
| 48 | review/review-shard | PASS | `55a2ec554987` |  |
| 49 | review/review-shard | INVALID | `55a2ec554987` | RuntimeError |
| 50 | review/review-shard | INVALID | `55a2ec554987` | RuntimeError |
