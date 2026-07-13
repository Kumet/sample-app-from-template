# Plan: Review timeout recovery

## Status

Approved

1. Replace the fixed review timeout with a named 600-second constant.
2. Keep timeout failures fail-closed and update the unit assertion.
3. Run specification lint and full validation.
4. Re-run the existing Feature 001 delivery only after the framework commit.
