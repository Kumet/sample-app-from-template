# Implementation plan: Project CRUD

## Status

Approved

## Summary

Extend the bootstrap FastAPI package with Project CRUD using a layered design:
FastAPI routes and schemas call an application service, the service depends on
a repository protocol, and a SQLAlchemy repository implements that protocol
over separately defined ORM models and SQLite infrastructure. Add isolated unit
and integration coverage, retain health behavior, and update only the approved
architecture and developer documentation.

## Risk classification

This is a high-risk feature under repository policy because it introduces an
SQLite schema and declares the `migration` risk domain. Autonomous delivery may
implement and validate in its isolated worktree, but must honor the high-risk
approval gate and must not disguise the domain as infrastructure or bypass a
pre-push stop.

## Existing code investigation

- `src/project_board/main.py` currently creates a single FastAPI app and defines
  the pure `/health` handler directly.
- There is no domain, application, repository, or database package yet.
- Application tests are separated into `tests/app/unit` and
  `tests/app/integration`; pytest is restricted to `tests/app`.
- Ruff includes all Python under `src/**` and `tests/app/**`; strict mypy covers
  all of `src`.
- `make test` runs 47 unchanged framework tests plus all app tests;
  `make integration-test`, build, and `make validate` are already real gates.
- The only current runtime dependencies are FastAPI and Uvicorn. SQLAlchemy is
  not installed and is the sole dependency addition approved here.

## Affected files

| File | Change | Risk |
|---|---|---|
| `pyproject.toml` | Add a bounded SQLAlchemy 2.x runtime dependency. | Medium |
| `src/project_board/main.py` | Compose the API router and database-backed application without changing health behavior. | Medium |
| `src/project_board/api/**` | Add request/response schemas, service dependency wiring, routes, and sanitized HTTP error mapping. | Medium |
| `src/project_board/application/**` | Add Project use-case orchestration against the repository interface. | Medium |
| `src/project_board/domain/**` | Add framework-independent Project validation and domain errors. | Medium |
| `src/project_board/repositories/**` | Add the repository protocol and SQLAlchemy implementation with transaction handling. | Medium |
| `src/project_board/infrastructure/**` | Add engine/session factories, explicit schema initialization, and a separate ORM model. | Medium |
| `tests/app/unit/**` | Test domain and service behavior with repository stubs. | Low |
| `tests/app/integration/**` | Test per-test temporary SQLite repository/API CRUD, validation, rollback, ordering, and health. | Medium |
| `README.md` | Document schema initialization, local database behavior, and Project API usage. | Low |
| `docs/architecture.md` | Record implemented Project-layer boundaries and remaining intended layers. | Low |
| `specs/001-project-crud/**` | Record the approved contract and autonomous delivery evidence. | Low |

## Design

### Composition and dependency direction

Use package boundaries matching the approved architecture:

```text
FastAPI router / Pydantic schemas
             |
             v
    Project application service
             |
             v
     ProjectRepository protocol
             ^
             |
SQLAlchemyProjectRepository -> SQLAlchemy model/session -> SQLite

Domain Project and domain errors have no FastAPI or SQLAlchemy imports.
```

`main.py` remains the composition root. It creates or imports a FastAPI app,
includes the Project router, and preserves `/health`. A testable application
factory may accept database configuration or a session factory so each test can
use its own temporary SQLite database. The default development app uses a local
SQLite file documented in README and invokes the explicit initialization
function during application startup/lifespan, never merely from module import.

### Domain

Represent Project independently of persistence. Centralize name and description
normalization and length checks in domain construction/update helpers. Use
timezone-aware UTC values. Define `ProjectValidationError`, `ProjectNotFound`,
and `RepositoryError` without importing delivery or persistence frameworks.

### Persistence and transactions

Use SQLAlchemy 2.x typed declarative mappings in infrastructure, distinct from
the domain Project. Provide engine/session factory functions and
`initialize_schema(engine)` for explicit development/test schema creation.

The SQLAlchemy repository converts between ORM and domain objects and is the
only layer that executes database queries. Create, update, and delete operations
commit on success. Any SQLAlchemy/database failure rolls back before raising a
sanitized `RepositoryError`. Reads do not commit. SQLite-loaded timestamps are
normalized back to timezone-aware UTC if the driver drops timezone metadata.

### Application service

The service implements create/list/get/update/delete use cases against the
repository protocol. It translates a missing repository result into
`ProjectNotFound` and delegates validation to the domain. It contains no
FastAPI, SQLAlchemy, engine, or session imports.

### API

Pydantic schemas validate shapes and maximum lengths and normalize whitespace
consistently with domain rules. PATCH inspects explicitly supplied fields and
rejects an empty patch. Routes call only the service. Dependency functions own
request-scoped session/repository/service construction and close sessions.

Map `ProjectNotFound` to 404, request/domain validation to 422, and
`RepositoryError` to a generic 500 response. DELETE returns a framework-native
empty 204 response.

## Data model impact

Create one SQLite `projects` table:

- `id`: integer primary key, database generated.
- `name`: non-null string up to 100 characters.
- `description`: nullable text up to 1000 characters.
- `created_at`: non-null timezone-aware UTC timestamp.
- `updated_at`: non-null timezone-aware UTC timestamp.

No Task foreign key, soft-delete column, migration history, or additional table
is introduced. Schema creation uses SQLAlchemy metadata only for development and
tests; production migration policy remains undefined and out of scope.

## API impact

Add:

- `POST /api/projects` → 201 Project response.
- `GET /api/projects` → 200 ordered Project list.
- `GET /api/projects/{project_id}` → 200 or 404.
- `PATCH /api/projects/{project_id}` → 200 updated Project or 404.
- `DELETE /api/projects/{project_id}` → 204 empty response or 404.

Keep `GET /health` unchanged. Invalid path/request/body/domain input returns 422
through FastAPI/Pydantic or an explicit sanitized handler.

## UI impact

None. No HTML, templates, static assets, HTMX, JavaScript, or Project Web UI.

## Test strategy

- Unit tests: Project creation/update normalization and validation; service
  create/list/get/update/delete with a repository stub; not-found behavior; and
  repository error propagation without swallowing or partial service state.
- Integration repository tests: create a new temporary SQLite database per
  test, explicitly initialize schema, perform CRUD and ordering, verify
  timezone-aware UTC round trips, and force a write failure to verify rollback.
- Integration API tests: construct the app against a new temporary database per
  test and cover 201/200/204, 404, 422, trimming, PATCH semantics, ordering,
  deletion, generic 500 sanitization, and `/health` regression.
- Regression tests: retain all existing framework and bootstrap application
  tests unchanged unless app factory composition requires a minimal in-scope
  adaptation under `tests/app/**`.
- Full validation: named unit/integration gates, build, and `make validate`.

## Security considerations

- Use local SQLite only; no external network or external database driver.
- Never include raw SQLAlchemy exceptions, SQL text, database paths, or
  connection details in API error bodies.
- Tests use synthetic values and independent temporary paths; they never touch
  the development database.
- Do not read secrets, `.env`, credentials, tokens, production configuration,
  or GitHub Secrets.
- Do not change CI, Makefile, repository policy, authentication, or deployment.

## Rollback strategy

Revert the feature commits through a normal PR. Before production use there is
no supported data migration contract; developers may remove the explicitly
documented local development database after stopping the app. No automated
destructive cleanup is introduced.

## Open questions

None. Production schema evolution, Project/Task deletion interaction, UI, CLI,
and pagination remain deliberately deferred to later approved specifications.
