# Codex usage

Codex is primarily used for:

- Implementing GitHub Issues
- Fixing CI failures
- Adding tests
- Reviewing PRs independently
- Investigating bugs
- Performing bounded implementation loops

## Before starting

Codex should read:

1. `AGENTS.md`
2. `docs/project-context.md`
3. The target GitHub Issue
4. The target `specs/<issue>-<feature>/` directory

## Standard Codex prompt

```text
Read AGENTS.md and docs/project-context.md.
Work on Issue #<number>.
Use the existing spec.md, plan.md, and tasks.md.
Implement tasks in order.
Run make validate.
Update validation-log.md.
Do not expand scope.
```

## CI fix prompt

```text
Read AGENTS.md and the failing CI logs.
Fix only the cause of the CI failure.
Do not weaken tests.
Run make validate.
Update validation-log.md.
```

## Review prompt

```text
Review this PR against AGENTS.md and the spec artifacts.
Focus on specification compliance, unrelated changes, test quality, and security risk.
Do not make changes unless asked.
```
