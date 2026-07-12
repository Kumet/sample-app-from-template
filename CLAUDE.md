# CLAUDE.md

Read `AGENTS.md` first. This file contains Claude Code specific instructions.

## Claude Code role

Claude Code is primarily used for:

- Requirements discussion
- Specification creation
- Clarification
- Technical planning
- Codebase exploration
- Complex debugging
- Refactoring strategy
- PR and design review

## Claude-specific workflow

Use the following phase discipline:

1. **Explore**: read the relevant docs, code, issue, and existing specs.
2. **Plan**: propose a concise plan and identify risks.
3. **Implement**: modify the smallest reasonable scope.
4. **Validate**: run the relevant checks.
5. **Record**: update `validation-log.md`.
6. **Review**: summarize what changed and what humans should inspect.

## Rules

- Before large changes, present a plan.
- Do not implement during specification, clarification, or planning phases.
- Prefer small diffs.
- Prefer adding tests before or alongside implementation.
- Do not edit files outside the approved scope without explaining why and waiting for review.
- When Codex produced a review, read it before making follow-up changes.
- If a command fails, summarize the failure and next action before retrying.

## Useful prompts

### Start a feature

```text
Read AGENTS.md, CLAUDE.md, docs/project-context.md, and Issue #<number>.
Create only the feature specification under specs/<number>-<name>/spec.md.
Do not implement yet.
```

### Plan a feature

```text
Using the approved spec.md, create plan.md.
Investigate the codebase and identify affected files, risks, and test strategy.
Do not implement yet.
```

### Review a PR

```text
Review the PR against AGENTS.md, spec.md, plan.md, tasks.md, and validation-log.md.
Focus on scope creep, regression risk, security, and test quality.
```
