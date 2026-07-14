# AI operation guide

This document explains how to operate Claude Code and Codex in this repository.

## Principles

- AI agents do work; humans approve direction and risk.
- Specifications are the source of truth.
- CI is the minimum mechanical gate.
- PR review is the human quality gate.

`make deliver-dry-run FEATURE=<feature>` uses the same read-only worktree,
ownership-marker, saved-state, branch/HEAD, contract, changed-path, and task
inspection as delivery. It reports create, resume, completed reuse, or explicit
blocking reasons without creating markers, worktrees, runtime evidence, commits,
or remote mutations. Ownership markers are valid only at a registered linked
worktree root. A marker at the parent repository root blocks delivery and
requires human handling.

The report also exposes the shared root safe-start decision (branch, detached or
dirty state, unmerged paths, and in-progress Git operations) and normalized
`expected_worktree_path`, `saved_worktree_path`, and `worktree_path_match` values.
The same safe-start inspection drives the enforcing delivery check.

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

If a human-approved recovery edit adds paths to an existing failed worktree,
do not edit `state.json` or `events.jsonl`. Run
`make approve-recovery-patch-dry-run FEATURE=<feature> PATHS='<explicit paths>'
REASON='<approval>'`, inspect the bindings, then run the corresponding
`approve-recovery-patch` target. The command accepts only newly added explicit
paths with an unchanged HEAD. It verifies registered ownership, branch,
contract, scope, the complete changed-path set, and a canonical digest covering
working-tree contents and index state. Approval and application are recorded as
append-only events. Delivery recomputes the active digest and fails closed after
any post-approval change.

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
only when necessary, and do the same for observed controlled descendants whose
PID start identity still matches. Known survivors require human review. Unknown
processes that escape before observation are not claimed as a portable guarantee;
kernel containment is a future optional adapter. Diagnostics contain allowlisted
identity metadata and redacted output tails. The timeout remains capped at 600 seconds.

The reviewer model is explicitly pinned in the review command and included in
the identity digest. Changing that model invalidates every cached shard. The
current reviewer is `gpt-5.4-mini`, selected for bounded, structured review.

Generate and commit `validation-log.md` from pre-final events, then run full
validation on that new HEAD and append the PASS runtime event. Do not regenerate
tracked evidence afterward. PR summaries identify the tracked-log cutoff, final
validation event, and validated HEAD.

The runtime sequence is strictly:

1. Render and commit snapshot-format validation log.
2. Append `evidence/tracked-evidence-snapshot` with HEAD, log Git blob,
   watermark, contract digest, and format version.
3. Run the full command on that unchanged HEAD.
4. Append `post-evidence/final-validation-attempt` for every command result.
5. Verify HEAD, attempt, snapshot, log blob, contract, result digest, and clean state.
6. Append `post-evidence/final-validation-accepted/PASS` only when every check
   succeeds; otherwise append `final-validation-rejected` when attribution fails.
7. Require the accepted PASS before review.

Ordinary task or pre-commit `validation` events never satisfy the final gate.
All reviewer exceptions pass through centralized redaction before event,
diagnostic, notification, or report persistence; EventStore recursively redacts
again as defense in depth.

## Test-weakening evidence

Mechanical weakening inspection records an explicit verdict with separate
`blocking_findings` and `review_candidates`. Blocking findings are
high-confidence conditions such as test deletion, an added skip marker, or a CI
failure condition being disabled; they stop delivery before review. Review
candidates are low-confidence signals such as a removed assertion diff line.
They remain visible to the tests review shard but are not proof of weakening.

The tests reviewer must corroborate a candidate against the current exact-HEAD
diff. Replacing an old assertion with an updated expectation or stronger
assertions is not weakening merely because the old line is removed. Other file
shards do not turn a test candidate into a blocking finding, while integration
may still verify the evidence identity and gate composition. Review input uses
one authoritative weakening record for the current HEAD and fails closed for
conflicting or malformed current-HEAD evidence.

Every reviewer invocation requires that canonical weakening PASS to belong to
the same exact HEAD, feature, branch, and isolated worktree as the accepted final
validation. Review and CI repairs create a new commit, so they repeat final
validation and weakening inspection before any reviewer is started for the new
HEAD. Missing or stale weakening evidence stops before consuming the bounded
review-call budget.
