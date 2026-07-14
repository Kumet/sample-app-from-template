# Plan: Container validation target policy

1. Extend only the repository policy target list with the two approved exact
   container target names.
2. Add policy-level regressions for accepted existing/container targets and
   fail-closed rejection of arbitrary, partial, case-variant, argument-bearing,
   multi-target, and injection-shaped values.
3. Add spec-lint regressions using complete version 2 contracts to prove both
   container targets are accepted only when explicitly requested.
4. Prove a non-container contract retains identical command construction and
   inspect the ordinary Make validation dependency graph for Docker independence.
5. Run targeted tests, full validation, exact-HEAD independent review, CI, and
   PR merge without changing framework implementation code.

## Risk and rollback

Risk is high because the policy expands which repository Make targets may be
executed by autonomous validation. The expansion is bounded to two exact names.
Rollback is a normal revert of the policy and regression-test commit; no state,
schema, dependency, deployment, or production migration is involved.
