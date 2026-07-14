# Tasks: Project-scoped Task Tags

## Rules

- Execute in dependency order and create one focused commit per task.
- Use only declared validations and allowed paths.
- Do not weaken tests, evidence, review, or approval gates.
- Stop for new dependencies, framework changes, migration-policy changes, or
  scope/specification expansion.
- High risk must stop before push.

## Tasks

- [x] T001: Implement Tag domain rules, errors, and repository interface.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-022
  - Acceptance criteria: AC-001, AC-002, AC-018
  - Validation: unit, app
  - Dependencies: none
  - Allowed paths: `src/project_board/domain/**`, `src/project_board/repositories/**`, `tests/app/unit/**`
- [x] T002: Add Tag and association ORM models, ownership constraints, indexes, and safe schema initialization.
  - Requirements: REQ-009, REQ-011, REQ-018, REQ-019, REQ-026
  - Acceptance criteria: AC-008, AC-014, AC-015
  - Validation: integration, full
  - Dependencies: T001
  - Allowed paths: `src/project_board/infrastructure/**`, `src/project_board/repositories/task_repository.py`, `tests/app/integration/**`
- [x] T003: Implement transactional SQLAlchemy Tag CRUD repository.
  - Requirements: REQ-003, REQ-005, REQ-006, REQ-008, REQ-020, REQ-021
  - Acceptance criteria: AC-002, AC-003, AC-005, AC-006, AC-016, AC-017
  - Validation: unit, integration, full
  - Dependencies: T001, T002
  - Allowed paths: `src/project_board/repositories/**`, `src/project_board/infrastructure/**`, `tests/app/**`
- [x] T004: Extend Task persistence with bulk Tag loading and `tag_id` filtering.
  - Requirements: REQ-012, REQ-013, REQ-014, REQ-024
  - Acceptance criteria: AC-009, AC-010, AC-011, AC-019
  - Validation: unit, integration, full
  - Dependencies: T001, T002, T003
  - Allowed paths: `src/project_board/domain/**`, `src/project_board/repositories/**`, `tests/app/**`
- [x] T005: Implement Project-scoped Tag CRUD application service.
  - Requirements: REQ-001, REQ-003, REQ-005, REQ-006, REQ-007, REQ-020, REQ-022
  - Acceptance criteria: AC-002, AC-003, AC-004, AC-005, AC-016, AC-018
  - Validation: unit, app
  - Dependencies: T001, T003
  - Allowed paths: `src/project_board/application/**`, `src/project_board/domain/**`, `tests/app/unit/**`
- [x] T006: Implement idempotent attach/detach service and cross-Project concealment.
  - Requirements: REQ-009, REQ-010, REQ-011, REQ-020, REQ-022
  - Acceptance criteria: AC-007, AC-008, AC-016, AC-018
  - Validation: unit, app, integration
  - Dependencies: T003, T005
  - Allowed paths: `src/project_board/application/**`, `src/project_board/repositories/**`, `tests/app/**`
- [x] T007: Add Tag CRUD and Task-Tag association API schemas, wiring, routes, and error mapping.
  - Requirements: REQ-004, REQ-005, REQ-006, REQ-007, REQ-010, REQ-021, REQ-023
  - Acceptance criteria: AC-003, AC-004, AC-005, AC-007, AC-017
  - Validation: app, integration
  - Dependencies: T005, T006
  - Allowed paths: `src/project_board/api/**`, `src/project_board/main.py`, `tests/app/**`
- [x] T008: Integrate ordered Tags into Task responses and add composable `tag_id` list filtering.
  - Requirements: REQ-012, REQ-013, REQ-014, REQ-024
  - Acceptance criteria: AC-009, AC-010, AC-011, AC-019
  - Validation: unit, app, integration
  - Dependencies: T004, T007
  - Allowed paths: `src/project_board/api/**`, `src/project_board/application/**`, `src/project_board/repositories/**`, `tests/app/**`
- [x] T009: Complete deletion cascades, rollback, physical-row, schema, import-isolation, and regression tests.
  - Requirements: REQ-011, REQ-015, REQ-016, REQ-017, REQ-018, REQ-019, REQ-020, REQ-021, REQ-022, REQ-025
  - Acceptance criteria: AC-007, AC-008, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-020
  - Validation: unit, app, integration, full
  - Dependencies: T002, T003, T004, T006, T007, T008
  - Allowed paths: `src/project_board/**`, `tests/app/**`
- [ ] T010: Update documentation and complete full validation/review readiness.
  - Requirements: REQ-024, REQ-025, REQ-026
  - Acceptance criteria: AC-019, AC-020, AC-021
  - Validation: full
  - Dependencies: T009
  - Allowed paths: `README.md`, `specs/003-task-tags/**`
