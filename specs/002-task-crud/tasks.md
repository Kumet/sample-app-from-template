# Tasks: Task CRUD

## Rules

- Execute tasks in dependency order with one focused implementation commit each.
- Use only the validations and paths declared below and in `validation.toml`.
- Do not weaken tests, review, evidence, or approval gates.
- Stop for human review if implementation needs framework changes, a migration
  framework, new dependencies, or scope/specification expansion.
- This feature is high-risk and must stop before push until explicitly approved.

## Tasks

- [x] T001: Implement Task domain model, enums, errors, and repository interface.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-017, REQ-018
  - Acceptance criteria: AC-003, AC-004, AC-006, AC-007, AC-008, AC-019, AC-020
  - Validation: unit, app
  - Dependencies: none
  - Allowed paths: `src/project_board/domain/**`, `src/project_board/repositories/project_repository.py`, `src/project_board/repositories/task_repository.py`, `tests/app/unit/**`
- [x] T002: Add Task SQLAlchemy mapping, schema registration, foreign-key enforcement, and indexes.
  - Requirements: REQ-001, REQ-015, REQ-020, REQ-021
  - Acceptance criteria: AC-001, AC-002, AC-017
  - Validation: integration, full
  - Dependencies: T001
  - Allowed paths: `src/project_board/infrastructure/**`, `tests/app/integration/**`
- [x] T003: Implement transactional SQLAlchemy Task repository and rollback behavior.
  - Requirements: REQ-006, REQ-009, REQ-010, REQ-011, REQ-012, REQ-013, REQ-016, REQ-017, REQ-022
  - Acceptance criteria: AC-009, AC-012, AC-013, AC-014, AC-015, AC-018, AC-021, AC-022
  - Validation: unit, integration, full
  - Dependencies: T001, T002
  - Allowed paths: `src/project_board/repositories/**`, `src/project_board/infrastructure/**`, `tests/app/unit/**`, `tests/app/integration/**`
- [x] T004: Implement Task application service and omitted/null update semantics.
  - Requirements: REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-014, REQ-016, REQ-017, REQ-018
  - Acceptance criteria: AC-003, AC-005, AC-009, AC-010, AC-011, AC-012, AC-016, AC-018, AC-019
  - Validation: unit, app
  - Dependencies: T001, T003
  - Allowed paths: `src/project_board/application/**`, `src/project_board/domain/**`, `tests/app/unit/**`
- [x] T005: Add nested Task create/detail schemas, dependencies, routes, and error mapping.
  - Requirements: REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-019, REQ-023
  - Acceptance criteria: AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-020, AC-021
  - Validation: app, integration
  - Dependencies: T004
  - Allowed paths: `src/project_board/api/**`, `src/project_board/main.py`, `tests/app/integration/**`
- [x] T006: Add Task PATCH/DELETE API and immutable-field validation.
  - Requirements: REQ-007, REQ-008, REQ-009, REQ-016, REQ-017, REQ-019, REQ-023
  - Acceptance criteria: AC-010, AC-011, AC-012, AC-018, AC-021
  - Validation: app, integration
  - Dependencies: T004, T005
  - Allowed paths: `src/project_board/api/**`, `src/project_board/application/**`, `tests/app/unit/**`, `tests/app/integration/**`
- [x] T007: Implement Task list filters, pagination, and deterministic sorting.
  - Requirements: REQ-004, REQ-010, REQ-011, REQ-012, REQ-013, REQ-022, REQ-023
  - Acceptance criteria: AC-008, AC-013, AC-014, AC-015, AC-023
  - Validation: unit, app, integration
  - Dependencies: T003, T005
  - Allowed paths: `src/project_board/api/**`, `src/project_board/application/**`, `src/project_board/repositories/**`, `tests/app/**`
- [x] T008: Protect Project deletion with 409 conflict while Tasks exist.
  - Requirements: REQ-014, REQ-015, REQ-016, REQ-019, REQ-023
  - Acceptance criteria: AC-016, AC-017, AC-018, AC-021, AC-023
  - Validation: unit, app, integration
  - Dependencies: T002, T003, T004
  - Allowed paths: `src/project_board/api/**`, `src/project_board/application/**`, `src/project_board/domain/**`, `src/project_board/repositories/**`, `tests/app/**`
- [x] T009: Complete domain, service, repository, API, rollback, import-isolation, persistence, and regression tests.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-012, REQ-013, REQ-014, REQ-015, REQ-016, REQ-017, REQ-018, REQ-019, REQ-020, REQ-022, REQ-023, REQ-024
  - Acceptance criteria: AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024
  - Validation: unit, app, integration, full
  - Dependencies: T005, T006, T007, T008
  - Allowed paths: `tests/app/**`, `src/project_board/**`
- [x] T010: Update approved documentation and complete full validation and review readiness.
  - Requirements: REQ-021, REQ-024, REQ-025
  - Acceptance criteria: AC-001, AC-024, AC-025
  - Validation: full
  - Dependencies: T009
  - Allowed paths: `README.md`, `docs/architecture.md`, `specs/002-task-crud/**`
