# Feature specification: Scope request normalization

## Status

Implemented

## Background

A live template consumer stopped correctly when a build created an out-of-scope
`*.egg-info/` directory. The work runner wrapped the structured scope failure in
another exception and later extracted text by splitting on the first colon. The
resulting event stored an explanatory sentence in `data.path`, so the exact-match
approval command could not approve a safe repository-relative path. The same run
also showed that operators need a supported way to request a newly discovered
remediation path such as `.gitignore` without editing runtime evidence.

## Goals

- Preserve machine-readable paths independently from human-readable errors.
- Support multiple out-of-scope paths without ambiguous string parsing.
- Add dry-run and mutating commands that create, but never approve, an explicit
  human-required scope request.
- Keep old evidence append-only and allow safe recovery from malformed legacy
  scope events.

## Non-goals

- Automatically approving any scope expansion.
- Rewriting or deleting existing state or event records.
- Changing risk classification, remote delivery, or merge behavior.
- Modifying the stopped sample application worktree.

## Users

- Operators recovering safely from an autonomous scope stop.
- Framework maintainers auditing scope evidence and approvals.

## Requirements

### Functional requirements

- REQ-001: Scope validation MUST raise a structured violation containing a human-readable message and an ordered collection of normalized repository-relative paths.
- REQ-002: Scope-request events MUST store path-only machine data, support multiple paths, and MUST NOT derive paths by parsing wrapped error prose.
- REQ-003: Path validation MUST reject empty values, absolute paths, parent traversal, control characters, unsafe globs, and repository-wide patterns.
- REQ-004: Existing valid single-path events MUST remain approvable, while malformed legacy events MUST NOT be treated as safe approval requests.
- REQ-005: Operators MUST be able to preview and append an explicit human-required request for a newly needed scope path without granting approval.
- REQ-006: Explicit requests MUST record feature, path, reason, timestamp through the event schema, and relevant failed-state identity when available.
- REQ-007: Duplicate pending requests, cross-feature approvals, unrequested paths, and path mismatches MUST fail closed.
- REQ-008: A valid explicit request MUST be consumable by the existing approval flow, after which failed work can use the existing contract-safe resume flow.
- REQ-009: Existing events MUST remain append-only; malformed history is diagnosed and a new request is appended rather than migrated in place.
- REQ-010: The CLI and Makefile MUST expose separate dry-run and mutating request-scope operations with no remote side effects.

### Non-functional requirements

- Runtime code remains Python 3.11+ standard-library only.
- Dry-run commands do not mutate files, state, or events.
- Existing scope, validation, delivery, and safety tests remain green.

## Acceptance criteria

- [x] AC-001: Tests prove single and multiple violations retain normalized paths separately from explanatory text through exception wrapping.
- [x] AC-002: Tests prove invalid paths and dangerous globs are rejected before an event or approval is created.
- [x] AC-003: Tests prove valid legacy single-path events work and malformed legacy events never become approvals automatically.
- [x] AC-004: Request dry-run is non-mutating, request apply appends HUMAN_REQUIRED evidence, and neither operation approves scope.
- [x] AC-005: Tests prove duplicate, mismatched, unrequested, and cross-feature operations fail closed.
- [x] AC-006: A newly requested `.gitignore` path can be approved through the normal flow without rewriting the earlier malformed event.
- [x] AC-007: CLI/Make interfaces are documented and the complete `make validate` suite passes.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| Should malformed events be repaired in place? | No. Evidence is append-only; diagnose it and append a new valid request. | 2026-07-12 |
| Does request-scope constitute approval? | No. It only creates a human-required request that must later match approve-scope. | 2026-07-12 |
| How are multiple paths represented? | Canonical events use `data.paths`; `data.path` remains supported for valid legacy single-path events. | 2026-07-12 |
| Is a request allowed while no failed state exists? | No. A remediation request must be bound to the feature's current failed scope state. | 2026-07-12 |

## Scope

### Allowed changes

- `scripts/agent/**`
- `tests/**`
- `Makefile`
- `README.md`
- `docs/**`
- `specs/005-scope-request-normalization/**`

### Forbidden changes

- `.env` and credentials
- GitHub Actions and repository settings
- application repositories created from this template
- automatic approval or bypass of human gates

## Security and privacy

All paths are treated as untrusted input. Scope requests and approvals fail
closed before persistence when path syntax, feature identity, state identity,
or forbidden-path rules are invalid. No secret file is read.
