# Plan: Token-boundary skip detection

1. Capture the approved token-boundary, near-miss, and real-disable behavior in
   a version 2 validation contract and focused regression matrix.
2. Refine the skip matcher so standalone disable calls remain detectable while
   suffixes inside larger identifiers cannot match.
3. Verify the mechanical verdict and required finding fields, reviewer
   precondition behavior, and unchanged assertion/test-deletion/CI semantics.
4. Run targeted Feature 015/016/017 regressions, full validation, exact-HEAD
   review, CI, merge, and post-merge validation.

## Risk and rollback

Risk is high because weakening detection controls whether autonomous delivery
may proceed to independent review. The change is narrowly bounded to lexical
token recognition. Rollback is a normal revert of the matcher and regression
commit; no application data, schema, dependency, or production state changes.
