# Validation log: 002-task-crud
<!-- validation-snapshot: {"event_schema_version":1,"feature":"002-task-crud","generated_at":"2026-07-14T12:11:59.448327+00:00","included_event_sequence":77,"snapshot_format_version":2,"validation_contract_digest":"debc5a9b82ccbc9f73f3d059a4f43e5abbf29c4354615a98f8a5e39548b2199a"} -->

This tracked snapshot does not embed its own commit SHA. Its commit and blob are attributed by the append-only tracked-evidence-snapshot event.

## Summary

Final included event result: FAIL.

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
| 14 | evidence/tracked-evidence-snapshot | PASS | `a9ca0a0be313` |  |
| 15 | post-evidence/final-validation-attempt | PASS | `a9ca0a0be313` |  |
| 16 | post-evidence/final-validation-accepted | PASS | `a9ca0a0be313` |  |
| 17 | delivery/weakening | PASS | `a9ca0a0be313` |  |
| 18 | review/review-shard | FAIL | `a9ca0a0be313` |  |
| 19 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 20 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 21 | review/review-shard | FAIL | `a9ca0a0be313` |  |
| 22 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 23 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 24 | review/review-shard | FAIL | `a9ca0a0be313` |  |
| 25 | review/review-shard | FAIL | `a9ca0a0be313` |  |
| 26 | review/review-shard | FAIL | `a9ca0a0be313` |  |
| 27 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 28 | review/review-shard | PASS | `a9ca0a0be313` |  |
| 29 | evidence/tracked-evidence-snapshot | PASS | `ad90ffcba10f` |  |
| 30 | post-evidence/final-validation-attempt | PASS | `ad90ffcba10f` |  |
| 31 | post-evidence/final-validation-accepted | PASS | `ad90ffcba10f` |  |
| 32 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 33 | review/review-shard | HUMAN_REQUIRED | `ad90ffcba10f` | ReviewBudgetExhausted |
| 34 | delivery/weakening | PASS | `ad90ffcba10f` |  |
| 35 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 36 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 37 | review/review-shard | FAIL | `ad90ffcba10f` |  |
| 38 | review/review-shard | FAIL | `ad90ffcba10f` |  |
| 39 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 40 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 41 | review/review-shard | FAIL | `ad90ffcba10f` |  |
| 42 | review/review-shard | FAIL | `ad90ffcba10f` |  |
| 43 | review/review-shard | FAIL | `ad90ffcba10f` |  |
| 44 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 45 | review/review-shard | PASS | `ad90ffcba10f` |  |
| 46 | evidence/tracked-evidence-snapshot | PASS | `51aa06c210b5` |  |
| 47 | post-evidence/final-validation-attempt | PASS | `51aa06c210b5` |  |
| 48 | post-evidence/final-validation-accepted | PASS | `51aa06c210b5` |  |
| 49 | review/review-shard | PASS | `51aa06c210b5` |  |
| 50 | review/review-shard | HUMAN_REQUIRED | `51aa06c210b5` | ReviewBudgetExhausted |
| 51 | delivery/weakening | PASS | `51aa06c210b5` |  |
| 52 | review/review-shard | FAIL | `51aa06c210b5` |  |
| 53 | review/review-shard | PASS | `51aa06c210b5` |  |
| 54 | review/review-shard | PASS | `51aa06c210b5` |  |
| 55 | review/review-shard | FAIL | `51aa06c210b5` |  |
| 56 | review/review-shard | PASS | `51aa06c210b5` |  |
| 57 | review/review-shard | PASS | `51aa06c210b5` |  |
| 58 | review/review-shard | FAIL | `51aa06c210b5` |  |
| 59 | review/review-shard | FAIL | `51aa06c210b5` |  |
| 60 | review/review-shard | FAIL | `51aa06c210b5` |  |
| 61 | review/review-shard | PASS | `51aa06c210b5` |  |
| 62 | review/review-shard | PASS | `51aa06c210b5` |  |
| 63 | evidence/tracked-evidence-snapshot | PASS | `29739819513c` |  |
| 64 | post-evidence/final-validation-attempt | PASS | `29739819513c` |  |
| 65 | post-evidence/final-validation-accepted | PASS | `29739819513c` |  |
| 66 | review/review-shard | PASS | `29739819513c` |  |
| 67 | review/review-shard | HUMAN_REQUIRED | `29739819513c` | ReviewBudgetExhausted |
| 68 | delivery/weakening | PASS | `29739819513c` |  |
| 69 | review/review-shard | FAIL | `29739819513c` |  |
| 70 | review/review-shard | FAIL | `29739819513c` |  |
| 71 | review/review-shard | FAIL | `29739819513c` |  |
| 72 | review/review-shard | FAIL | `29739819513c` |  |
| 73 | review/review-shard | FAIL | `29739819513c` |  |
| 74 | review/review-shard | FAIL | `29739819513c` |  |
| 75 | review/review-shard | FAIL | `29739819513c` |  |
| 76 | review/review-shard | FAIL | `29739819513c` |  |
| 77 | review/review-shard | FAIL | `29739819513c` |  |
