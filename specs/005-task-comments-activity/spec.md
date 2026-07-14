# Feature specification: Task comments and activity history

## Status

Approved

The human-approved Feature 005 request and its Project-deletion clarification
on 2026-07-15 are the source of truth. There is no GitHub Issue. High-risk
pre-push approval remains a separate gate.

## Goal

Add Project-scoped comments to Tasks and expose append-only comment lifecycle
activity while proving database ownership, atomic mutation/activity writes,
rollback, UTC timestamps, bounded pagination, deterministic ordering, cascade
cleanup, and cross-Project concealment.

## Requirements

- REQ-001: `TaskComment` has positive integer `id`, immutable positive
  `project_id` and `task_id`, trimmed `body`, and aware UTC `created_at` and
  `updated_at`; created time never changes and successful updates advance
  updated time.
- REQ-002: Comment body is a string of 1..2000 characters after trimming,
  accepts Unicode and newlines, rejects empty/whitespace, null, and 2001+
  characters with 422, and is returned as JSON text without HTML execution.
- REQ-003: `TaskCommentActivity` has positive integer `id`, immutable ownership
  and `comment_id`, fixed event type `comment_created|comment_updated|comment_deleted`,
  and aware UTC `occurred_at`.
- REQ-004: Activity is append-only: no update/delete API or repository mutation
  exists. It stores no Comment body or sensitive payload, and retains the
  deleted Comment ID after physical Comment deletion while its Task exists.
- REQ-005: Add `task_comments` and `task_comment_activities` tables without
  changing existing Project, Task, Tag, or association columns, constraints, or
  meanings.
- REQ-006: Both tables enforce `(project_id, task_id)` ownership with composite
  foreign keys to Tasks and `ON DELETE CASCADE`; direct Project foreign keys
  provide defensive ownership/cascade integrity. Activity `comment_id` is an
  identifier, not a foreign key to the deletable Comment row.
- REQ-007: Add deterministic Task-local indexes over ownership plus timestamp
  and ID. SQLite foreign-key enforcement remains enabled and new empty databases
  initialize all existing and new tables.
- REQ-008: Extend only the existing metadata/create-all development/test schema
  initialization. Add no migration framework/dependency and never connect to or
  mutate a production database.
- REQ-009: Comment create/list/detail/PATCH/delete endpoints are nested below
  `/api/projects/{project_id}/tasks/{task_id}/comments`; success statuses are
  201/list 200/detail 200/PATCH 200/delete empty 204.
- REQ-010: Comment list accepts limit 1..100 default 50, offset >=0 default 0,
  and `order=asc|desc` default asc; it orders by created_at in the requested
  direction and integer ID ascending as final tie-breaker, then paginates.
- REQ-011: PATCH accepts exactly the mutable `body`, requires it, rejects null,
  omitted body, and immutable/unknown fields with 422. Patching the same
  normalized body succeeds, advances `updated_at`, and appends one update event.
- REQ-012: Activity list is the only activity endpoint, nested at
  `/api/projects/{project_id}/tasks/{task_id}/activities`; it supports the same
  bounded pagination/order and optional fixed `event_type`, filters before
  sorting/pagination, and sorts by occurred_at plus ascending ID tie-breaker.
- REQ-013: Every endpoint verifies Project and Task ownership. Missing Project,
  Task, Comment, or cross-Task/cross-Project Comment returns the existing
  sanitized 404 without revealing foreign data; invalid query/body returns 422.
- REQ-014: Comment create and `comment_created` activity are one transaction;
  either both commit or both roll back.
- REQ-015: Comment update and `comment_updated` activity are one transaction;
  event failure rolls back body and updated time, and failed update adds no event.
- REQ-016: `comment_deleted` activity creation and physical Comment deletion are
  one transaction; either both commit or both roll back. The committed activity
  remains retrievable after the Comment is gone.
- REQ-017: Repository/commit/constraint failures roll back partial state, expose
  no SQL/table/path/stack details, and leave the request session reusable.
- REQ-018: Task deletion cascades all its Comment and Activity rows without
  deleting unrelated data. Existing Project deletion remains 409 while Tasks
  exist; after Tasks are explicitly deleted and cascades have removed child
  rows, Project deletion succeeds with no orphan Comment/Activity rows.
- REQ-019: Project CRUD, Task CRUD/query, Tag CRUD/association, response schemas,
  defaults, and existing tests remain unchanged. Task responses do not embed
  Comments or Activity, and existing Task list queries add no Comment query.
- REQ-020: Domain/application/repository interfaces remain independent of
  SQLAlchemy. Package roots export interfaces/domain types only; service or
  interface imports do not eagerly load infrastructure or concrete repositories.
- REQ-021: API handlers build no SQL and perform no commit/rollback. A combined
  Comment persistence boundary owns atomic mutation plus activity append using
  the existing request-scoped session convention.
- REQ-022: Comment and Activity lists execute bounded single-entity queries and
  do not issue per-row follow-up queries; statement-count tests prove no N+1.
- REQ-023: Comprehensive domain, schema, API, repository, rollback, cascade,
  isolation, import, statement-count, and prior-feature regressions pass without
  weakening tests or framework gates.
- REQ-024: Feature risk is high with migration domain and auto-merge disabled;
  exact-HEAD validation and all review shards must pass before stopping at the
  human high-risk pre-push gate.

## Acceptance criteria

- [ ] AC-001: Domain tests prove trim, empty/null rejection, 2000/2001 boundary,
  Unicode/newlines, aware UTC enforcement, and fixed activity event types.
- [ ] AC-002: Schema inspection proves both tables, required columns, nullability,
  composite Task ownership FKs, Project FKs, cascades, and deterministic indexes.
- [ ] AC-003: Empty schema initialization creates all tables with foreign keys
  enabled and preserves existing Project/Task/Tag schema and rows.
- [ ] AC-004: Comment CRUD returns specified status/body shapes and preserves
  Project/Task ownership and UTC timestamp serialization.
- [ ] AC-005: Comment list default/boundary pagination and ascending/descending
  deterministic order pass; invalid limit/offset/order returns 422.
- [ ] AC-006: PATCH rejects absent/null/extra/immutable fields; normal and
  same-body updates advance updated time, preserve created time, and append one event.
- [ ] AC-007: Activity list filters all three event types before pagination,
  orders deterministically, has no mutation routes, and never exposes body.
- [ ] AC-008: Missing and foreign Project/Task/Comment operations return
  indistinguishable existing 404 responses and leak no cross-Project data.
- [ ] AC-009: Forced activity failure on create rolls back the Comment; successful
  create commits exactly one Comment and one created event.
- [ ] AC-010: Forced activity/update failure restores body and updated time and
  leaves no update event; the session remains usable.
- [ ] AC-011: Forced activity/delete or Comment-delete failure preserves the
  Comment and adds no deleted event; success removes the row and retains one event.
- [ ] AC-012: Task deletion physically removes owned Comments/Activity; other
  Tasks and Projects remain. Project deletion retains existing 409 semantics,
  then succeeds after explicit Task deletion with no child orphans.
- [ ] AC-013: Direct database attempts to associate rows with mismatched
  Project/Task ownership fail and roll back.
- [ ] AC-014: Clean subprocess imports of Comment service/interfaces do not load
  SQLAlchemy, infrastructure models, or concrete repositories.
- [ ] AC-015: Statement-count tests show Comment and Activity list query counts
  remain constant as row count grows and existing Task lists issue no new query.
- [ ] AC-016: Existing Project, Task, Tag, Task-query, and health tests pass with
  unchanged response contracts.
- [ ] AC-017: Feature spec-lint, targeted tests, Ruff, format, mypy, secrets,
  build, and exact-HEAD `make validate` pass.
- [ ] AC-018: Evidence order is accepted -> weakening -> review; all five review
  shards pass under max eight calls with no required finding.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| Project deletion | Preserve Feature 002: a Project with Tasks returns 409. Task deletion performs the meaningful child cascade; after all Tasks are explicitly deleted, Project deletion succeeds and no Comment/Activity orphan remains. | Human clarification |
| Project FK | New child tables also reference Project defensively, but existing Task FK and Project API semantics are not changed. | Human clarification |
| Same-body PATCH | Return 200, advance `updated_at`, and append exactly one `comment_updated` activity. | Approved recommendation |
| Activity and Comment deletion | Activity `comment_id` is intentionally not a Comment FK, so deletion history remains while Task exists. | Append-only requirement |
| Transaction owner | One SQLAlchemy Comment repository method performs each mutation and activity append in the same request-scoped session/commit. | Existing repository convention |
| UTC | Domain rejects naive values; repository restores SQLite timestamps as aware UTC; API serializes existing datetime shape. | Existing Features 001-004 |
| API prefix | All paths retain the existing `/api/projects` prefix. | Existing API |
| Errors | Existing `{"detail": ...}` shape; repository failures use the existing sanitized 500 response. | Existing API |
| Migration | Metadata initialization only; no Alembic, dependency, or production migration. | Approved scope |

No material ambiguity remains. Changes require new human approval.

## API

```text
POST   /api/projects/{project_id}/tasks/{task_id}/comments
GET    /api/projects/{project_id}/tasks/{task_id}/comments
GET    /api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}
PATCH  /api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}
DELETE /api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}
GET    /api/projects/{project_id}/tasks/{task_id}/activities
```

Comment list query: `limit=50`, `offset=0`, `order=asc`.
Activity list adds optional `event_type`.

## Risk and non-goals

Risk is high, `risk_domains = ["migration"]`, auto-merge false. Non-goals:
authors/users/auth, reactions, attachments, body snapshots, activity mutation,
Task response embedding, production migration/deployment, external services,
and changes to existing table semantics.
