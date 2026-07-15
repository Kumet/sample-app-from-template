# Tasks: Containerized operational readiness

## Rules

- Execute in dependency order with one focused commit per task.
- Never change application, schema, dependency, framework, policy, or prior
  runtime evidence paths.
- Real container smoke remains required; mocks cover cleanup branches only.

## Tasks

- [x] T001: Fix the approved specification, plan, tasks, validation, and scope contract.
  - Requirements: REQ-001, REQ-003, REQ-006, REQ-008, REQ-012, REQ-014, REQ-017
  - Acceptance criteria: AC-010, AC-012
  - Validation: unit
  - Dependencies: none
  - Allowed paths: `specs/020-containerized-operational-readiness/**`
- [x] T002: Add the multi-stage non-root Dockerfile and deny-oriented build context.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-016
  - Acceptance criteria: AC-001, AC-002
  - Validation: unit
  - Dependencies: T001
  - Allowed paths: `Dockerfile`, `.dockerignore`, `tests/app/operations/**`
- [x] T003: Add localhost-only hardened Compose and structural regressions.
  - Requirements: REQ-003, REQ-004, REQ-006, REQ-018
  - Acceptance criteria: AC-003
  - Validation: unit
  - Dependencies: T002
  - Allowed paths: `compose.yaml`, `tests/app/operations/**`
- [x] T004: Implement unique-resource real HTTP and persistence smoke lifecycle.
  - Requirements: REQ-008, REQ-009, REQ-010, REQ-018
  - Acceptance criteria: AC-004, AC-005
  - Validation: unit
  - Dependencies: T002, T003
  - Allowed paths: `scripts/operations/**`, `tests/app/operations/**`
- [ ] T005: Add opt-in Make container targets without changing ordinary validation.
  - Requirements: REQ-007, REQ-011
  - Acceptance criteria: AC-006
  - Validation: unit, container-build
  - Dependencies: T002, T004
  - Allowed paths: `Makefile`, `tests/app/operations/**`
- [ ] T006: Add a separate bounded real-container CI job and CI safety regressions.
  - Requirements: REQ-010, REQ-011, REQ-012, REQ-018
  - Acceptance criteria: AC-005, AC-007
  - Validation: unit
  - Dependencies: T004, T005
  - Allowed paths: `.github/workflows/ci.yml`, `tests/app/operations/**`
- [ ] T007: Document build, start, verify, stop, persistence, and destructive cleanup.
  - Requirements: REQ-013, REQ-018
  - Acceptance criteria: AC-008
  - Validation: unit
  - Dependencies: T003, T005
  - Allowed paths: `README.md`, `tests/app/operations/**`
- [ ] T008: Prove real build, runtime boundary, HTTP flow, and restart persistence.
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-008, REQ-009, REQ-010
  - Acceptance criteria: AC-001, AC-002, AC-003, AC-004, AC-005
  - Validation: container-build, container-smoke
  - Dependencies: T005, T006, T007
  - Allowed paths: `Dockerfile`, `.dockerignore`, `compose.yaml`, `Makefile`, `scripts/operations/**`, `tests/app/operations/**`, `specs/020-containerized-operational-readiness/**`
- [ ] T009: Run browser acceptance with temporary data and record honest results.
  - Requirements: REQ-014, REQ-015, REQ-016
  - Acceptance criteria: AC-009, AC-012
  - Validation: integration
  - Dependencies: T008
  - Allowed paths: `specs/020-containerized-operational-readiness/**`
- [ ] T010: Complete regressions, exact evidence, independent review, and PR readiness.
  - Requirements: REQ-011, REQ-012, REQ-016, REQ-017, REQ-018
  - Acceptance criteria: AC-006, AC-007, AC-010, AC-011, AC-012
  - Validation: full, container-smoke
  - Dependencies: T008, T009
  - Allowed paths: `README.md`, `specs/020-containerized-operational-readiness/**`, `tests/app/operations/**`
