# Implementation plan: Delivery smoke test

## Status

Approved

## Summary

Commit an approved medium-risk feature contract, then invoke the real
autonomous delivery entrypoint. Codex will add a small README section in an
isolated worktree. The framework will validate, independently review, push,
create one PR, and monitor CI without merging it.

## Existing code investigation

The delivery coordinator, worktree manager, Codex runner, structured review,
GitHub client, risk gate, and CI monitoring have unit coverage with controlled
stubs. No live delivery has yet exercised their composition.

## Affected files

| File | Change | Risk |
|---|---|---|
| `README.md` | Add smoke-test commands | Low |
| `specs/003-delivery-smoke-test/**` | Contract and evidence | Low |
| `scripts/agent/**`, `tests/**` | Only if live defects require repair | Medium |

## Design

Use one implementation task. Validation names map to allowlisted `test` and
`validate` Make targets. The declared medium risk guarantees the resulting PR
cannot auto-merge. Any live defect repair must add a regression test.

## Data model impact

None.

## API impact

None beyond documenting existing Make commands.

## UI impact

README documentation only.

## Test strategy

- Run the existing 30-test suite for the task.
- Run project-wide `make validate`.
- Inspect delivery evidence, PR uniqueness, check status, and merge state.
- Add a regression test if live behavior exposes a framework defect.

## Security considerations

Keep GitHub authentication outside Codex, inspect only safe evidence, and stop
on scope, secret, or risk escalation.

## Rollback strategy

Close the smoke-test PR and preserve the worktree/evidence for inspection. Do
not destructively reset or delete failed work.

## Open questions

- None.
