# Feature specification: Project dashboard analytics

## Status

Approved

The human-approved Feature 018 request dated 2026-07-15 is the source of
truth. There is no GitHub Issue. The identifier is 018 because repository
identifiers 006 through 017 are already occupied by framework specifications.

## Goal

Add one read-only Project dashboard API that reports deterministic Task, due,
Tag, Comment, and recent Comment-activity aggregates without changing the
database schema or existing API contracts.

## Requirements

- REQ-001: Add exactly one `GET /api/projects/{project_id}/dashboard` endpoint;
  an existing Project returns 200 and a missing Project returns the existing
  sanitized 404 even when all aggregate tables are empty.
- REQ-002: The response contains integer `project_id`, aware UTC `as_of`, Task
  totals, due buckets, Tag counts, Comment statistics, and recent activities in
  the approved nested shape without modifying existing response schemas.
- REQ-003: A single injectable clock value is normalized to UTC once per
  request and is used for every due boundary and the returned `as_of`; naive or
  non-datetime clock values fail validation.
- REQ-004: Task total includes every owned Task. `by_status` contains `todo`,
  `in_progress`, and `done` in enum order including zeros; `by_priority`
  contains `low`, `medium`, and `high` in enum order including zeros. Each map
  sums to total and foreign Project rows are excluded.
- REQ-005: `done` is the sole terminal status and is centralized through the
  existing Task enum/domain policy. Terminal Tasks remain in total/status/
  priority counts but are excluded from all due counts.
- REQ-006: For active Tasks, `overdue` is non-null due_at before `as_of`;
  `due_today` is from `as_of` inclusive to the next UTC midnight exclusive;
  `upcoming_7_days` is from that midnight inclusive to seven days later
  exclusive; `later` starts at that endpoint; null is `no_due_date`.
- REQ-007: Due buckets are mutually exclusive and their sum equals
  `active_total`; due_at equal to `as_of` is today, next UTC midnight is
  upcoming, and the upcoming endpoint is later.
- REQ-008: Tags include every owned Tag, including unattached Tags at zero,
  count distinct owned Task associations once, exclude deleted/foreign Tags,
  and order by normalized name ascending then integer ID ascending.
- REQ-009: Comment `total` counts current owned Comment rows and
  `tasks_with_comments` counts distinct owned Tasks with one or more current
  Comments; Activity rows and deleted Comments are not counted.
- REQ-010: Recent activities contain only existing owned Task activity metadata
  using the existing payload-free Activity shape and fixed event enum, ordered
  by occurred_at descending then ID descending. Deleted-comment activity remains
  while its Task exists; cascaded Task activity is absent.
- REQ-011: `activity_limit` defaults to 10, accepts integers 0..50, rejects
  negatives, 51+, bool-like/non-integers with 422, affects only recent activity,
  and zero returns an empty list without an activity data query.
- REQ-012: An empty Project returns every status, priority, and due key at zero,
  zero Comment statistics, empty activity, and all owned unattached Tags at zero.
- REQ-013: A framework-independent typed dashboard query/result boundary keeps
  SQLAlchemy and database rows out of domain/application imports; API handlers
  build no SQL and response schemas are separate from ORM models.
- REQ-014: The SQLAlchemy implementation uses grouped and distinct aggregate
  queries plus one bounded activity query in the existing request-scoped
  Session, performs no commit or mutation, uses parameter binding, and reads no
  full entity collection for Python-side aggregation.
- REQ-015: SQL statement count is bounded by eight and does not grow with Task,
  Tag, Comment, or Activity row counts; no per-row follow-up query is permitted.
- REQ-016: Repeated reads over unchanged data are deterministic and dashboard
  execution leaves all Project, Task, Tag, association, Comment, and Activity
  rows unchanged.
- REQ-017: Existing Project, Task, Tag, Comment/Activity, and Task-query APIs,
  defaults, response schemas, statement counts, and tests remain unchanged.
- REQ-018: Feature 018 changes no table, column, index, constraint, migration,
  dependency, framework script, policy, CI setting, or production configuration.
- REQ-019: Feature risk is medium with infrastructure domain and auto-merge
  disabled; bounded validation, weakening inspection, exact-HEAD evidence, and
  all five review shards remain required.
- REQ-020: Full regression, import-isolation, project-isolation, boundary,
  deterministic-order, statement-count, and no-mutation tests pass without
  weakening existing assertions or gates.

## Acceptance criteria

- [ ] AC-001: Missing Project returns 404; empty Project returns the complete
  zero-valued dashboard and owned zero-count Tags.
- [ ] AC-002: The response schema, ID types, aware UTC serialization, activity
  metadata, and `activity_limit` 0/default/50 and invalid boundaries pass.
- [ ] AC-003: One fixed injectable aware clock supplies `as_of` and every due
  calculation; naive/non-datetime clocks fail before repository aggregation.
- [ ] AC-004: Task total, all zero-inclusive status/priority keys, enum order,
  sum invariants, terminal inclusion, and cross-Project exclusion pass.
- [ ] AC-005: Every due boundary and null/terminal case passes and due buckets
  sum exactly to active total.
- [ ] AC-006: Tag zero/distinct/multi-Tag counts, foreign exclusion, normalized
  ordering, and ID tie-break pass.
- [ ] AC-007: Current Comment total and distinct Tasks-with-Comments pass across
  multiple Comments, deletion, Activity rows, and foreign Projects.
- [ ] AC-008: Recent activity is bounded, descending by timestamp and ID,
  payload-free, ownership confined, and respects Comment/Task deletion behavior.
- [ ] AC-009: Typed repository/application boundaries and clean subprocess
  imports prove no eager SQLAlchemy/infrastructure loading.
- [ ] AC-010: SQL statement counts remain at most eight and constant as each
  aggregate data family grows; all statements retain parameter binding.
- [ ] AC-011: Dashboard reads make no database changes and repeated responses
  with a fixed clock are deterministic.
- [ ] AC-012: Existing Project, Task, Tag, Comment/Activity, Task-query, health,
  framework, app, and integration regressions pass unchanged.
- [ ] AC-013: Feature spec-lint, targeted tests, Ruff, format, mypy, secret
  check, build, and exact-HEAD `make validate` pass.
- [ ] AC-014: No schema, migration, dependency, framework, policy, CI, prior
  spec, or runtime-evidence path changes.
- [ ] AC-015: Accepted validation precedes current-HEAD weakening evidence and
  all file review shards; integration runs only after their gate PASS.
- [ ] AC-016: All review shards pass with at most eight subprocess calls and no
  required finding before the ready-for-review PR is created.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| Feature identifier | Use `018-project-dashboard-analytics`; do not create or change any `specs/006-*` path. | Approved request and occupied framework IDs |
| API prefix and IDs | Use `/api/projects/{project_id}/dashboard` and existing positive integer IDs. | Existing API contract |
| Terminal status | `TaskStatus.DONE` (`done`) is the sole terminal status; define the policy once rather than repeating string literals. | Existing Task enum and approved fallback |
| Status/priority order | `todo, in_progress, done` and `low, medium, high`, matching enum definition order. | Existing domain |
| Tag order | `normalized_name ASC, id ASC`; normalized name remains internal. | Existing Tag list policy |
| Activity response | Reuse the existing payload-free Activity fields: id, project_id, task_id, comment_id, event_type, occurred_at. | Feature 005 |
| Query budget | Maximum eight SQL statements: Project existence plus bounded grouped aggregate queries; row count must not affect the total. | Approved recommendation and current repository structure |
| Snapshot | All reads use the same request-scoped Session with no commit. SQLite request-session consistency is the existing supported snapshot convention. | Existing infrastructure |
| Migration | No schema/model/initialization change, migration, dependency, or production database access. | Approved scope |

No material ambiguity remains. Any change to these answers requires new human
approval.

## Response contract

```json
{
  "project_id": 1,
  "as_of": "2026-07-15T00:00:00Z",
  "tasks": {
    "total": 0,
    "by_status": {"todo": 0, "in_progress": 0, "done": 0},
    "by_priority": {"low": 0, "medium": 0, "high": 0}
  },
  "due": {
    "active_total": 0,
    "overdue": 0,
    "due_today": 0,
    "upcoming_7_days": 0,
    "later": 0,
    "no_due_date": 0
  },
  "tags": [],
  "comments": {"total": 0, "tasks_with_comments": 0},
  "recent_activities": []
}
```

## Risk and non-goals

Risk is medium, `risk_domains = ["infrastructure"]`, auto-merge false.
Non-goals include schema/migration/index changes, dashboards across Projects,
historical snapshots, authentication/authorization, UI/charting, caching,
background jobs, exports, and changes to existing APIs.
