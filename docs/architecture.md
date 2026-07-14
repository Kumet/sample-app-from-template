# Architecture

## Status

Local Project Board implements Project CRUD and nested Task CRUD through
FastAPI, application services and repository abstractions, and SQLAlchemy 2.x
repositories over local SQLite. Task lists include bounded filtering,
pagination, and deterministic sorting, and Projects with Tasks are protected
from deletion. The health endpoint remains independent of persistence. Tag
behavior, web UI, CLI, import/export, backup/restore, and production migration
policy remain future work.

## System overview

The application is expected to use a layered architecture in which the web UI,
REST API, and CLI share the same application service and domain logic. SQLite
provides local persistence. The user-facing web interface is rendered from
templates and enhanced only where useful with HTMX or small JavaScript modules.

The current runtime surface is composed in `project_board.main`. It creates the
FastAPI application, preserves `GET /health`, installs the Project and nested
Task routes, and wires a SQLite session factory into request-scoped
dependencies.

```text
FastAPI Project and Task routes / Pydantic schemas
                         |
                         v
           ProjectService / TaskService
                         |
                         v
 ProjectRepository / TaskRepository protocols
                         ^
                         |
        SQLAlchemy repository implementations
                         |
       separate ORM models / session / SQLite
```

Dependencies point inward. The API calls `ProjectService` and `TaskService` and
never executes SQL, owns transactions, or uses ORM models. Services depend on
repository protocols, not SQLAlchemy implementations. Domain Project and Task
objects, enums, datetime rules, and errors have no FastAPI, SQLAlchemy, or
SQLite dependency, and ORM models remain separate persistence types.

## Implemented application layers

### API layer

`project_board.api` contains Pydantic request/response schemas, Project routes,
nested Task routes, list-query validation, and dependency construction. Each
request receives its own SQLAlchemy session; dependencies construct the needed
repositories and service, then reliably close the session. Routes call only
service use cases. They map missing resources to 404, Project deletion conflicts
to 409, validation errors to 422, and repository failures to a generic sanitized
500 response.

### Application service layer

`project_board.application` coordinates create, list, retrieve, partial update,
and physical deletion for Projects and Tasks. `TaskService` validates that the
parent Project exists, preserves omitted update fields, supports explicit null
for optional fields, and enforces nested ownership through the Task repository.
The services turn missing results into stable domain errors and have no FastAPI,
SQLAlchemy, engine, or session dependency.

### Domain layer

`project_board.domain` owns persistence-independent Project and Task values,
Task status and priority enums, normalization and length rules, and centralized
timezone-aware UTC normalization. It also defines stable validation, not-found,
Project-has-Tasks conflict, and repository errors. Tag and user-facing timezone
presentation rules remain unimplemented.

### Repository layer

`project_board.repositories` defines the `ProjectRepository` and
`TaskRepository` protocols plus separate SQLAlchemy implementations. Concrete
repositories are the only layer that queries, commits, or rolls back
persistence. They map between ORM and domain types, physically delete rows, and
convert unexpected database failures into a sanitized `RepositoryError` after
rollback so the caller-owned session remains reusable.

The Task repository scopes every lookup and mutation by both Project and Task
ID. Its single list query applies exact status/priority and strict due-date
filters, enforces a maximum page size of 100, and avoids per-row Project loads.
Allow-listed sort expressions implement semantic priority order, due-date nulls
last in either direction, and ascending Task ID as the stable tie-breaker.

Project deletion checks for an owned Task in the same write transaction. If one
exists, the repository rolls back and raises a stable conflict without deleting
either record. There is no Task cascade; after Tasks are explicitly deleted,
normal Project deletion can proceed.

### SQLite infrastructure

`project_board.infrastructure` owns the SQLAlchemy declarative base, distinct
Project and Task ORM models, SQLite engine and session factories, and
`initialize_schema(engine)`. Every SQLite connection enables foreign-key
enforcement. Task storage has a non-cascading foreign key to Projects and
indexes on `project_id`, `(project_id, status)`, `(project_id, priority)`, and
`(project_id, due_at)`.

Merely importing modules or constructing an engine does not create schema. The
default development app explicitly initializes `project_board.sqlite3` during
application startup. SQLAlchemy metadata creates missing development/test
tables and indexes without dropping existing Project rows. This is not a
versioned production migration mechanism; production schema upgrades remain an
explicitly unresolved risk and require a separate approved feature. No migration
dependency is present.

## Test isolation and health

Unit and integration coverage exercises domain and service rules, schema and
foreign-key behavior, repository CRUD/list ordering, rollback and reusable
sessions, API validation and ownership isolation, persistence across restart,
import isolation, Project CRUD regression, and health regression. Integration
tests create fresh SQLite files beneath pytest temporary directories, explicitly
initialize schema, and inject the corresponding session factory. They never
connect to the default development database. Engines and sessions are disposed
or closed after use.

`GET /health` still returns HTTP 200 with `{"status":"ok"}`. The handler does
not consult the database or any external service.

## Intended future layers

The web UI and CLI will be separate delivery adapters over the same application
service and domain layers. Jinja2/templates, HTMX or small JavaScript modules,
Tag persistence, and local import/export and backup/restore require their own
approved specifications. Future adapters must not create parallel business
logic or persistence paths.

### Templates/static assets

Jinja2 templates and static assets are intended to render the web UI. HTMX or a
small amount of JavaScript may enhance interactions. Presentation code must call
the Web/API boundary and shared services rather than recreate domain rules.

## Dependency direction

The dependency direction is from the outside toward the domain:

```text
FastAPI API -> ProjectService / TaskService -> repository protocols -> Domain
                                                  ^
                                                  |
                              SQLAlchemy repositories -> ORM / SQLite
```

Future Web UI and CLI adapters will enter through application services. They
must not access SQLAlchemy sessions or ORM models directly.

## Cross-cutting constraints

- Web UI, REST API, and CLI operate on the same data through shared service and
  domain layers.
- Dates and times are stored and processed internally in UTC; presentation
  timezone behavior remains specification-required.
- Failed imports leave existing data unchanged, and exported data is importable.
- Complete Task bodies are not logged unconditionally or sent externally.
- No layer reads secrets or production configuration for application behavior.
- Authentication, billing, external services, production deployment, and other
  stated out-of-scope capabilities are not part of this design.

## Development automation boundary

The repository retains its specification-driven automation framework. Approved
feature contracts under `specs/` drive bounded task execution, validation,
evidence logging, review, and optional PR/CI delivery. That automation is a
development tool around the application, not an application runtime layer.
