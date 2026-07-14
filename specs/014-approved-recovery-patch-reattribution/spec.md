# Feature specification: Approved recovery patch re-attribution

## Status

Implemented

## Purpose

Provide a formal, fail-closed path for a human-approved recovery-only patch to
be incorporated into an existing failed delivery worktree without deleting the
worktree, rewriting runtime evidence, or weakening normal resume checks.

## Requirements

- REQ-001: Recovery re-attribution applies only to an existing `failed` state
  for a registered framework-owned isolated worktree whose ownership marker
  names the requested feature.
- REQ-002: The command binds the saved and current HEAD, branch, contract
  digest, worktree path, prior changed paths, current changed paths, approved
  paths, and a canonical recovery diff digest.
- REQ-003: The first version accepts only an unchanged HEAD and an explicit,
  non-empty set of newly added changed paths; committed recovery patches and
  implicit approval of already-saved paths are rejected.
- REQ-004: Every current changed path remains within the approved feature
  contract scope and no requested path may be forbidden or outside that scope.
- REQ-005: Dry-run performs the same inspection as apply, reports all bindings
  and planned mutations, and does not change Git index, HEAD, branch, state,
  events, marker, or worktree files.
- REQ-006: Apply re-inspects immediately before mutation, appends bounded
  `recovery-patch-approved` evidence, updates state through the state API, and
  appends `recovery-patch-applied` evidence.
- REQ-007: The updated state is re-attributed to the verified current HEAD and
  complete current changed-path set while retaining failed task, failure class,
  branch, contract, and worktree identity.
- REQ-008: Normal delivery dry-run and delivery verify the active recovery
  evidence and current diff digest through their shared worktree inspection.
- REQ-009: Any unapproved path, scope violation, changed contract, changed
  branch, ownership failure, worktree mismatch, changed HEAD, or post-approval
  diff mutation fails closed.
- REQ-010: Approval reason and path arguments are validated and evidence data is
  bounded and redacted; secret and runtime paths are never accepted.
- REQ-011: Existing delivery, validation, review, risk, and approval gates are
  not weakened.

## Acceptance criteria

- [x] AC-001: A failed owned worktree with exactly the approved added paths can
  be previewed and formally re-attributed, after which delivery inspection is
  resumable.
- [x] AC-002: Dry-run leaves Git and runtime artifacts byte-for-byte unchanged.
- [x] AC-003: State and two append-only evidence events contain the required
  identity, path, contract, ownership, and digest bindings.
- [x] AC-004: Missing/mismatched ownership, branch, contract, worktree, HEAD,
  paths, scope, or diff digest is rejected.
- [x] AC-005: A post-approval content or index mutation is detected by delivery
  inspection even if its changed-path set is unchanged.
- [x] AC-006: Targeted tests, full validation, and all independent review shards
  pass without weakening existing gates.

## Clarifications

- Risk is high because this feature updates saved delivery state and approval
  evidence used by resume gates.
- `PATHS` is a whitespace-separated list of explicit repository-relative file
  paths, not globs or directories.
- Version one intentionally requires `current HEAD == saved HEAD`. A recovery
  commit must not be created before approval; supporting committed recovery
  history requires a separate specification.
- Approved paths must equal `current changed paths - saved changed paths`.
  Existing saved paths remain governed by the original failed-state evidence.
- The sample repository and Feature 002 worktree, state, and events are out of
  scope and must not be read or changed by implementation or validation.

## Scope

Allowed: recovery approval/reattribution implementation, shared delivery
inspection integration, command and Make targets, framework regression tests,
minimal user documentation, and this feature directory.

Forbidden: sample repository content, Feature 002, runtime state/events and
worktrees in this repository, CI configuration, application source,
credentials, secrets, production configuration, gate weakening, and direct
main changes.
