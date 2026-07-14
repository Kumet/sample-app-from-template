# Plan: Project Board Web UI

## Existing architecture and constraints

- FastAPI is composed by `project_board.main.create_app`; business routes use
  `/api/projects` and dependency-injected services.
- Project, dashboard, Task query/CRUD, Tag/attachment, Comment, and Activity
  endpoints already satisfy the UI contract. No business API change is needed.
- Setuptools discovers `src/` packages; package data is not configured yet.
- Assets will live in `project_board.web` and be read by fixed-name,
  package-relative resource routes. No catch-all static filesystem access is
  required.

## Implementation design

1. Add an API-layer Web router for `/`, `/static/app.css`, and
   `/static/app.js`. Read only a fixed allowlist via `importlib.resources` and
   set HTML/static-specific security headers.
2. Add a semantic HTML shell with external assets, landmarks, labelled forms,
   aria-live output, empty/loading/error regions, and accessible destructive
   confirmation.
3. Implement one module-scoped state object, deterministic render functions,
   and a same-origin fetch helper that handles 204/JSON/errors and never treats
   failures as success.
4. Map existing APIs exactly. Build Task queries with `URLSearchParams`, reset
   offsets, and use request identities plus `AbortController` for stale lists.
5. Implement Project/dashboard, Task, Tag, Comment, and Activity flows with
   dependent-state resets and refreshes only after successful mutations.
6. Use createElement/textContent/replaceChildren throughout. Keep content out
   of HTML/style/URL/event-handler strings and prohibit all unsafe DOM/code APIs.
7. Add responsive, keyboard-visible, reduced-motion-aware CSS using a neutral
   system-font design and fixed classes.
8. Configure only setuptools package data. Add Python route/static/security,
   build archive, DOM-contract, state/API mapping, and regression tests.
9. Update README minimally, run full validation, then exercise the built UI on
   localhost with a temporary SQLite database and clean up only smoke data.

## Validation and rollback

- Targeted route, security, archive, and UI contract tests run before full
  `make validate`; no JS runtime dependency is added.
- Browser smoke uses an isolated temporary database and same-origin server.
- Rollback is ordinary commit reversion: no schema/data migration exists.
- Stop for any business API/schema/dependency/framework/scope requirement.
- Risk remains medium (`infrastructure`), auto-merge remains false, and the PR
  may be pushed only after exact-HEAD evidence and all five review shards pass.

