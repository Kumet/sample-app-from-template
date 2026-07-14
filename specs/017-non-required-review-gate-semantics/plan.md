# Plan: Non-required review finding gate semantics

1. Add typed raw-result and gate-verdict projections to parsed review results.
2. Record canonical chunk and aggregate evidence with separated finding lists.
3. Validate exact-identity chunk/aggregate evidence in cache and pre-push gates.
4. Keep non-required findings in final results and PR summaries.
5. Add fail-closed regressions for malformed results, required findings,
   identity mismatch, incomplete chunks, ordering, reuse, and existing limits.
6. Run targeted validation, full validation, exact-HEAD review, CI, and merge.

## Compatibility

Pre-Feature-017 identity-bound PASS chunks remain compatible. Legacy FAIL
chunks are not silently upgraded into non-blocking evidence and must be
regenerated through the current review path.
