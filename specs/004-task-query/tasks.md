# Tasks: Task query

## Rules

- Execute in dependency order and create one focused commit per task.
- Preserve Feature 002 defaults and Feature 003 Tag behavior.
- Do not add aliases, migrations, dependencies, framework changes, or schema changes.
- Stop for scope/specification expansion or repeated failures; do not weaken gates.

## Tasks

- [x] T001: Extend the infrastructure-neutral typed Task query contract and unit tests.
  - Requirements: REQ-003, REQ-005, REQ-006, REQ-008, REQ-013, REQ-015
  - Acceptance criteria: AC-003, AC-005, AC-006, AC-012
  - Validation: unit, app
  - Dependencies: none
  - Allowed paths: `src/project_board/domain/**`, `src/project_board/repositories/**`, `tests/app/unit/**`
- [x] T002: Add backward-compatible API parsing for `q` and repeated status/priority.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-005, REQ-006, REQ-010
  - Acceptance criteria: AC-001, AC-002, AC-003, AC-005
  - Validation: unit, app
  - Dependencies: T001
  - Allowed paths: `src/project_board/api/**`, `tests/app/unit/**`, `tests/app/integration/**`
- [x] T003: Implement bound literal search and repeated enum predicates in SQLAlchemy.
  - Requirements: REQ-004, REQ-005, REQ-006, REQ-011, REQ-013, REQ-016
  - Acceptance criteria: AC-004, AC-005, AC-006, AC-010
  - Validation: unit, integration
  - Dependencies: T001, T002
  - Allowed paths: `src/project_board/repositories/**`, `tests/app/**`
- [ ] T004: Add title sorting and preserve deterministic due/priority/tie-break behavior.
  - Requirements: REQ-002, REQ-008, REQ-009, REQ-010, REQ-011
  - Acceptance criteria: AC-002, AC-006, AC-007, AC-008
  - Validation: app, integration
  - Dependencies: T003
  - Allowed paths: `src/project_board/repositories/**`, `src/project_board/api/**`, `tests/app/**`
- [ ] T005: Prove Project/Tag isolation and complete filter composition regressions.
  - Requirements: REQ-007, REQ-008, REQ-011, REQ-012, REQ-016
  - Acceptance criteria: AC-006, AC-009, AC-014
  - Validation: app, integration
  - Dependencies: T003, T004
  - Allowed paths: `src/project_board/application/**`, `src/project_board/api/**`, `tests/app/**`
- [ ] T006: Add query-count, DB-side execution, and import-isolation regressions.
  - Requirements: REQ-013, REQ-014, REQ-015, REQ-016, REQ-017
  - Acceptance criteria: AC-010, AC-011, AC-012, AC-013
  - Validation: unit, integration, full
  - Dependencies: T003, T004
  - Allowed paths: `src/project_board/repositories/**`, `tests/app/**`
- [ ] T007: Complete API compatibility, boundaries, pagination, and regression coverage.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-012, REQ-018
  - Acceptance criteria: AC-001, AC-002, AC-003, AC-006, AC-007, AC-008, AC-009, AC-014
  - Validation: unit, app, integration, full
  - Dependencies: T002, T004, T005, T006
  - Allowed paths: `src/project_board/api/**`, `src/project_board/application/**`, `tests/app/**`
- [ ] T008: Finalize documentation, full validation, evidence, and review readiness.
  - Requirements: REQ-017, REQ-018
  - Acceptance criteria: AC-013, AC-014, AC-015, AC-016
  - Validation: full
  - Dependencies: T007
  - Allowed paths: `README.md`, `specs/004-task-query/**`
