# Plan: Canonical redacted review evidence

1. Define one review-layer helper that recursively redacts and validates the
   persisted result/findings representation before any digest is calculated.
2. Use that representation for chunk evidence fields, required/non-required
   projections, aggregate evidence, evidence files, and exact round-trip checks.
3. Redact review repair detail and PR summaries before external or tracked
   output, while retaining raw reviewer result and required semantics.
4. Version review identity and add focused persistence, tampering, cache,
   redaction-pattern, budget, ordering, and gate regressions.
5. Run targeted tests, full validation, exact-HEAD independent review, CI,
   merge, and post-merge validation.

## Risk and rollback

Risk is high because review evidence controls pre-push authorization. The change
keeps all gates fail-closed and only moves canonical redaction before digest
construction. Rollback is a normal revert; no data schema, dependency,
deployment, or production state changes are involved.
