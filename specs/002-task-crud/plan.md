# Implementation plan: Task CRUD

## Status

Approved

The human approved implementation and autonomous delivery on 2026-07-14.
High-risk pre-push approval remains a separate required gate.

## Summary

Extend the implemented Project layers with a Task domain entity, repository
protocol and SQLAlchemy implementation, application service, nested FastAPI
schemas/routes, deterministic list query, and Project-delete conflict handling.
No application implementation is included in this planning commit.

## Existing architecture investigation

- Project and path IDs are SQLite integer primary keys and FastAPI integer path
  parameters.
- API routes live under `/api/projects`, call application services, and map
  domain/repository errors to `{"detail": ...}` responses.
- Request schemas use Pydantic `model_fields_set` plus an application `UNSET`
  sentinel to distinguish omitted values from explicit null.
- Project DELETE returns 204 with no body. Empty Project PATCH returns 422.
- Domain dataclasses are frozen, validate on construction, and normalize aware
  datetimes to `datetime.UTC`.
- Repository protocols live in `repositories/*_repository.py`; concrete
  SQLAlchemy repositories are imported directly only by API wiring and tests.
- Concrete repositories own write commit/rollback on a caller-owned request
  session. Reads do not commit; failures become sanitized `RepositoryError`.
- ORM models use typed SQLAlchemy declarative mappings in
  `infrastructure/models.py`. `initialize_schema()` explicitly imports mappings
  and calls metadata `create_all`; importing modules alone does not create data.
- SQLite foreign keys are not currently enabled and must be enabled per engine
  connection for Task integrity.
- Tests inject one temporary SQLite engine/session factory per test and use
  clean subprocesses for import-isolation checks.
- API UTC responses end in `Z`; repository conversion restores UTC awareness
  lost by SQLite.

## Risk and approval

Risk is high in the `migration` domain because the work adds a table, indexes,
and foreign key, changes Project deletion behavior, and exercises transactional
rollback. `auto_merge` remains false. Autonomous implementation must stop at
the high-risk pre-push gate and preserve repository policy's review-call limit.

## Design

### Domain and application

Add a frozen Task entity, `TaskStatus`/`TaskPriority` string enums, normalization
helpers, Task-specific validation/not-found errors, and a Project-has-Tasks
conflict error. Add a Task repository protocol with nested ownership-aware CRUD
and list-query inputs. `TaskService` validates Project existence through an
interface dependency, creates timestamps, preserves omitted PATCH fields,
rejects empty patches, and never imports SQLAlchemy.

### Infrastructure and schema

Add `TaskModel` with integer primary key and non-null `project_id` foreign key
to `projects.id`. Do not configure cascade deletion. Add named indexes for the
four approved shapes. Extend the SQLite engine connection setup so every
connection executes `PRAGMA foreign_keys=ON` without exposing raw SQL outside
infrastructure.

`initialize_schema()` remains the only schema creation entry point. SQLAlchemy
`create_all` creates the missing Task table and indexes without dropping or
rewriting existing Project rows. This is suitable only for current local
development/tests; production migration and schema-version upgrades remain
unresolved. No Alembic or dependency change is allowed.

### Repositories and transactions

Add `SQLAlchemyTaskRepository`, which converts ORM/domain values, uses bound
SQLAlchemy expressions for nested ownership queries, applies all filters and
deterministic ordering in one query, and enforces limit/offset. Successful
writes commit; every SQLAlchemy failure rolls back before a generic
`RepositoryError`. Project deletion must check Task existence in the same
write transaction and raise a stable conflict error without deleting anything.

After rollback, repository calls on the same caller-owned session must work.
No API route commits or rolls back.

### API

Add Task create/update/response/query schemas and nested routes under
`/api/projects/{project_id}/tasks`. Pydantic forbids extra request fields,
validates enum/query bounds, and rejects naive datetimes. The service boundary
performs the same domain validation. Reuse generic sanitized repository-error
mapping and add stable Task 404 and Project conflict 409 mappings.

Task PATCH follows Project's sentinel approach but accepts all five mutable
fields. Empty PATCH is 422; explicit null is permitted only for description and
due date. Task DELETE returns an empty 204 response.

### List query

Build one SQLAlchemy SELECT constrained by `project_id`, optional status,
priority, and strict due bounds. Apply a bounded limit/offset and one of four
allow-listed sort expressions. Use CASE for semantic priority order and explicit
null ranking for due dates. Always append ascending Task ID as tie-breaker and
do not load Projects per Task, preventing N+1 queries.

### UTC normalization

Move or reuse one infrastructure-neutral UTC normalization helper so Task
domain input, due filters, repository hydration, and API response semantics do
not drift. Naive client datetimes fail before persistence; SQLite-loaded values
are restored as aware UTC.

## Affected paths

| Path | Planned change | Risk |
|---|---|---|
| `src/project_board/domain/**` | Task entity, enums, errors, shared UTC rules | Medium |
| `src/project_board/repositories/**` | Task protocol/implementation and Project delete guard support | High |
| `src/project_board/infrastructure/**` | Task mapping, indexes, foreign-key enablement | High |
| `src/project_board/application/**` | Task use cases and conflict orchestration | Medium |
| `src/project_board/api/**` | Task schemas/routes/dependencies and 409 mapping | Medium |
| `src/project_board/main.py` | Include Task routes without changing health behavior | Medium |
| `tests/app/**` | Isolated unit/application/integration/regression tests | Medium |
| `README.md`, `docs/architecture.md` | Document Task API, schema limits, and remaining migration risk | Low |
| `specs/002-task-crud/**` | Contract and later evidence | Low |

## Test strategy

- Domain/unit: defaults, every field, trim/length, enums, due UTC/naive input,
  immutable ownership, and timestamp invariants.
- Service tests: create/get/patch/delete, missing Project/Task, ownership
  mismatch, null versus omitted values, empty PATCH, and repository failures.
- Repository integration: schema/index/foreign-key inspection; CRUD; filters;
  pagination; every sort; semantic priority; nulls-last; stable IDs; rollback;
  reusable session; and persisted restart.
- API integration: full nested round trip, 201/204/404/409/422/generic 500,
  cross-Project isolation, forbidden fields, query validation, and deterministic
  response order.
- Project deletion: no-Task success, Task conflict with data intact, then Task
  removal followed by successful Project deletion.
- Import isolation: clean subprocess imports of Task service and repository
  protocol do not load SQLAlchemy or concrete infrastructure.
- Regression: existing Project CRUD, `/health`, framework tests, type checking,
  build, and full `make validate`.

## Rollback strategy

Before production use, revert Feature 002 commits through a normal PR. Do not
drop tables or delete local data automatically. Existing Project data remains
valid because schema initialization only adds missing Task structures.

## Implementation order

1. Domain entity/enums/errors and repository protocol.
2. ORM schema, indexes, and SQLite foreign-key enforcement.
3. Transactional Task repository and Project delete guard.
4. Task application service.
5. Create/detail API.
6. PATCH/DELETE API.
7. Filtered, sorted, paginated list API.
8. Project deletion conflict behavior.
9. Complete unit/integration/import-isolation/regression coverage.
10. Documentation, full validation, exact-HEAD evidence, and review readiness.

## Open questions

None for implementation. A production migration/versioning strategy remains an
explicit residual risk and non-goal requiring a separate approved feature.
