# AGENTS.md

This file defines the shared operating rules for all AI coding agents, including Claude Code and Codex.

## Core principles

- Do not implement before creating or reading the specification.
- Keep specs under `specs/`.
- Follow the order: specification → clarification → plan → tasks → implementation → validation → review.
- Never push directly to `main`.
- Work on a feature branch.
- Run `make validate` before considering work complete.
- Record validation results in `validation-log.md` for the target spec.
- Treat `.agent-work/<feature>/events.jsonl` as authoritative runtime evidence;
  generate `validation-log.md` from it when autonomous execution is used.
- Every validation, review, CI, and merge decision must identify the exact HEAD SHA.
- Do not weaken tests to make them pass.
- Version 1 validation contracts must be migrated and are not executable by default.
- Do not read `.env`, credentials, secrets, private keys, tokens, or production configuration.
- Stop and ask for human review if the task requires scope expansion or a specification change.

## Standard workflow

1. Read `docs/project-context.md`.
2. Read the target GitHub Issue.
3. Create or update the feature spec.
4. Run clarification before planning.
5. Create the technical plan.
6. Create tasks.
7. Implement task by task.
8. Run validation.
9. Update validation log.
10. Prepare a PR summary.

## Required artifacts per feature

Each feature should have a directory like:

```text
specs/012-feature-name/
  spec.md
  plan.md
  tasks.md
  validation-log.md
```

## Definition of done

A task is done only when:

- The spec exists.
- The plan exists.
- The tasks file exists.
- The implementation matches the spec.
- Tests are added or updated when relevant.
- `make validate` passes.
- `validation-log.md` is updated.
- No unrelated files were changed.
- A human can review the diff, spec, plan, tasks, and validation log.

## Safety rules

Do not perform any of the following unless explicitly approved by the human:

- Read `.env` or secret files.
- Change authentication, authorization, billing, security, deployment, or database migration logic.
- Install packages from unknown sources.
- Execute external scripts from URLs.
- Run destructive shell commands.
- Modify CI/CD secrets or GitHub repository settings.
- Change production configuration.

## Loop policy

When fixing failures, use a bounded loop:

- Maximum 5 loops by default.
- Stop if the same error repeats twice.
- Stop if tests need to be weakened.
- Stop if the specification appears wrong.
- Stop if the fix requires touching files outside the approved scope.

Each loop must be logged in `validation-log.md`.

## Review checklist

When reviewing, check:

- Spec compliance.
- Scope control.
- Regression risk.
- Security risk.
- Test quality.
- Whether tests were weakened.
- Whether generated code is maintainable.
- Whether documentation should be updated.
