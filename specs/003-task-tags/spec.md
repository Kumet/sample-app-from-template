# Feature specification: Project-scoped Task Tags

## Status

Approved

The human supplied and approved this specification on 2026-07-14. There is no
GitHub Issue; the approved request is the source of truth. High-risk pre-push
approval remains a separate gate.

## Background and goals

Feature 001 added Project CRUD and Feature 002 added Project-owned Task CRUD.
This feature adds Project-owned Tags, many-to-many Task assignment, Tag data in
Task responses, and a Tag filter for Task lists while preserving the existing
layering, transactions, deterministic ordering, and non-disclosure rules.

## Requirements

- REQ-001: A Tag has a positive integer `id`, immutable integer `project_id`,
  trimmed display `name`, internal `normalized_name`, nullable `color`, and
  server-generated UTC `created_at` and `updated_at`.
- REQ-002: Tag name is required and 1..50 characters after trimming. Its
  internal uniqueness value is the trimmed display name's Python `casefold()`;
  `normalized_name` is never returned by the API.
- REQ-003: `(project_id, normalized_name)` is unique. Duplicate create or rename
  returns 409, equal names remain legal across Projects, and a case-only rename
  of the same Tag is legal.
- REQ-004: Color is null or exactly `#RRGGBB`; lowercase hex is normalized to
  uppercase, invalid or empty values return 422, and explicit PATCH null clears it.
- REQ-005: Nested Tag create/list/detail/update/delete endpoints return
  201/200/200/200/204 respectively, with an empty body for 204.
- REQ-006: Missing Project/Tag and cross-Project Tag access return 404 without
  revealing ownership. Invalid or forbidden request fields return 422.
- REQ-007: Tag PATCH requires at least one of `name` or `color`; name cannot be
  null. `id`, `project_id`, timestamps, and `normalized_name` are forbidden.
- REQ-008: Tag lists sort by normalized name ascending and then integer ID
  ascending, deterministically.
- REQ-009: A Task and Tag have a many-to-many association, and only Tags owned
  by the Task's Project can be associated.
- REQ-010: PUT/DELETE nested Task-Tag association endpoints attach/detach with
  empty 204 responses. Repeated attach and absent detach are idempotent.
- REQ-011: Missing or cross-Project Project/Task/Tag association requests return
  404. Service validation and database constraints both prevent cross-Project
  associations; failed writes roll back without changing Task or Tag data.
- REQ-012: Task create/detail/list/PATCH responses include `tags`, ordered by
  casefolded name then ID. Untagged Tasks return an empty array and all existing
  Task fields/status codes remain unchanged.
- REQ-013: Task list accepts optional positive integer `tag_id`. A valid owned
  Tag filters to associated Tasks; missing or foreign Tags return 404.
- REQ-014: `tag_id` composes with existing status, priority, due filters,
  sorting, limit, and offset. Filtering happens before pagination, produces no
  duplicate Tasks, and preserves existing deterministic order.
- REQ-015: Tag deletion removes its association rows but preserves Tasks and
  Projects. Failure rolls back both Tag and association deletion.
- REQ-016: Task deletion removes its association rows but preserves Tags.
- REQ-017: Project deletion remains 409 while Tasks exist. With no Tasks, a
  Project may be deleted even when it owns Tags; its Tags and associations are
  deleted without affecting other Projects.
- REQ-018: Schema initialization adds `tags`, `task_tags`, required uniqueness,
  foreign keys, and indexes while preserving existing Project and Task rows and
  keeping SQLite foreign keys enabled.
- REQ-019: Database ownership enforcement uses `task_tags.project_id` plus
  composite foreign keys to `(project_id, id)` of Tasks and Tags. Initialization
  creates/checks the required unique Task ownership index for existing databases.
- REQ-020: Successful create/update/delete/attach/detach explicitly commits;
  SQLAlchemy or commit failure rolls back and leaves the request session reusable.
- REQ-021: Duplicate database constraints map to the stable 409 domain error;
  unexpected infrastructure failures remain sanitized at the API and are not
  swallowed.
- REQ-022: Domain entities and repository protocols remain independent of
  FastAPI/SQLAlchemy. Service or repository-interface import must not eagerly
  load concrete SQLAlchemy repositories or infrastructure.
- REQ-023: API handlers contain no SQL, ORM, commit, or rollback logic. Concrete
  repositories own persistence transactions consistently with Features 001/002.
- REQ-024: SQLAlchemy queries use parameter binding, Task Tag loading avoids
  per-Task N+1 queries, list results are deterministic, and existing Task limits
  remain bounded to 100.
- REQ-025: Domain, repository, service, API, schema, rollback, import-isolation,
  Project/Task/health regression, and full validation tests cover this contract
  without weakening existing assertions or framework gates.
- REQ-026: No dependency or production migration framework is added. Metadata
  initialization remains development/test-only; production migration is an
  explicit residual risk and non-goal.

## Acceptance criteria

- [ ] AC-001: Domain tests prove trim, empty rejection, 50/51 boundaries,
  `casefold()` normalization, UTC timestamps, color uppercase, and invalid color.
- [ ] AC-002: Same-Project `Backend`/`backend` conflicts with 409; another
  Project may use the same name; a case-only self rename succeeds.
- [ ] AC-003: Tag CRUD returns the specified status/body shapes and persists
  display name, normalized name, color, and UTC timestamps.
- [ ] AC-004: Tag PATCH distinguishes omitted/color-null, rejects empty body,
  name null, and each immutable/internal field with 422 and no DB change.
- [ ] AC-005: Missing and cross-Project Tag operations return indistinguishable 404s.
- [ ] AC-006: Tag lists order by casefolded name and ID.
- [ ] AC-007: Attach/detach return empty 204, are idempotent, and physically
  create/remove exactly one association row.
- [ ] AC-008: Service and DB both reject cross-Project association; no Task,
  Tag, or association data is partially changed.
- [ ] AC-009: All Task response variants include deterministically ordered Tags
  or an empty list without changing existing response fields.
- [ ] AC-010: `tag_id` returns only associated Tasks and returns 404 for missing
  or foreign Tags.
- [ ] AC-011: Tag filtering composes with all existing filters, sorting, and
  pagination without duplicate Tasks.
- [ ] AC-012: Tag deletion removes associations but retains Tasks and Project;
  Task deletion removes associations but retains Tags.
- [ ] AC-013: A Task-free Project with Tags deletes successfully and cascades
  only its Tags; a Project with Tasks still returns 409 with all data intact.
- [ ] AC-014: Empty and existing SQLite databases initialize Tags safely and
  preserve existing Project/Task rows.
- [ ] AC-015: Schema inspection proves columns, Project-local unique name,
  ownership constraints, composite association uniqueness, cascades, and indexes.
- [ ] AC-016: Forced failures for create/update/delete/attach/detach roll back;
  the same session remains usable.
- [ ] AC-017: Duplicate constraints map to 409 while unexpected repository
  errors produce the existing sanitized 500 response.
- [ ] AC-018: Clean subprocess imports of Tag/Task services and repository
  protocols do not load SQLAlchemy, infrastructure models, or concrete repositories.
- [ ] AC-019: Repository query-count/integration coverage proves bulk Tag loading
  and no per-Task N+1 behavior.
- [ ] AC-020: Existing Project CRUD, Task CRUD/filter/sort/pagination, and
  `/health` regressions pass unchanged.
- [ ] AC-021: Unit/app/integration tests, Ruff, mypy, secrets, build, and
  `make validate` pass within approved scope.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| IDs and API prefix | SQLite integer IDs; endpoints remain below `/api/projects`. | Existing APIs |
| Error body | Existing FastAPI `{"detail": ...}` shape; foreign ownership is reported as not found. | Existing convention |
| DELETE and association success | 204 No Content with an empty body. | Existing Project/Task DELETE |
| UTC serialization | Aware UTC datetimes serialized with trailing `Z`; SQLite hydration restores UTC awareness. | Feature 002 |
| Empty Tag PATCH | 422 and no timestamp/data change. | Existing PATCH convention |
| Name uniqueness | Python `casefold()` of the trimmed name, persisted in `normalized_name`; no locale-dependent database folding. | Approved source |
| Case-only rename | Allowed when the unique owner is the same Tag; `updated_at` changes on successful rename. | Approved source |
| Association ownership | `task_tags` includes `project_id` and composite FKs to Task and Tag ownership keys. | DB-level guarantee |
| Existing Task schema | Initialization creates a unique `(project_id,id)` index with `IF NOT EXISTS` semantics before association use; rows are not rewritten. | No migration framework |
| Task tag loading | Repository returns Task domain objects with immutable Tag tuples via bounded bulk loading, not one query per Task. | N+1 requirement |
| Project delete | Existing Task conflict is checked first; database cascade deletes owned Tags only after Project delete is allowed. | Features 002/003 |
| Migration | Extend explicit metadata/schema initialization only; no Alembic and no production migration. | Repository policy |

No material ambiguity remains. Changes to these decisions require new human approval.

## API contract

```text
POST   /api/projects/{project_id}/tags
GET    /api/projects/{project_id}/tags
GET    /api/projects/{project_id}/tags/{tag_id}
PATCH  /api/projects/{project_id}/tags/{tag_id}
DELETE /api/projects/{project_id}/tags/{tag_id}
PUT    /api/projects/{project_id}/tasks/{task_id}/tags/{tag_id}
DELETE /api/projects/{project_id}/tasks/{task_id}/tags/{tag_id}
```

Tag responses expose `id`, `project_id`, `name`, `color`, `created_at`, and
`updated_at`; they never expose `normalized_name`. Task responses add `tags` as
an array of the same public Tag shape.

## Non-goals

- Authentication, authorization, users, collaboration, sharing, or ownership
  beyond the local Project boundary.
- Tag search, rename propagation events, global Tags, labels with values,
  automatic Tag creation, bulk operations, UI, CLI, import/export, or backup.
- New dependencies, Alembic, production deployment, or production migration.

## Scope

Allowed paths are `src/project_board/domain/**`, `application/**`,
`repositories/**`, `infrastructure/**`, `api/**`, `src/project_board/main.py`,
`tests/app/**`, `README.md`, and `specs/003-task-tags/**`. Framework, policy,
CI, earlier specifications, runtime evidence, secrets, and production settings
are forbidden as enumerated by `validation.toml`.
