# Implementation plan: Project-scoped Task Tags

## Status

Approved

## Existing architecture

- Project, Task, and path IDs are SQLite integer primary keys.
- Frozen domain dataclasses validate text and aware UTC timestamps.
- Protocols live in `repositories/*_repository.py`; services import protocol
  modules directly, while API dependency wiring imports concrete repositories.
- SQLAlchemy repositories own successful write commit and failure rollback on
  request-scoped sessions. Routes only map domain errors.
- Explicit `initialize_schema()` imports ORM mappings and invokes metadata
  creation; SQLite foreign keys are enabled on every connection.
- Task lists already implement bounded filtering, pagination, deterministic
  sort, UTC conversion, cross-Project concealment, and rollback coverage.

## Design

### Domain and interfaces

Add a frozen Tag entity and centralized name/color normalization. Add Tag
validation/not-found/duplicate errors and a Tag repository protocol containing
owned CRUD plus idempotent association operations. Extend Task with a default
empty immutable Tag tuple and extend `TaskListQuery` with optional `tag_id`.

### Database schema

Add `tags` with Project FK cascade, Project-local normalized-name uniqueness,
and normalized list index. Add `task_tags(project_id, task_id, tag_id)` with a
composite primary key and cascading composite foreign keys to Task and Tag
ownership pairs. Add/check a unique `(project_id,id)` Task index during explicit
schema initialization so existing Task tables gain the parent key without row
replacement. Tag owns a table-level unique `(project_id,id)` key. SQLite FK
enforcement remains mandatory.

### Repositories and transactions

Implement Tag CRUD and association writes with bound SQLAlchemy expressions,
explicit commit, rollback, duplicate conversion, and idempotency. Extend Task
repository queries to filter through the association table and bulk load Tags
for returned Tasks in one additional query, preserving ordering and pagination.
Project and Task deletion rely on database cascades for association rows; the
existing Task-conflict guard remains authoritative before Project deletion.

### Application and API

Add TagService for Project-scoped CRUD and attach/detach ownership validation.
Pydantic create/update/public schemas forbid extras, normalize request values,
and omit `normalized_name`. Add nested Tag and association routes with stable
404/409/422/500 mappings. Extend Task response and list query with Tags and
`tag_id` without changing existing fields or status codes.

### Validation and tests

- Domain: boundaries, casefold, color, UTC, import isolation.
- Schema/repository: constraints/indexes, persistence, ordering, idempotency,
  cross-Project rejection, cascades, rollback, restart, query count.
- Service/API: CRUD, error shapes, immutable fields, Tag response ordering,
  association endpoints, filter composition, physical deletion.
- Regression: all Project/Task/health tests plus framework and full validation.

## Transaction and rollback strategy

Concrete repositories retain transaction ownership. Integrity errors caused by
Project-local duplicate names become `DuplicateTagName`; all other SQLAlchemy
failures become sanitized repository errors after rollback. Failed association
or cascade operations leave Task, Tag, and association rows unchanged and the
same session usable.

## Migration strategy and residual risk

Only development/test explicit initialization is extended. It creates missing
tables/indexes and does not drop or rewrite existing Project/Task rows. No
dependency or production migration framework is introduced. Applying these
schema changes to production databases remains unresolved and makes this a high
`migration`-domain risk requiring pre-push human approval.

## Affected paths

| Area | Change |
|---|---|
| `src/project_board/domain/**` | Tag entity, errors, Task Tag tuple |
| `src/project_board/repositories/**` | Tag protocol/SQLAlchemy repository, Task loading/filter |
| `src/project_board/infrastructure/**` | Tag/association models, constraints and initialization index |
| `src/project_board/application/**` | Tag CRUD and association service |
| `src/project_board/api/**`, `main.py` | schemas, dependencies, routes, response/filter integration |
| `tests/app/**` | unit, service, repository, API, schema and regression coverage |
| `README.md` | local Tag API/schema documentation |
| `specs/003-task-tags/**` | contract and evidence snapshot |

## Implementation order

1. Tag domain/errors/protocol.
2. ORM tables, ownership constraints, indexes, schema initialization.
3. Transactional Tag repository.
4. Task repository Tag loading and filtering.
5. Tag CRUD service.
6. Attach/detach service.
7. Tag API schemas/routes.
8. Task response and `tag_id` integration.
9. Deletion/cascade/rollback and comprehensive tests.
10. Documentation, full validation, exact-HEAD evidence, and review readiness.

## Rollback

Revert Feature 003 commits through a normal PR before production use. Do not
drop Tag tables or delete local data automatically. Runtime evidence and failed
worktrees remain available for investigation.
