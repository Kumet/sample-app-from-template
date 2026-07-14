# Plan: Task query

## Existing architecture

- FastAPI exposes the existing nested Task list route and Pydantic validates its
  query parameters.
- `TaskService` verifies Project and optional Tag ownership before delegating.
- The infrastructure-neutral `TaskListQuery` crosses the application/repository
  boundary.
- `SQLAlchemyTaskRepository` builds bound expressions, applies strict due
  filters, deterministic sorting, offset/limit, and bulk-loads Tags.
- Feature 002 owns defaults and ordering; Feature 003 owns Tag filtering/loading.

## Design

1. Extend `TaskListQuery` with normalized `q` and immutable tuples of statuses
   and priorities. Validate due-bound order without importing infrastructure.
2. Parse repeated FastAPI parameters while preserving one-value requests and
   existing defaults. Keep all existing names; add no aliases.
3. Build SQLAlchemy predicates for escaped literal case-insensitive search and
   `IN` filters. Keep Project and Tag checks in the service.
4. Add case-insensitive title sorting while retaining existing due nulls-last,
   priority order, and ID tie-break rules.
5. Preserve the DB-side filter -> sort -> pagination pipeline and bounded bulk
   Tag loading. Add statement-count regression coverage.
6. Expand API/repository tests for compatibility, validation, composition,
   isolation, wildcard escaping, timezones, and deterministic ordering.
7. Update README only if a concise query-parameter note is necessary, then run
   full exact-HEAD validation and independent review.

## Data and migration

No model, metadata, table, column, index, constraint, database initialization,
or migration file changes are permitted. Existing Task/Tag schema supports the
queries. Discovery of a required schema change is a safety stop.

## Query semantics

- API validates and trims `q`; the repository escapes SQL LIKE metacharacters
  and uses a bound pattern with an explicit escape character.
- Status/priority are deduplicated into tuples and map to SQL `IN` predicates.
- Due values are aware UTC-normalized datetimes with strict predicates.
- All filters are applied before deterministic sort and pagination.
- Tag hydration remains a bounded bulk query, never a query per Task.

## Validation strategy

- Unit: query-object normalization/validation and import isolation.
- App/API: parameter compatibility, 422/404 behavior, search, repeated enums,
  composition, deterministic sorting, pagination, and response compatibility.
- Integration: bound literal search, cross-Project isolation, SQL statement
  counts, Tag loading, strict due boundaries, and regression behavior.
- Full: `make validate`, exact-HEAD evidence, weakening inspection, and five
  identity-bound review shards with integration last.

## Rollback and failure handling

This is read-only query functionality. Validation failures occur before SQL;
repository failures follow existing sanitized error handling. Revert focused
task commits if human-directed rollback is required; never change schema or
runtime evidence manually.

## Implementation order and scope

Implement the query contract, API parsing, repository predicates/sorting,
performance/isolation tests, broad API regressions, and final documentation in
dependency order. Only the validation contract's allowed paths may change.
Framework, migration, dependency, policy, and prior-spec changes are stop
conditions.

## Risk and gates

Medium infrastructure risk, auto-merge disabled. Attempts remain bounded. All
validation and review gates remain unchanged. Push and ready-for-review PR are
allowed only after exact-HEAD validation and all review shards pass; main merge
requires later human approval.
