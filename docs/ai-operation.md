# AI operation guide

This document explains how to operate Claude Code and Codex in this repository.

## Principles

- AI agents do work; humans approve direction and risk.
- Specifications are the source of truth.
- CI is the minimum mechanical gate.
- PR review is the human quality gate.

## Phase gates

### 1. Specification gate

Before implementation, confirm:

- `spec.md` exists.
- Requirements are understandable.
- Acceptance criteria are testable.
- Non-goals are explicit.

### 2. Plan gate

Before implementation, confirm:

- `plan.md` exists.
- Affected files are identified.
- Test strategy is clear.
- Security and migration risks are called out.

### 3. Task gate

Before implementation, confirm:

- `tasks.md` exists.
- Tasks are small enough.
- Each task has a validation method.

### 4. Validation gate

Before PR, confirm:

- `make validate` passes.
- `validation-log.md` is updated.
- Tests were not weakened.
- No secrets were touched.

## Recommended division of labor

### Claude Code

Use Claude Code for:

- Understanding the system
- Creating specs and plans
- Investigating complex failures
- Reviewing design quality

### Codex

Use Codex for:

- Implementing tasks
- Fixing CI failures
- Adding tests
- Reviewing PR diffs independently

## Standard prompts

## Automated execution

After the feature contract is approved and committed on a feature branch:

```bash
make validate-spec FEATURE=012-feature-name
make work-dry-run FEATURE=012-feature-name
make work FEATURE=012-feature-name
make work-status FEATURE=012-feature-name
```

`make work` runs one task at a time, uses only named validations from
`validation.toml`, commits successful tasks locally, and never pushes or
merges. A stopped run preserves its diff and evidence under `.agent-work/` for
human review.

For autonomous delivery, use `make deliver-dry-run` first and then
`make deliver`. Low-risk merge is disabled unless both repository and feature
policy explicitly enable it. Medium risk stops at a PR and high risk stops
before push. Use `work-resume` only when saved branch, HEAD, contract digest,
and changed paths still match.

### Create a spec

```text
Read AGENTS.md, docs/project-context.md, and Issue #<number>.
Create specs/<number>-<name>/spec.md only.
Do not implement anything yet.
```

### Create a plan

```text
Using the approved spec.md, inspect the codebase and create plan.md.
Identify affected files, risks, and test strategy.
Do not implement anything yet.
```

### Implement tasks

```text
Use tasks.md and implement tasks in order.
Keep diffs small.
Run make validate.
Update validation-log.md.
Stop if scope changes are required.
```

### Review

```text
Review the PR against AGENTS.md, spec.md, plan.md, tasks.md, and validation-log.md.
Focus on scope, regression risk, security, and test quality.
```

## Resumable review and exact-HEAD evidence

Review reuse is an exact-identity decision backed by append-only events. Never
edit review JSON or events to make a shard reusable. A reused PASS records a new
decision event referencing its source sequence. Any tracked change invalidates
validation and every review shard.

Review timeouts terminate the dedicated process group with TERM and then KILL
only when necessary. Diagnostics contain allowlisted identity metadata and
redacted output tails. The timeout remains capped at 600 seconds.

The reviewer model is explicitly pinned in the review command and included in
the identity digest. Changing that model invalidates every cached shard. The
current reviewer is `gpt-5.4-mini`, selected for bounded, structured review.

Generate and commit `validation-log.md` from pre-final events, then run full
validation on that new HEAD and append the PASS runtime event. Do not regenerate
tracked evidence afterward. PR summaries identify the tracked-log cutoff, final
validation event, and validated HEAD.
