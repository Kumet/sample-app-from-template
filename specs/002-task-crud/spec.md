# Feature specification: Task CRUD

## Status

Approved

The contract in this document is fixed by the human request dated 2026-07-14.
Implementation and delivery remain separately human-required and are not
authorized by this specification-only change.

## Background

Feature 001 introduced layered Project CRUD backed by SQLite and SQLAlchemy.
Feature 002 adds Tasks that always belong to one Project, including nested REST
CRUD, deterministic filtered lists, foreign-key integrity, and a protected
Project deletion rule. The implementation must extend the existing domain,
application, repository, infrastructure, and API boundaries without introducing
a migration framework or weakening the delivery gates.

## Goals

- Persist Task records under existing Projects.
- Provide create, list, detail, partial update, and physical deletion APIs.
- Enforce Project ownership, UTC timestamps, foreign keys, rollback, and
  deterministic list behavior.
- Reject deletion of a Project that still owns Tasks.
- Preserve Project CRUD, `/health`, architecture boundaries, and quality gates.

## Non-goals

- Moving a Task to another Project.
- Assignees, users, authentication, comments, labels, tags, attachments,
  recurring Tasks, notifications, or soft deletion.
- Bulk operations, frontend UI, CLI, import/export, or backup/restore.
- A new migration framework, production migration, deployment, Docker, or
  Kubernetes.
- Implicit or explicit cascade deletion of Tasks when a Project is deleted.

## Requirements

### Functional requirements

- REQ-001: Task uses an immutable SQLite integer primary key and has immutable
  integer `project_id`, required trimmed `title`, nullable `description`,
  required `status`, required `priority`, nullable `due_at`, and server-generated
  `created_at` and `updated_at`.
- REQ-002: `title` is 1 to 200 characters after trimming; `description` is at
  most 2000 characters after trimming, and an empty trimmed description is
  normalized to `null`.
- REQ-003: Task status is exactly `todo`, `in_progress`, or `done`, defaulting to
  `todo`; priority is exactly `low`, `medium`, or `high`, defaulting to `medium`.
- REQ-004: `due_at`, `due_before`, and `due_after` accept only timezone-aware
  ISO 8601 values, reject naive values with 422, and normalize to UTC.
- REQ-005: `POST /api/projects/{project_id}/tasks` creates a Task with HTTP 201,
  takes `project_id` only from the path, and returns 404 when the Project is absent.
- REQ-006: Nested detail lookup returns a Task only when both Project and Task
  exist and ownership matches; a missing Project, missing Task, or ownership
  mismatch returns 404 without disclosing the Task's actual owner.
- REQ-007: PATCH updates only supplied mutable fields. Explicit `description:
  null` and `due_at: null` clear those fields; omitted fields remain unchanged;
  `title`, `status`, and `priority` reject null; immutable fields are forbidden.
- REQ-008: An empty PATCH body returns 422, matching the existing Project PATCH
  convention, and does not change `updated_at` or any persisted value.
- REQ-009: A successful Task DELETE physically deletes only the selected Task
  and returns HTTP 204 with no body; missing or mismatched Tasks return 404.
- REQ-010: Task list supports exact `status` and `priority` filters and strict
  `due_before` (`due_at < value`) and `due_after` (`due_at > value`) filters.
- REQ-011: Task list supports `limit` 1..100 (default 50) and `offset` >= 0
  (default 0); invalid query values return 422.
- REQ-012: Task list supports `sort` values `created_at`, `updated_at`, `due_at`,
  and `priority`, plus `order` values `asc` and `desc`; defaults are
  `created_at` and `asc`.
- REQ-013: List ordering is deterministic: equal primary sort values use
  ascending Task ID; due-date nulls are last for both directions; priority uses
  semantic order `low < medium < high` and reverses for descending order.
- REQ-014: A Project with one or more Tasks cannot be deleted and returns HTTP
  409; neither Project nor Task is changed. After all Tasks are explicitly
  deleted, Project deletion succeeds normally.
- REQ-015: SQLite foreign-key enforcement prevents orphan Tasks, and Task
  deletion is never an implicit consequence of Project deletion.
- REQ-016: Create, update, and delete commit only on success. Repository failure
  rolls back all partial work and leaves the caller-owned session reusable.
- REQ-017: `updated_at` changes only after a successful non-empty update;
  validation failure, empty PATCH, not-found, conflict, or rollback leaves it
  unchanged. All stored and domain timestamps are timezone-aware UTC.
- REQ-018: Task domain/entity and repository interface remain independent of
  FastAPI and SQLAlchemy; application imports do not eagerly load infrastructure,
  and repository package roots do not eagerly export concrete implementations.
- REQ-019: API handlers call application services and contain no SQL, ORM model,
  commit, rollback, or transaction ownership logic.
- REQ-020: Explicit schema initialization adds a `tasks` table with indexes on
  `project_id`, `(project_id, status)`, `(project_id, priority)`, and
  `(project_id, due_at)` while preserving existing Project data.
- REQ-021: No migration dependency is introduced. SQLAlchemy metadata-based
  explicit initialization creates missing development/test tables; production
  migration remains unresolved and out of scope.
- REQ-022: All persistence queries use SQLAlchemy parameter binding, list
  queries are bounded to 100 records, avoid N+1 behavior, and return deterministic
  results.
- REQ-023: Errors preserve the existing `{"detail": ...}` response shape: 404
  for missing/mismatched resources, 409 for Project-with-Tasks conflict, 422 for
  request/query validation, and a generic sanitized 500 for repository failure.
- REQ-024: Unit, application, integration, import-isolation, rollback,
  persistence-restart, Project CRUD regression, and `/health` regression tests
  cover this contract using isolated temporary SQLite databases.
- REQ-025: `make validate` succeeds without changing framework code, policy,
  CI, review budgets, or quality gates.

### Non-functional requirements

- Centralize UTC normalization rather than duplicating conversions across API,
  service, and repository code.
- Keep enum values consistent across domain, API schemas, database persistence,
  filters, and sorting.
- Do not log Task descriptions or expose SQL, filesystem paths, exception text,
  credentials, tokens, or secrets.
- Use no external network and no test-only branch in production code.

## Acceptance criteria

- [ ] AC-001: Explicit initialization creates `projects` and `tasks` in an empty
  SQLite database and preserves existing Project rows when adding `tasks`.
- [ ] AC-002: Task schema has the required columns, foreign key, non-null rules,
  and four required index shapes.
- [ ] AC-003: POST returns 201 with integer IDs, defaults, and UTC `Z` timestamps.
- [ ] AC-004: POST accepts all optional fields and normalizes aware `due_at` to UTC.
- [ ] AC-005: POST for a missing Project returns 404 and creates no Task.
- [ ] AC-006: Empty/blank/201-character titles and 2001-character descriptions
  return 422; accepted text is trimmed consistently.
- [ ] AC-007: Every allowed status and priority is accepted; invalid values and
  null required values return 422.
- [ ] AC-008: Naive due dates and due filters return 422; aware values round-trip
  as UTC ending in `Z`.
- [ ] AC-009: Detail returns the owned Task; missing Project, missing Task, and
  cross-Project lookup return the same 404 shape.
- [ ] AC-010: PATCH updates supplied fields, preserves omitted fields, and clears
  description/due date when explicitly null.
- [ ] AC-011: Empty PATCH and immutable-field input return 422 and leave all
  fields including `updated_at` unchanged.
- [ ] AC-012: Successful DELETE returns 204 with no body; missing or mismatched
  deletion returns 404.
- [ ] AC-013: Status, priority, due-before, and due-after filters return only
  matching Tasks from the path Project.
- [ ] AC-014: Pagination defaults and boundaries work, and invalid limit/offset
  values return 422.
- [ ] AC-015: Every supported sort/order is deterministic, priorities use
  semantic order, null due dates are last, and IDs break ties ascending.
- [ ] AC-016: A Project with Tasks returns 409 on DELETE and both records remain;
  deleting Tasks first permits Project deletion.
- [ ] AC-017: Foreign keys are enabled and an orphan Task cannot be persisted.
- [ ] AC-018: Forced create/update/delete failures roll back; the same session can
  subsequently perform a valid operation.
- [ ] AC-019: Application and repository-interface imports do not load SQLAlchemy
  infrastructure or the concrete Task repository.
- [ ] AC-020: Routes use services, services use repository interfaces, and ORM
  models remain separate from domain entities.
- [ ] AC-021: Repository/API failures return sanitized errors without partial data.
- [ ] AC-022: A restart against the same temporary SQLite file preserves Project
  and Task data.
- [ ] AC-023: Project→Task create→get→patch→list→delete round trip succeeds, and
  Tasks remain isolated between Projects.
- [ ] AC-024: Existing Project CRUD and `GET /health` regressions pass unchanged.
- [ ] AC-025: Unit/app/integration tests, build, and `make validate` pass within
  the approved scope.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| Task and Project ID type | SQLite-generated integer primary keys; nested path IDs are integers. | Existing Project implementation |
| API prefix | Full endpoints are under `/api/projects/{project_id}/tasks`. | Existing `/api` router convention |
| Error response shape | FastAPI JSON `{"detail": ...}`; Task 404 uses `Task not found`, missing Project uses `Project not found`, and ownership mismatch uses `Task not found`. | Existing API convention and non-disclosure rule |
| DELETE success | HTTP 204 No Content with an empty body. | Existing Project DELETE |
| UTC serialization | Pydantic/FastAPI ISO 8601 UTC with a trailing `Z`; SQLite-loaded naive values regain UTC awareness centrally. | Existing response and repository tests |
| Empty PATCH | HTTP 422; no persisted value or `updated_at` changes. | Existing Project PATCH convention |
| Description whitespace | Trim; normalize an empty trimmed value to `null`; explicit null clears it. | Existing Project normalization |
| due filter boundaries | Strictly earlier/later (`<` and `>`), excluding null due dates. | Meaning of `before`/`after` fixed here |
| Stable tie-breaker | Task ID ascending regardless of requested primary sort direction. | Deterministic contract |
| Project deletion | 409 while Tasks exist; no cascade; succeeds after explicit Task deletion. | Human-approved Feature 002 rule |
| Foreign-key enforcement | Enable SQLite `PRAGMA foreign_keys=ON` for every application connection. | Required orphan prevention |
| Transaction owner | Concrete SQLAlchemy repositories commit successful writes and roll back failures on the caller-owned request session. | Existing Project repository |
| Migration | Extend metadata and explicit `initialize_schema`; do not add Alembic. Existing Project rows must survive. | Existing initialization policy |
| Domain status naming | Feature 002 uses `in_progress` exactly; this approved feature contract supersedes the earlier contextual placeholder `doing`. | Human-approved request |

No material ambiguity remains. Changing these decisions, introducing a formal
migration framework, or expanding scope requires new human approval.

## API contract

```text
POST   /api/projects/{project_id}/tasks
GET    /api/projects/{project_id}/tasks
GET    /api/projects/{project_id}/tasks/{task_id}
PATCH  /api/projects/{project_id}/tasks/{task_id}
DELETE /api/projects/{project_id}/tasks/{task_id}
```

Create accepts `title` and optional `description`, `status`, `priority`, and
`due_at`. Update accepts at least one of those mutable fields. Both request
schemas forbid extra fields, including `id`, `project_id`, `created_at`, and
`updated_at`.

Task responses contain:

```json
{
  "id": 1,
  "project_id": 1,
  "title": "Implement Task CRUD",
  "description": null,
  "status": "todo",
  "priority": "medium",
  "due_at": "2026-07-31T00:00:00Z",
  "created_at": "2026-07-14T00:00:00Z",
  "updated_at": "2026-07-14T00:00:00Z"
}
```

## Scope

### Allowed changes

- `src/project_board/**`
- `tests/app/**`
- `README.md`
- `docs/architecture.md`
- `specs/002-task-crud/**`

### Forbidden changes

- `.github/**`, `.agent-policy.toml`, `Makefile`, and `pyproject.toml`
- `scripts/agent/**`, `prompts/**`, and framework tests outside `tests/app/**`
- `specs/001-project-crud/**`, `specs/012/**`, and `specs/013/**`
- `.agent-work/**`, `.agent-worktrees/**`, and `.agent-worktree-owned`
- `.env`, `.env.*`, `**/.env`, `**/.env.*`, credentials, secrets, keys, tokens,
  and production configuration

## Security and privacy

Task data stays in explicitly configured local SQLite storage. The feature adds
no external communication, authentication, personal information, telemetry, or
secret access. Errors are sanitized and test data is synthetic.
