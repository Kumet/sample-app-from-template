# Feature specification: Project CRUD

## Status

Approved

## Background

Local Project Board currently exposes only a dependency-free health endpoint.
The first product capability is persistent Project management through a REST
API. This feature introduces the minimum domain, application service,
repository abstraction, SQLAlchemy repository, and SQLite infrastructure needed
for Project CRUD while preserving the existing health endpoint and quality
gates.

This specification and all clarifications below are explicitly human-approved.
Implementation may proceed without further approval while it remains within the
declared scope.

The feature is classified high-risk because it creates a new SQLite schema and
retains the repository policy risk domain `migration`. High-risk delivery gates
must not be bypassed; a policy stop before push is an expected safe outcome.

## Goals

- Persist Projects in a local SQLite database through SQLAlchemy 2.x.
- Expose create, list, retrieve, partial update, and physical deletion under
  `/api/projects`.
- Keep API, application service, domain, repository, and infrastructure
  responsibilities separate and dependencies pointing inward.
- Provide explicit development/test schema initialization and isolated test
  databases.
- Preserve `GET /health` and all existing validation gates.

## Non-goals

- Task or Tag models and behavior.
- Kanban UI, Project Web UI, templates, static assets, or browser interactions.
- CLI, import/export, backup, or restore.
- Pagination or caller-selected sorting.
- Soft deletion.
- Alembic, production migrations, production databases, or deployment.
- Authentication, authorization, billing, or external APIs.
- Docker or Kubernetes.

## Users

- Developers building Local Project Board features on a stable Project API.
- Local API clients managing Projects.
- AI agents implementing later approved features through the shared layers.

## Requirements

### Functional requirements

- REQ-001: Development and test environments can explicitly initialize the SQLite schema.
- REQ-002: Project has `id`, `name`, `description`, `created_at`, and `updated_at`.
- REQ-003: Project name is required and contains 1 to 100 characters after trimming leading and trailing whitespace.
- REQ-004: Project description is optional and at most 1000 characters when provided.
- REQ-005: A Project can be created.
- REQ-006: Projects can be listed in ascending `created_at` order, with ascending `id` as the tie-breaker.
- REQ-007: A Project can be retrieved by integer ID.
- REQ-008: Project `name` and `description` can be partially updated through PATCH, with at least one field required.
- REQ-009: A Project can be physically deleted.
- REQ-010: Retrieving, updating, or deleting a nonexistent Project returns HTTP 404.
- REQ-011: Invalid request input returns HTTP 422.
- REQ-012: Successful deletion returns HTTP 204 with no response body.
- REQ-013: All database operations are separated into the repository layer.
- REQ-014: The API layer uses the application service and never accesses SQLAlchemy directly.
- REQ-015: Dates and times are stored and returned as timezone-aware UTC values.
- REQ-016: Database errors roll back the transaction and never commit incomplete changes.
- REQ-017: Every test uses an independent test database and never changes the development database.
- REQ-018: Existing `GET /health` behavior remains HTTP 200 with `{"status":"ok"}`.
- REQ-019: Unit and integration tests cover the principal domain, service, repository, and API behavior.
- REQ-020: `make validate` succeeds without weakening existing gates or tests.

### Non-functional requirements

- Use SQLite through Python's standard-library driver and SQLAlchemy 2.x only.
- Add no runtime dependency other than SQLAlchemy.
- The domain layer does not import FastAPI, SQLAlchemy, or SQLite infrastructure.
- Route functions do not execute SQL, commit sessions, or use ORM models.
- The domain Project is not the SQLAlchemy model.
- Application services depend on a repository interface, not a concrete
  SQLAlchemy repository.
- Repository failures expose a stable `RepositoryError`; API error responses do
  not disclose SQL, database paths, credentials, secrets, or internals.
- Tests use no external network, shared global database, or sleep-based synchronization.

## Acceptance criteria

- [ ] AC-001: An empty SQLite database can have its schema explicitly initialized.
- [ ] AC-002: `POST /api/projects` returns HTTP 201 and the created Project.
- [ ] AC-003: `GET /api/projects` returns created Projects ordered by ascending `created_at`, then ascending `id`.
- [ ] AC-004: `GET /api/projects/{id}` returns the selected Project.
- [ ] AC-005: `PATCH /api/projects/{id}` returns the partially updated Project.
- [ ] AC-006: `DELETE /api/projects/{id}` returns HTTP 204 with no response body.
- [ ] AC-007: Retrieving a deleted Project returns HTTP 404.
- [ ] AC-008: An empty or whitespace-only name returns HTTP 422.
- [ ] AC-009: A name of 101 or more characters returns HTTP 422.
- [ ] AC-010: A description of 1001 or more characters returns HTTP 422.
- [ ] AC-011: GET, PATCH, and DELETE for a nonexistent ID return HTTP 404.
- [ ] AC-012: A SQLite integration test completes a CRUD round trip.
- [ ] AC-013: A database operation failure rolls back its transaction.
- [ ] AC-014: `GET /health` continues to return HTTP 200 and `{"status":"ok"}`.
- [ ] AC-015: Unit tests, integration tests, package build, and `make validate` succeed.
- [ ] AC-016: API, application service, domain, repository, and database infrastructure are structurally separate.
- [ ] AC-017: API routes do not directly access a SQLAlchemy session or model.
- [ ] AC-018: Implementation and tests remain within the allowed scope.

## Clarifications

| Question | Approved answer | Date |
|---|---|---|
| Maximum Project name length | 100 characters after trimming. | 2026-07-12 |
| Maximum Project description length | 1000 characters after trimming. | 2026-07-12 |
| Name whitespace handling | Trim leading and trailing whitespace; reject the result if empty. | 2026-07-12 |
| Description whitespace handling | Trim leading and trailing whitespace. Normalize an empty trimmed description to `null` consistently across create and update. | 2026-07-12 |
| List ordering | Ascending `created_at`; use ascending `id` when timestamps are equal. | 2026-07-12 |
| Delete behavior | Physical deletion. | 2026-07-12 |
| Successful DELETE response | HTTP 204 No Content with no body. | 2026-07-12 |
| Pagination | Out of scope for this feature. | 2026-07-12 |
| Database | SQLite. | 2026-07-12 |
| ORM | SQLAlchemy 2.x. | 2026-07-12 |
| Schema initialization | Provide an explicit function for development and tests; do not initialize implicitly on import. | 2026-07-12 |
| Alembic | Do not add it; production migrations are out of scope. | 2026-07-12 |
| Dates and times | Timezone-aware UTC for domain values and API responses. Persistence must restore UTC awareness even if SQLite loses timezone metadata. | 2026-07-12 |
| API prefix | `/api`. | 2026-07-12 |
| Project ID | SQLite integer primary key. | 2026-07-12 |
| Update method | PATCH partial update with at least one of `name` or `description` explicitly supplied. Explicit `description: null` clears the description. | 2026-07-12 |
| Task relationship | Ignore Task relationships because Task is not implemented in this feature. | 2026-07-12 |
| Domain errors | Define `ProjectNotFound`, `ProjectValidationError`, and `RepositoryError`. | 2026-07-12 |
| HTTP error mapping | `ProjectNotFound` → 404; request validation → 422; unexpected `RepositoryError` → generic 500. | 2026-07-12 |
| Delivery risk | High. The initial medium declaration conflicted with repository policy because `migration` is a high-risk domain; the human approved changing only the declared risk to high and retaining `risk_domains = ["migration"]`. | 2026-07-12 |

No material ambiguity remains. A need to alter these decisions, introduce a
different migration policy, or expand the declared scope is human-required.

## API contract

### Endpoints

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{project_id}
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
```

### Create request

```json
{
  "name": "Sample project",
  "description": "Project description"
}
```

### Update request

At least one field must be explicitly present.

```json
{
  "name": "Updated project",
  "description": "Updated description"
}
```

### Project response

```json
{
  "id": 1,
  "name": "Sample project",
  "description": "Project description",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

## Error handling

- `ProjectValidationError` represents domain input invalidity and must not carry
  infrastructure details.
- `ProjectNotFound` represents a missing integer Project ID.
- `RepositoryError` wraps unexpected persistence failures after rollback.
- FastAPI/Pydantic request validation and domain validation are converted to 422.
- API 500 responses use a generic message and never expose database exception
  text, SQL, local paths, credentials, or secrets.

## Scope

### Allowed changes

- `pyproject.toml`
- `src/project_board/**`
- `tests/app/**`
- `README.md`
- `docs/architecture.md`
- `specs/001-project-crud/**`

### Forbidden changes

- `.env`, `.env.*`, `**/.env`, and `**/.env.*`
- `local.properties`
- `**/*.pem` and `**/*.key`
- `**/credentials.*` and `**/secrets.*`
- `.github/**`
- `.agent-policy.toml`
- `Makefile`
- Existing framework tests outside `tests/app/**`
- Production configuration or deployment files

## Security and privacy

Project data remains local in user-selected SQLite storage. This feature does
not introduce authentication, personal information, secrets, external services,
or telemetry. Tests use temporary SQLite databases and synthetic data only.
Exceptions crossing the API boundary are sanitized so database internals and
filesystem paths are not returned to clients.
