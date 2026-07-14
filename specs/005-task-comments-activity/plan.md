# Plan: Task comments and activity history

## Existing architecture

- FastAPI routes use Pydantic schemas and sanitized domain/repository errors.
- Application services verify nested ownership through interface-only repositories.
- SQLAlchemy repositories own commit/rollback in one request-scoped session.
- SQLite foreign keys are enabled on connect; explicit metadata initialization
  creates parent tables before composite association tables.
- Tasks have a unique `(project_id, id)` ownership index suitable for composite FKs.

## Design

1. Add infrastructure-independent Comment and Activity domain types, body/UTC
   validation, fixed activity enum, errors, list query objects, and repository protocol.
2. Add `task_comments` and `task_comment_activities` models. Both use composite
   ownership FKs to Tasks and direct Project FKs; only Task/Project deletion
   cascades Activity. Comment IDs in Activity remain plain immutable identifiers.
3. Update schema initialization ordering so Tasks precede both new child tables;
   preserve existing table definitions and initialization behavior.
4. Implement a combined SQLAlchemy Comment repository. Each create/update/delete
   method writes its lifecycle event before one commit and rolls the whole unit
   back on any SQLAlchemy failure. Read methods are bounded and ownership scoped.
5. Implement `TaskCommentService` for Project/Task verification, domain creation,
   same-body updates, not-found concealment, and query orchestration.
6. Add strict request/response schemas, dependency wiring, Comment CRUD routes,
   and read-only Activity list route using existing error mapping.
7. Test domain boundaries, schema/FKs/indexes, CRUD/pagination, activity history,
   atomic rollback/session reuse, Task cascade, clarified Project deletion,
   cross-Project DB/service/API isolation, import isolation, and statement counts.
8. Run complete regressions, update minimal docs, record evidence, validate the
   exact HEAD, run weakening inspection and all review shards, then stop pre-push.

## Transaction and rollback

Repository mutation methods accept the domain mutation and event timestamp,
stage Comment and Activity rows in one session, and commit exactly once. Any
flush/commit/delete failure rolls back. Tests inject failures at event append,
Comment delete, and commit boundaries and then reuse the same session.

## Cascade and deletion

Task deletion cascades Comments and Activities through composite Task ownership
FKs. Comment deletion leaves Activity because Activity does not reference the
Comment row. Existing Project deletion still returns 409 while Tasks exist;
tests explicitly delete Tasks first, prove child cascades, then delete Project
and prove no orphans or cross-Project effects.

## Migration strategy

Extend metadata/create-all development/test initialization only. Create existing
parents first and the two child tables in dependency-safe order. Do not change
existing columns/constraints, add dependencies, introduce Alembic, or access
production data. Schema inspection and preservation tests are mandatory.

## Validation strategy

- Unit: domain/body/UTC/event enum, list query, service orchestration, import isolation.
- Integration: schema, composite FK, CRUD/activity APIs, rollback, cascades,
  physical deletion, pagination/order/filter, cross-Project concealment, query count.
- Regression: all Project/Task/Tag/query/health plus full framework suite.
- Exact evidence: tracked snapshot, full validation, accepted event, weakening,
  file shards, integration last, high-risk pre-push stop.

## Scope and safety

Use only the declared application, test, README, and Feature 005 spec paths.
Production configuration, prior specs/runtime evidence, framework, CI, dependency,
and existing schema semantic changes are forbidden. Stop for scope expansion,
new dependencies, framework defects, repeated failure, or atomicity uncertainty.
