# Validation log: 001-project-crud
<!-- validation-snapshot: {"event_schema_version":1,"feature":"001-project-crud","generated_at":"2026-07-13T05:14:18.895225+00:00","included_event_sequence":17,"snapshot_format_version":2,"validation_contract_digest":"d2c19736548721ae1265e97c035496c510a219ffbf60bb8431209d022a01244b"} -->

This tracked snapshot does not embed its own commit SHA. Its commit and blob are attributed by the append-only tracked-evidence-snapshot event.

## Summary

Final included event result: FAIL.

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
