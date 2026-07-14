# Validation log: 002-task-crud
<!-- validation-snapshot: {"event_schema_version":1,"feature":"002-task-crud","generated_at":"2026-07-14T10:47:06.095066+00:00","included_event_sequence":13,"snapshot_format_version":2,"validation_contract_digest":"debc5a9b82ccbc9f73f3d059a4f43e5abbf29c4354615a98f8a5e39548b2199a"} -->

This tracked snapshot does not embed its own commit SHA. Its commit and blob are attributed by the append-only tracked-evidence-snapshot event.

## Summary

Final included event result: PASS.

## Runs

| # | Event | Result | HEAD | Notes |
|---:|---|---|---|---|
| 1 | task/task-complete | PASS | `d2cc4fa792c5` | T001 |
| 2 | task/failure | FAIL | `d2cc4fa792c5` | Identical failure repeated for T002: full exited 2: make[1]: *** [format-check] Error 1  |
| 3 | approval/recovery-patch-approved | PASS | `d2cc4fa792c5` | Human-approved Ruff format-only recovery after repeated format-check failure |
| 4 | approval/recovery-patch-applied | PASS | `d2cc4fa792c5` | Approved recovery patch re-attributed to failed state |
| 5 | task/task-complete | PASS | `db3bfe1b02f1` | T002 |
| 6 | task/task-complete | PASS | `069db054f07f` | T003 |
| 7 | task/task-complete | PASS | `94949b381892` | T004 |
| 8 | task/task-complete | PASS | `4b1a1e7fc620` | T005 |
| 9 | task/task-complete | PASS | `5fb792780c5a` | T006 |
| 10 | task/task-complete | PASS | `ff647028085e` | T007 |
| 11 | task/task-complete | PASS | `f308e8ed4de4` | T008 |
| 12 | task/task-complete | PASS | `c2842aac23ad` | T009 |
| 13 | task/task-complete | PASS | `7c378c9d4238` | T010 |
