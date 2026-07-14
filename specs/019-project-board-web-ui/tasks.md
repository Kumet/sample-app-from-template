# Tasks: Project Board Web UI

## Rules

- Execute in dependency order with one focused commit per task.
- Preserve all existing APIs, defaults, database schema, dependencies, tests,
  gates, prior runtime evidence, and package metadata outside package data.
- Stop for business API, schema, dependency, framework, or scope changes.

## Tasks

- [x] T001: Add package-relative fixed Web routes and HTML/static security headers.
  - Requirements: REQ-001, REQ-002, REQ-003
  - Acceptance criteria: AC-001, AC-002
  - Validation: unit, app
  - Dependencies: none
  - Allowed paths: `src/project_board/api/**`, `src/project_board/web/**`, `tests/app/**`
- [x] T002: Build the semantic accessible HTML application shell.
  - Requirements: REQ-011, REQ-012
  - Acceptance criteria: AC-008, AC-009
  - Validation: unit, app
  - Dependencies: T001
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T003: Implement the safe shared API client, state model, error handling, and request identity controls.
  - Requirements: REQ-010, REQ-011
  - Acceptance criteria: AC-007, AC-008
  - Validation: unit, app
  - Dependencies: T002
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T004: Implement Project navigation and dashboard rendering/refresh.
  - Requirements: REQ-004, REQ-005
  - Acceptance criteria: AC-003
  - Validation: app, integration
  - Dependencies: T003
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T005: Implement Task query, pagination, stale-request handling, and Task CRUD.
  - Requirements: REQ-006, REQ-007
  - Acceptance criteria: AC-004, AC-005
  - Validation: app, integration
  - Dependencies: T003, T004
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T006: Implement Tag CRUD and Task attach/detach flows.
  - Requirements: REQ-008
  - Acceptance criteria: AC-005
  - Validation: app, integration
  - Dependencies: T005
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T007: Implement Comment CRUD, Activity list, pagination, and safe literal content rendering.
  - Requirements: REQ-009, REQ-011
  - Acceptance criteria: AC-006, AC-008
  - Validation: app, integration
  - Dependencies: T005
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T008: Add responsive, focus-visible, reduced-motion-aware presentation and explicit states.
  - Requirements: REQ-012, REQ-013
  - Acceptance criteria: AC-009
  - Validation: app
  - Dependencies: T004, T005, T006, T007
  - Allowed paths: `src/project_board/web/**`, `tests/app/**`
- [x] T009: Configure package data and prove archive, security, UI contract, API, OpenAPI, and schema regressions.
  - Requirements: REQ-002, REQ-014, REQ-015, REQ-018
  - Acceptance criteria: AC-001, AC-002, AC-010, AC-011
  - Validation: unit, app, integration, full
  - Dependencies: T001, T002, T003, T004, T005, T006, T007, T008
  - Allowed paths: `pyproject.toml`, `tests/app/**`, `src/project_board/api/**`, `src/project_board/web/**`
- [ ] T010: Update usage docs, run full validation/browser smoke, and prepare exact-HEAD review evidence.
  - Requirements: REQ-016, REQ-017, REQ-018
  - Acceptance criteria: AC-012, AC-013
  - Validation: full
  - Dependencies: T009
  - Allowed paths: `README.md`, `specs/019-project-board-web-ui/**`, `tests/app/**`

