# Plan: Weakening evidence semantics

## Status

Approved

1. Introduce an explicit weakening inspection result that separates blocking
   findings from review candidates.
2. Emit unambiguous exact-HEAD weakening evidence and project one authoritative
   record into independent review.
3. Update shard guidance and the versioned prompt semantics so candidates
   require current-diff corroboration.
4. Add regression coverage for strengthened assertions, genuine high-confidence
   weakening, event selection, review identity, budgets, ordering, and limits.
5. Run specification lint, targeted tests, full validation, and all review
   shards before delivery.
