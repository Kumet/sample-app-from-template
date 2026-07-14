# Plan: Project dashboard analytics

## Existing architecture

- FastAPI routes use Pydantic response models and sanitized service errors.
- Application services depend only on repository protocols and support injected
  clocks; UTC normalization is centralized in the domain datetime helper.
- SQLAlchemy repositories use one request-scoped Session and restore SQLite
  datetime awareness at their persistence boundary.
- Existing models already contain every ownership key and association required
  for Task, Tag, Comment, and Activity aggregation. No schema work is needed.
- Task status order is `todo, in_progress, done`; `done` is terminal. Priority
  order is `low, medium, high`; Tag order is normalized name then ID.

## Design

1. Add infrastructure-neutral immutable aggregate value objects and a
   `ProjectDashboardRepository` protocol. Centralize terminal status and result
   invariants in this boundary/domain layer.
2. Implement `SQLAlchemyProjectDashboardRepository` with grouped Task counts,
   mutually-exclusive due conditional aggregates, outer-joined Tag counts,
   Comment total/distinct counts, and a bounded recent Activity query.
3. Keep the query count at no more than eight including Project existence. Use
   ownership predicates in every statement, `COUNT(DISTINCT ...)` where needed,
   deterministic ordering, bound parameters, and no entity-per-row loading.
4. Implement `ProjectDashboardService` with one injected/normalized UTC clock,
   explicit Project existence verification, repository orchestration, and
   invariant validation before returning the typed dashboard.
5. Add Pydantic nested response schemas, request-scoped dependency wiring, and
   one dashboard route with `activity_limit` validation.
6. Add unit tests for clock, enums, invariants, service orchestration, and import
   isolation; integration tests for every aggregate/boundary/isolation/order,
   statement counts, parameter binding, determinism, and database non-mutation.
7. Run prior-feature regressions, update README minimally, validate the exact
   HEAD, generate evidence, run weakening and all review shards, then publish a
   ready-for-review PR without merging it.

## Due calculation

The service calls the clock once. Repository predicates receive the normalized
`as_of`, next UTC midnight, and the midnight seven days later. Only non-`done`
Tasks participate. SQL conditional counts implement the approved half-open
boundaries; the typed result verifies bucket sum equals active total.

## Snapshot and mutation safety

The existing request-scoped Session is shared by Project existence and all
aggregate queries. Dashboard code never flushes, commits, updates, or deletes.
Tests fingerprint all table rows before and after reads and repeat fixed-clock
requests to prove deterministic non-mutation.

## Query-count strategy

Use a fixed sequence of set-based statements: Project existence, grouped Task
status/priority counts, due conditional counts, outer-joined Tag counts,
Comment totals, and bounded Activity rows. The enforced upper bound is eight;
tests compare empty and increasing Task/Tag/Comment/Activity datasets using SQL
statement events, never wall-clock timing.

## Validation strategy

- Unit: typed aggregate invariants, terminal policy, aware clock, service
  ownership/orchestration, repository/application import isolation.
- Integration: API schema and limits, all due boundaries, grouped counts,
  ownership isolation, ordering/tie-breaks, deleted rows, query count,
  parameter binding, repeated determinism, and table fingerprint stability.
- Regression: every existing Project/Task/Tag/Comment/Activity/query/health test
  plus framework suite, Ruff, format, mypy, secrets, and build.
- Evidence/review: tracked snapshot, exact validation, accepted, weakening,
  spec-scope/security/tests/maintainability, integration last, max eight calls.

## Scope and rollback

Only approved application, test, README, and Feature 018 spec paths may change.
Implementation is additive and read-only; rollback is reverting Feature 018
commits. Stop before implementation if schema, dependency, framework, policy,
prior spec/runtime evidence, or additional scope changes become necessary.
