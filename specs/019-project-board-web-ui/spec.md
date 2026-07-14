# Feature specification: Project Board Web UI

## Status

Approved. The human-approved Feature 019 request dated 2026-07-15 is the
source of truth; there is no GitHub Issue.

## Goal

Provide a same-origin, dependency-free browser UI for the existing Project,
dashboard, Task query/CRUD, Tag, Comment, and Activity APIs without changing
their contracts or the database schema.

## Requirements

- REQ-001: `GET /` returns a semantic HTML5 application shell with external
  same-origin `/static/app.css` and `/static/app.js`; `/health`, `/docs`,
  `/openapi.json`, and existing API 404 behavior remain intact.
- REQ-002: Only the fixed packaged assets are served with correct media types,
  missing/traversal paths are 404, resolution is package-relative and works in
  source and built wheel/sdist independent of the current directory.
- REQ-003: HTML/static responses use a restrictive self-only CSP without
  unsafe-inline/eval plus nosniff, no-referrer, and frame-denial protections;
  existing business API responses are not globally changed.
- REQ-004: The UI supports Project list/select/create/update/delete and resets
  dependent cross-Project state safely after selection or deletion.
- REQ-005: The UI renders the existing dashboard response as supplied,
  including counts, due buckets, Tags, Comment totals, recent payload-free
  Activity, and `as_of`, and refreshes it after successful mutations.
- REQ-006: Task query uses only `q`, repeatable `status` and `priority`,
  `tag_id`, `due_after`, `due_before`, `sort`, `order`, `limit`, and `offset`,
  retains limit 50 / created_at asc defaults, uses `URLSearchParams`, resets
  offset on filter/Project change, and prevents stale results from winning.
- REQ-007: Task create/detail/update/delete sends only the existing mutable
  fields, supports nullable clears, confirms deletion, prevents double submit,
  and refreshes Task/dashboard/detail state only after success.
- REQ-008: Tag list/create/update/delete and Task attach/detach use only owned
  Tags and existing APIs; server normalization is authoritative and user color
  never becomes an arbitrary style value.
- REQ-009: Comment list/create/update/delete and Activity list operate only on
  the selected Task, preserve existing pagination/order, render body as text,
  never request or display body in Activity, and refresh related state after
  success.
- REQ-010: Frontend state explicitly owns projects, selection, dashboard,
  Tasks/query, Tags, Comments, Activities, loading/errors, and active request
  identities; a shared fetch client safely handles JSON, 204, validation,
  non-2xx, network, and malformed responses without optimistic success.
- REQ-011: API/user strings are constructed with DOM APIs and `textContent`;
  `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`,
  `new Function`, string timers, inline handlers/styles/scripts, unsafe URLs,
  CDNs, analytics, and external assets are forbidden.
- REQ-012: The UI provides semantic landmarks, labels, named buttons, heading
  hierarchy, keyboard controls, visible focus, aria-live status/error output,
  explicit loading/empty/error states, and accessible destructive confirmation.
- REQ-013: Responsive CSS supports desktop/tablet/320px mobile layouts,
  wrapping cards/forms/long content and reduced motion without making horizontal
  scrolling a prerequisite for primary actions.
- REQ-014: Package data includes exactly the required HTML/CSS/JS assets using
  only the minimal setuptools package-data configuration; no dependency,
  version, backend, tooling, or lockfile change is permitted.
- REQ-015: Automated tests cover route/assets/security/package contents, DOM
  safety, accessibility contract, client/state/API mappings, regressions,
  OpenAPI stability, and unchanged database schema without adding a JS runner.
- REQ-016: After automated validation, an available localhost browser is used
  with an isolated temporary database for the approved CRUD/query/activity,
  responsive, keyboard, XSS-literal, cleanup, and health smoke flow; absence of
  a browser must be recorded as SKIPPED, never fabricated.
- REQ-017: Feature risk is medium/infrastructure, auto-merge is disabled, exact
  HEAD validation, weakening inspection, all five review shards, and bounded
  review calls remain mandatory.
- REQ-018: Existing Project/Task/Tag/Comment/Activity/dashboard semantics,
  schemas, defaults, database schema, dependencies, framework, prior specs, and
  runtime evidence remain unchanged.

## Acceptance criteria

- [ ] AC-001: `/`, fixed assets, missing/traversal assets, health/docs/OpenAPI,
  source checkout, changed cwd, and built archives pass their route tests.
- [ ] AC-002: CSP and security headers pass with no unsafe token, inline code,
  external origin, or impact on existing API responses.
- [ ] AC-003: Project navigation and dashboard work across loading, empty,
  success, validation, conflict, not-found, and server/network failure states.
- [ ] AC-004: Task query emits only approved names/defaults, handles repeated
  filters/pagination, and ignores or cancels stale responses.
- [ ] AC-005: Task and Tag CRUD/attachment use only existing payloads/routes,
  update dependent state after success, and preserve failure state.
- [ ] AC-006: Comment CRUD and Activity display preserve pagination/order,
  deletion history, payload-free Activity, and safe multiline literal text.
- [ ] AC-007: Shared state/client resets selection correctly, handles 204 and
  structured errors, omits undefined fields, and blocks duplicate mutations.
- [ ] AC-008: Static inspection and integration tests prove all approved XSS
  payloads render literally and forbidden DOM/code APIs are absent.
- [ ] AC-009: Semantic accessibility, focus, aria-live, responsive layout, and
  reduced-motion requirements pass automated contract checks and browser smoke.
- [ ] AC-010: Wheel and sdist include all assets with no dependency, schema,
  API contract, framework, or unrelated scope change.
- [ ] AC-011: Existing framework/app/integration/import-isolation/secret/build
  and OpenAPI operation regressions pass without weakening tests or gates.
- [ ] AC-012: Local browser smoke completes using only temporary data and the
  result is honestly recorded in the validation log.
- [ ] AC-013: Exact-HEAD validation, accepted→weakening→review order, all five
  review shards, and CI pass before the ready-for-review PR waits for a human.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| API prefix | Use the existing `/api/projects` routes and exact nested paths. | Current FastAPI router |
| Task query | Use only q/status/priority/tag_id/due_after/due_before/sort/order/limit/offset; defaults remain limit 50 and created_at asc. | Features 002/004 contract |
| Assets | Use `project_board.web` package resources and exact asset routes, not a catch-all mount. | Traversal and packaging requirements |
| Confirmation | Use accessible native dialog or an explicit in-page two-step control; never browser `confirm()` as the only accessible path. | Approved accessibility requirement |
| Tag color | Display the validated color string and a fixed CSS swatch treatment only when safe; do not create user-authored style text. | Existing API and DOM safety |
| Browser | Run a localhost smoke test after automated validation when the in-app browser is available. | Human approval |

## Scope

Allowed: minimal UI routing under `src/project_board/api/**`, packaged assets
under `src/project_board/web/**`, app unit/integration tests, minimal README,
package-data-only `pyproject.toml`, and this spec directory. All business/domain,
database, framework, CI, secret, prior-spec, and runtime-evidence paths are
forbidden.

