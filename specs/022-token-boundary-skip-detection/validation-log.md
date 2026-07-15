# Validation log: 022-token-boundary-skip-detection
<!-- validation-snapshot: {"event_schema_version":1,"feature":"022-token-boundary-skip-detection","generated_at":"2026-07-15T10:44:43.358965+00:00","included_event_sequence":18,"snapshot_format_version":2,"validation_contract_digest":"e53bd8e3cb238a4447f3af8ce7f2356ebfe10196f3b9287c7f5d01ad99184607"} -->

This tracked snapshot does not embed its own commit SHA. Its commit and blob are attributed by the append-only tracked-evidence-snapshot event.

## Summary

Final included event result: FAIL.

## Runs

| # | Event | Result | HEAD | Notes |
|---:|---|---|---|---|
| 1 | task/task-complete | PASS | `2a8ab1eb682c` | T004 |
| 2 | evidence/tracked-evidence-snapshot | PASS | `9ed7b6d51d43` |  |
| 3 | post-evidence/final-validation-attempt | PASS | `9ed7b6d51d43` |  |
| 4 | post-evidence/final-validation-accepted | PASS | `9ed7b6d51d43` |  |
| 5 | evidence/tracked-evidence-snapshot | PASS | `7a6e04bc7e2f` |  |
| 6 | post-evidence/final-validation-attempt | PASS | `7a6e04bc7e2f` |  |
| 7 | post-evidence/final-validation-accepted | PASS | `7a6e04bc7e2f` |  |
| 8 | delivery/weakening | PASS | `7a6e04bc7e2f` |  |
| 9 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 10 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 11 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 12 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 13 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 14 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 15 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 16 | review/review-shard | PASS | `7a6e04bc7e2f` |  |
| 17 | review/review-shard | FAIL | `7a6e04bc7e2f` |  |
| 18 | review/review-shard | FAIL | `7a6e04bc7e2f` |  |
