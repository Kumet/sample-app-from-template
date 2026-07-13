# Feature specification: State-aware delivery dry-run

## Status

Implemented

## Purpose

Make delivery dry-run report the same existing-worktree resume decision used by
delivery, without mutating the repository, runtime evidence, or worktrees. Guard
ownership marker creation so it can occur only inside a registered isolated
worktree and never at the repository root.

## Requirements

- REQ-001: Dry-run detects an existing feature worktree read-only.
- REQ-002: Only a missing worktree reports `create-isolated-worktree`.
- REQ-003: A valid framework-owned worktree reports `resume-existing-worktree`.
- REQ-004: Inspection covers path, marker/feature, branch/HEAD, state identity and
  status, contract digest, changed paths, and task completion.
- REQ-005: Output contains worktree action/path/existence, ownership validity,
  state status/failure/task, saved/current HEAD, contract/branch/path matches,
  completed/pending tasks, resume safety, blockers, and planned remote mutations.
- REQ-006: Unsafe resume reports explicit blocking reasons.
- REQ-007: Dry-run changes no root/worktree files, state, events, marker, index,
  branch, or HEAD.
- REQ-008: Dry-run creates no ownership marker.
- REQ-009: Dry-run creates no worktree.
- REQ-010: Dry-run invokes no Codex, review, validation, push, or GitHub API.
- REQ-011: Completed and failed worktrees are reported distinctly.
- REQ-012: Dry-run and delivery use one read-only inspection function.
- REQ-013: A marker is created only at a newly registered isolated worktree root.
- REQ-014: Marker creation never targets the parent repository root.
- REQ-015: Marker creation verifies the target is a registered linked worktree.
- REQ-016: Marker creation rejects a target equal to the repository root.
- REQ-017: A root marker is reported for human action and never auto-deleted.
- REQ-018: Cleanup handles only the isolated worktree marker.
- REQ-019: Dry-run and delivery share one read-only root safe-start inspection
  covering protected/detached branches, dirty tracked or untracked files,
  unmerged paths, and in-progress merge/rebase/cherry-pick operations.
- REQ-020: Existing-worktree output reports normalized expected/saved paths and
  `worktree_path_match`; a mismatch or nonexistent saved path blocks resume.

## Acceptance criteria

- [x] AC-001: Missing, failed, and completed worktree dry-runs have distinct actions.
- [x] AC-002: Every required inspection field is present and fail-closed.
- [x] AC-003: Filesystem, Git, state, and event snapshots are identical before/after dry-run.
- [x] AC-004: Root marker creation is rejected and linked-worktree marker creation succeeds.
- [x] AC-005: Delivery and dry-run resume eligibility are identical.
- [x] AC-006: Existing framework, application, integration, and build validation pass.
- [x] AC-007: Dry-run and delivery accept or reject the same root start state.
- [x] AC-008: Normalized saved worktree path matching is structured and fail-closed.

## Clarifications

- Risk is high because `infrastructure` worktree ownership and resume controls are
  safety boundaries; auto merge remains disabled.
- Root-marker investigation found no root marker at specification time. The only
  marker present is the existing Feature 001 linked-worktree marker, created on
  2026-07-12 at 16:24:28 +0900 with content `001-project-crud`.
- There is no evidence that dry-run created a root marker. Earlier unlabeled
  sequential status output likely attributed the linked-worktree marker to root.
- Even so, root contamination must be mechanically rejected and reported.
- The previous repair cycle stopped after five review loops. Human approval starts
  a new cycle limited to shared safe-start inspection and worktree path output.
- Template-port review found that spec/scope review could not assess files
  assigned to other shards and displayed worktree paths remained raw despite
  normalized matching. Human approval starts a bounded repair cycle limited to
  complete spec/scope diff input and canonical path output.
- Complete diff visibility in the read-only spec/scope shard is intentional and
  overlaps focused shards so requirements can be traced across the whole change.
  It grants no additional file access, execution, or secret-handling authority.
- For high-risk work, `planned_remote_mutations` is empty until approval;
  `deferred_remote_mutations` names the post-approval push/PR/CI steps and
  `remote_mutation_blocker` identifies the high-risk pre-push gate.
- Saved worktree identity requires the absolute lexical managed path itself,
  not an external symlink alias that happens to resolve to it. Normalized paths
  remain output evidence, while raw-path mismatch fails closed.

## Scope

Allowed: `scripts/agent/delivery.py`, `scripts/agent/worktree.py`,
`scripts/agent/work.py`, `scripts/agent/git_utils.py`, `scripts/agent/review.py`, `tests/**`, `README.md`,
`docs/**`, and this feature directory. Feature 001 application/spec/runtime
evidence and CI are forbidden.
