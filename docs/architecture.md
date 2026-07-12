# Architecture

## Status

Local Project Board implements the first vertical product slice: Project CRUD
through FastAPI, an application service and repository abstraction, and a
SQLAlchemy 2.x repository over local SQLite. The health endpoint remains
independent of persistence. Task and Tag behavior, web UI, CLI, import/export,
backup/restore, and production migration policy remain future work.

## System overview

The application is expected to use a layered architecture in which the web UI,
REST API, and CLI share the same application service and domain logic. SQLite
provides local persistence. The user-facing web interface is rendered from
templates and enhanced only where useful with HTMX or small JavaScript modules.

The current runtime surface is composed in `project_board.main`. It creates the
FastAPI application, preserves `GET /health`, installs the Project API router,
and wires a SQLite session factory into request-scoped dependencies.

```text
FastAPI Project routes / Pydantic schemas
                    |
                    v
          Project application service
                    |
                    v
          ProjectRepository protocol
                    ^
                    |
       SQLAlchemyProjectRepository
                    |
       ORM model / session / SQLite
```

Dependencies point inward. The API calls `ProjectService` and never executes
SQL or uses ORM models. The service depends on the `ProjectRepository` protocol,
not its SQLAlchemy implementation. Domain Project objects and errors have no
FastAPI, SQLAlchemy, or SQLite dependency, and the ORM Project model is a
separate persistence type.

## Implemented Project layers

### API layer

`project_board.api` contains Pydantic request/response schemas, Project routes,
and dependency construction. Each request receives its own SQLAlchemy session;
the dependency constructs a repository and `ProjectService`, then reliably
closes the session. Routes call only service use cases. They map not-found and
validation errors to 404 and 422, and expose repository failures only as a
generic 500 response.

### Application service layer

`project_board.application` coordinates create, list, retrieve, partial update,
and physical deletion use cases. It depends on the repository protocol and
turns missing results into the stable `ProjectNotFound` domain error. It has no
FastAPI, SQLAlchemy, engine, or session dependency.

### Domain layer

`project_board.domain` owns the persistence-independent Project value and its
normalization, length, and UTC timestamp rules. It also defines stable Project
validation, not-found, and repository errors. Task, status, priority, due-date,
Tag, and user-facing timezone rules remain unimplemented.

### Repository layer

`project_board.repositories` defines the `ProjectRepository` protocol and its
SQLAlchemy implementation. This implementation is the only layer that queries,
commits, or rolls back Project persistence. It maps between the ORM model and
domain Project, orders lists by `created_at` and `id`, physically deletes rows,
and converts unexpected database failures into a sanitized `RepositoryError`
after rollback.

### SQLite infrastructure

`project_board.infrastructure` owns the SQLAlchemy declarative base, distinct
Project ORM model, SQLite engine and session factories, and
`initialize_schema(engine)`. Merely importing modules or constructing an engine
does not create schema. The default development app explicitly initializes
`project_board.sqlite3` during application startup. Production migrations,
import/export, and backup/restore are not defined by this feature.

## Test isolation and health

Repository and API integration tests create a fresh SQLite file beneath each
test's pytest temporary directory, explicitly initialize its schema, and inject
the corresponding session factory. They never connect to the default
development database. Engines and sessions are disposed or closed after use.

`GET /health` still returns HTTP 200 with `{"status":"ok"}`. The handler does
not consult the database or any external service.

## Intended future layers

The web UI and CLI will be separate delivery adapters over the same application
service and domain layers. Jinja2/templates, HTMX or small JavaScript modules,
Task and Tag persistence, and local import/export and backup/restore require
their own approved specifications. Future adapters must not create parallel
business-logic or persistence paths.

### Templates/static assets

Jinja2 templates and static assets are intended to render the web UI. HTMX or a
small amount of JavaScript may enhance interactions. Presentation code must call
the Web/API boundary and shared services rather than recreate domain rules.

## Dependency direction

The dependency direction is from the outside toward the domain:

```text
FastAPI API -> ProjectService -> ProjectRepository protocol -> Domain
                                  ^
                                  |
                    SQLAlchemy repository -> ORM / SQLite
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
