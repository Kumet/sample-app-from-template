# Architecture

## Status

Local Project Board is in its bootstrap stage. A minimal FastAPI process and
health endpoint exist, while the product layers below remain an intended
architecture rather than a current implementation. Concrete interfaces,
transaction boundaries, and framework integration must be decided in approved
feature specifications and technical plans.

## Intended system overview

The application is expected to use a layered architecture in which the web UI,
REST API, and CLI share the same application service and domain logic. SQLite
provides local persistence. The user-facing web interface is rendered from
templates and enhanced only where useful with HTMX or small JavaScript modules.

The current runtime surface is limited to `project_board.main`, which creates
the FastAPI application and serves `GET /health`. It has no database, domain
model, application service, templates, CLI, or external integration.

```text
Web UI / REST API       CLI
         \               /
          Web/API and CLI adapters
                    |
        Application service layer
                    |
               Domain layer
                    ^
          Repository abstractions
                    ^
         SQLite infrastructure

Templates and static assets support the Web UI boundary.
```

Dependencies should point inward: outer delivery and infrastructure layers may
depend on application and domain abstractions, while the domain must not depend
on FastAPI, CLI parsing, SQLAlchemy, SQLite, templates, or static assets.
Repository interfaces are expected to be defined at an inward-facing boundary;
their SQLite/SQLAlchemy implementations remain infrastructure concerns.

## Intended layers

### Web/API layer

The planned FastAPI boundary handles HTTP input, request/response validation,
web routes, and REST API routes. It delegates use cases to the application
service layer and must not duplicate domain decisions. Authentication and
authorization are out of scope.

### CLI layer

The planned CLI translates local commands and arguments into the same
application service calls used by the web and API boundaries. It must not
maintain a separate business-logic or persistence path.

### Application service layer

This layer is intended to coordinate use cases, domain objects, repository
abstractions, and transaction boundaries. Import is required to execute as one
atomic transaction, but the concrete unit-of-work design is not yet decided.

### Domain layer

This is the intended home of Project, Task, status, priority, due-date, and Tag
rules. It should be independent of delivery frameworks and storage technology.
Undefined rules, including Project deletion behavior and user-facing timezone
policy, must remain undecided until an Approved specification resolves them.

### Repository layer

Repository abstractions are intended to express the persistence operations
needed by application services without exposing SQLite details to the domain.
Interfaces, aggregate boundaries, query shapes, and deletion semantics are not
yet fixed.

### SQLite infrastructure

The planned infrastructure uses local SQLite, likely through SQLAlchemy, to
implement repository and transaction abstractions. Schema design, migration
strategy, connection handling, and backup/restore mechanics are not yet fixed.
Import/export and backup/restore may access only local files explicitly selected
by the user.

### Templates/static assets

Jinja2 templates and static assets are intended to render the web UI. HTMX or a
small amount of JavaScript may enhance interactions. Presentation code must call
the Web/API boundary and shared services rather than recreate domain rules.

## Intended dependency direction

The dependency direction is from the outside toward the domain:

```text
Templates/static assets -> Web/API layer ----\
                                             -> Application services -> Domain
CLI layer -----------------------------------/
SQLite infrastructure -> Repository abstractions ------------------> Domain
```

Dependency inversion should allow infrastructure implementations to satisfy
interfaces used by inner layers. The exact interface ownership and module
layout must be validated in a future technical plan.

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
