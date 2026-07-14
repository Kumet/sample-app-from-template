# Tasks: Project dashboard analytics

## Rules

- Execute in dependency order with one focused commit per task.
- Preserve all existing APIs and database schema.
- Do not weaken tests, evidence, review, risk, or approval gates.
- Stop for schema, dependency, framework, specification, or scope changes.

## Tasks

- [x] T001: Add typed dashboard aggregates, terminal policy, invariants, and repository protocol.
  - Requirements: REQ-002, REQ-004, REQ-005, REQ-006, REQ-007, REQ-013
  - Acceptance criteria: AC-003, AC-004, AC-005, AC-009
  - Validation: unit, app
  - Dependencies: none
  - Allowed paths: `src/project_board/domain/**`, `src/project_board/repositories/**`, `tests/app/unit/**`
- [ ] T002: Implement set-based SQLAlchemy Task/status/priority/due aggregates.
  - Requirements: REQ-004, REQ-005, REQ-006, REQ-007, REQ-014, REQ-015
  - Acceptance criteria: AC-004, AC-005, AC-010
  - Validation: unit, integration
  - Dependencies: T001
  - Allowed paths: `src/project_board/repositories/**`, `tests/app/integration/**`
- [ ] T003: Implement Tag and Comment aggregate queries with deterministic ownership confinement.
  - Requirements: REQ-008, REQ-009, REQ-014, REQ-015
  - Acceptance criteria: AC-006, AC-007, AC-010
  - Validation: integration
  - Dependencies: T001, T002
  - Allowed paths: `src/project_board/repositories/**`, `tests/app/integration/**`
- [ ] T004: Implement bounded recent Activity query and payload-free typed mapping.
  - Requirements: REQ-010, REQ-011, REQ-014, REQ-015
  - Acceptance criteria: AC-002, AC-008, AC-010
  - Validation: unit, integration
  - Dependencies: T001, T003
  - Allowed paths: `src/project_board/repositories/**`, `tests/app/**`
- [ ] T005: Implement ProjectDashboardService, single clock, Project check, and result invariants.
  - Requirements: REQ-001, REQ-003, REQ-004, REQ-007, REQ-012, REQ-013, REQ-016
  - Acceptance criteria: AC-001, AC-003, AC-004, AC-005, AC-009, AC-011
  - Validation: unit, app
  - Dependencies: T001, T002, T003, T004
  - Allowed paths: `src/project_board/application/**`, `src/project_board/domain/**`, `tests/app/unit/**`
- [ ] T006: Add dashboard response schemas, dependency wiring, route, and activity_limit validation.
  - Requirements: REQ-001, REQ-002, REQ-010, REQ-011, REQ-012, REQ-013
  - Acceptance criteria: AC-001, AC-002, AC-008, AC-009
  - Validation: app, integration
  - Dependencies: T005
  - Allowed paths: `src/project_board/api/**`, `tests/app/**`
- [ ] T007: Prove query-count, parameter binding, no-mutation, determinism, isolation, and import boundaries.
  - Requirements: REQ-014, REQ-015, REQ-016, REQ-017, REQ-018, REQ-020
  - Acceptance criteria: AC-009, AC-010, AC-011, AC-012, AC-014
  - Validation: unit, app, integration, full
  - Dependencies: T002, T003, T004, T005, T006
  - Allowed paths: `src/project_board/**`, `tests/app/**`
- [ ] T008: Update minimal documentation and complete full validation/evidence/review readiness.
  - Requirements: REQ-017, REQ-018, REQ-019, REQ-020
  - Acceptance criteria: AC-012, AC-013, AC-014, AC-015, AC-016
  - Validation: full
  - Dependencies: T007
  - Allowed paths: `README.md`, `specs/018-project-dashboard-analytics/**`
