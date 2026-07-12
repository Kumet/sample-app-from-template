# Implementation plan: Production-ready autonomous template

## Status

Implemented

## Summary

Introduce a versioned event/evidence core first, then migrate orchestration and
delivery gates to exact-SHA decisions. Add bounded modules for approvals,
doctor, quality configuration, contract migration, sharded review, SHA-scoped
CI, notifications, queue/locks, telemetry, stack qualification, and release
readiness. Preserve standard-library-only runtime and stub all remote tests.

## Existing code investigation

The live feature 003 delivery proves the current path but also demonstrates
split evidence, manual scope/state repair, long monolithic reviews, and evidence
commits that require renewed gates. Current version 1 work remains executable,
CI log lookup is not run/SHA-specific, adapters are proposals, and quality
placeholder targets pass.

## Affected files

| Area | Change | Risk |
|---|---|---|
| `scripts/agent/**` | Add and integrate production orchestration modules | High |
| policy/schemas/prompts | Version contracts and gates | High |
| adapters/fixtures/tests | Stack qualification | Medium |
| Make/docs/release files | Operator and release interface | Medium |

## Design

An append-only versioned JSONL event store becomes the source of truth. Gate
events carry exact SHA and are reduced into a deterministic delivery state and
Markdown log. Policy owns quality, budgets, legacy behavior, queue concurrency,
notifications, and adapter selection. All mutation interfaces support dry-run
or preview. GitHub interactions resolve PR head to workflow/job identity.
Reviews shard complete inputs and aggregate schema-bound SHA results.

## Test strategy

- Unit tests for every parser, reducer, lock, budget, and safety decision.
- Temporary Git repositories for scope, migration, worktree, and release checks.
- Stubbed Codex/GitHub/notification boundaries.
- Offline Python, Node.js, and Go fixture qualification.
- Existing tests remain green.

## Security considerations

Fail closed on SHA drift, event corruption, unknown executable migration,
unsafe scope patterns, lock conflicts, oversized unsplittable reviews, and
budget exhaustion. Central redaction applies before every persisted event or
notification. No remote tests or destructive Git operations.

## Rollback strategy

Revert feature commits. Event schemas are additive and existing ignored runtime
logs remain inspectable. No automatic destructive migration is provided.

## Open questions

- None blocking implementation.
