# Feature specification: Task query

## Status

Approved

The human-approved Feature 004 request and its clarification on 2026-07-15 are
the source of truth. The clarification supersedes conflicting earlier wording
and makes the existing Feature 002 list contract authoritative.

## Goal

Extend the existing Project-scoped Task list endpoint with safe text search and
composable repeated status/priority filters while preserving its response,
defaults, Tag behavior, deterministic ordering, bounded pagination, layering,
and Project isolation. No database schema or migration changes are permitted.

## Requirements

- REQ-001: Extend only `GET /api/projects/{project_id}/tasks`; keep the list
  response schema, Task/Tag representation, HTTP behavior, and Project scope.
- REQ-002: With no query parameters, preserve `sort=created_at`, `order=asc`,
  `limit=50`, `offset=0`, the existing deterministic order, and at most 50 rows.
- REQ-003: Add optional `q`, trimmed before use and valid only at 1..100
  characters. Empty/whitespace-only or longer input returns 422.
- REQ-004: `q` performs a case-insensitive substring match against title OR
  nullable description. `%`, `_`, and the escape character are literals, input
  is bound as a parameter, and no SQL string concatenation is allowed.
- REQ-005: Existing `status` accepts one or repeated Task status values. Values
  are deduplicated without changing results; values within the field are ORed;
  omitted behavior is unchanged; invalid values return 422.
- REQ-006: Existing `priority` accepts one or repeated Task priority values with
  the same deduplication, OR, omission, and 422 rules as status.
- REQ-007: Existing scalar `tag_id` behavior is unchanged: the owned Tag filters
  associated Tasks, while a missing or foreign Tag returns the existing 404
  without disclosing cross-Project data.
- REQ-008: Existing timezone-aware RFC 3339 `due_after` and `due_before` are
  normalized to UTC and retain strict `due_at > due_after` and
  `due_at < due_before` semantics. Null due dates do not match. Naive values and
  `due_after >= due_before` return 422.
- REQ-009: Use only existing `sort` and `order`. Preserve all current sort
  fields and add `title`; order remains `asc|desc`, defaults remain
  `created_at|asc`, priority follows `low < medium < high`, title ordering is
  case-insensitive and deterministic, due nulls remain last in both directions,
  and integer Task ID is the final ascending tie-breaker.
- REQ-010: Preserve existing `limit` range 1..100, default 50, and `offset`
  minimum 0/default 0. Apply filters, then sort, then offset/limit and keep the
  response as a list.
- REQ-011: Compose different filter fields with AND; compose repeated status and
  repeated priority within their own field with OR. `q`, status, priority,
  `tag_id`, due bounds, sorting, and pagination work together.
- REQ-012: Verify Project existence before querying regardless of whether the
  eventual result is empty. Never return Tasks or Tag information from another
  Project.
- REQ-013: Represent query criteria with an infrastructure-independent typed
  object. API code validates parameters, the application service orchestrates
  Project/Tag checks, and only the SQLAlchemy repository builds SQL expressions.
- REQ-014: Filtering, sorting, and pagination execute in the database. Task Tags
  are bulk loaded with bounded statement count rather than one query per Task;
  pagination/filter joins must not duplicate Tasks.
- REQ-015: Domain, application, and repository-interface imports do not eagerly
  load SQLAlchemy, infrastructure models, or concrete repositories.
- REQ-016: Queries use parameter binding, validation and 404 responses expose no
  SQL or internal paths, and SQL-like input is treated as data.
- REQ-017: Add no table, column, index, constraint, migration, dependency,
  production configuration, framework change, or response-schema change.
- REQ-018: Add comprehensive unit/app/integration regressions for the approved
  contract while preserving Project, Task, Tag, health, framework, validation,
  review, and approval gates.

## Acceptance criteria

- [ ] AC-001: Parameter-free listing preserves the list schema, created-at
  ascending order, Tag ordering, and default limit 50, including a dataset over
  50 Tasks.
- [ ] AC-002: Existing explicit limit/offset, scalar status/priority, scalar
  `tag_id`, strict due bounds, and sort/order behavior remain compatible.
- [ ] AC-003: `q` matches title or description case-insensitively after trimming,
  accepts 1 and 100 characters, rejects empty/whitespace and 101 characters,
  and safely handles null descriptions.
- [ ] AC-004: `%`, `_`, escape characters, and SQL-injection-shaped values are
  literal bound search data and cannot broaden or alter the query.
- [ ] AC-005: Repeated status values and repeated priority values implement OR,
  duplicates are inert, invalid values return 422, and scalar calls still work.
- [ ] AC-006: `q`, status, priority, Tag, and strict due filters compose with AND;
  equal due boundaries are excluded and invalid/reversed ranges return 422.
- [ ] AC-007: Offset/limit is applied after filter and sort with the existing
  validation bounds and deterministic Task IDs as tie-breakers.
- [ ] AC-008: Each allowed sort field works ascending and descending; title is
  case-insensitive and stable, priority uses domain order, and due nulls are last.
- [ ] AC-009: Missing Projects and missing/foreign Tags return the existing 404,
  and no cross-Project Task or Tag data appears.
- [ ] AC-010: Repository SQL performs filtering/sorting/pagination and uses bound
  parameters without per-row Python filtering.
- [ ] AC-011: SQL statement-count tests show Tag loading does not grow with Task
  count and remains within a fixed bound for one and multiple Tasks.
- [ ] AC-012: Clean subprocess imports of application services and repository
  interfaces do not load SQLAlchemy or infrastructure modules.
- [ ] AC-013: Schema inspection and source scope confirm no database or migration
  changes and no unapproved dependency/framework changes.
- [ ] AC-014: Existing Project CRUD, Task CRUD, Tag CRUD/association, Task Tag
  responses, `/health`, and all prior tests remain green.
- [ ] AC-015: Feature spec-lint, targeted tests, Ruff, formatting, mypy, secret
  checks, build, and `make validate` pass at the exact validated HEAD.
- [ ] AC-016: Independent spec-scope, security, tests, maintainability, and
  integration review complete under the existing bounded review policy.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| Authoritative list contract | Feature 002's existing API contract takes precedence over conflicting initial Feature 004 wording. | Human clarification |
| Pagination default | Omitted `limit` remains 50; explicit limit remains 1..100; offset remains default 0/minimum 0. | Feature 002 |
| Sort parameters | Keep `sort` and `order`; add no `sort_by` or `sort_order` aliases. Existing defaults are `created_at` and `asc`. | Feature 002 |
| Due parameters | Keep `due_after` and `due_before`; add no `due_from` or `due_to` aliases. Boundaries are strict. | Feature 002 |
| Due range | Both bounds mean `due_after < due_at < due_before`; `due_after >= due_before` is 422. | Human clarification |
| Status/priority | Preserve scalar calls and extend repeated values to OR within each field; different fields remain AND. | Human clarification |
| Search | Add only `q`, with trimmed 1..100 literal case-insensitive substring semantics. | Human clarification |
| Response | Keep the existing list and existing Task response including deterministic Tags. | Backward compatibility |
| Unknown aliases | Do not introduce aliases and do not change the application's general unknown-query policy solely for this feature. | Human clarification |
| Migration | No schema, migration, or dependency change. Existing schema is sufficient. | Approved scope |

No material ambiguity remains. Any change to these decisions requires new
human approval.

## API query contract

```text
GET /api/projects/{project_id}/tasks
  ?q=<1..100 chars>
  &status=<todo|in_progress|done>        # repeatable
  &priority=<low|medium|high>            # repeatable
  &tag_id=<positive integer>
  &due_after=<aware RFC3339>             # strict lower bound
  &due_before=<aware RFC3339>            # strict upper bound
  &sort=<created_at|updated_at|due_at|priority|title>
  &order=<asc|desc>
  &limit=<1..100, default 50>
  &offset=<>=0, default 0>
```

The aliases `sort_by`, `sort_order`, `due_from`, and `due_to` are not part of
Feature 004.

## Risk and non-goals

Risk is medium with `risk_domains = ["infrastructure"]`: query construction,
isolation, and bounded loading change, but persistence schema and deployment do
not. Auto-merge is disabled.

Out of scope: schema/migrations/indexes, full-text search, fuzzy search, multiple
Tag filters, totals/page metadata, response envelopes, authentication,
authorization, new dependencies, framework changes, and production deployment.
