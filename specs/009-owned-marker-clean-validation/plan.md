# Plan: Owned marker clean validation

## Status

Implemented

1. Reuse the registered-worktree ownership helper for evidence cleanliness.
2. Expose the existing read-only Git status parser through a narrow helper.
3. Apply verified-marker filtering to acceptance and final-evidence lookup.
4. Add linked-worktree and adversarial marker regression tests.
5. Run specification, targeted, full, and independent review validation.
