# Tasks: Project bootstrap

## Rules

- Execute tasks in dependency order.
- Do not add product features, persistence, or dependencies outside the approved scope.
- Each task must pass its named validation before completion.
- Stop for human review if implementation requires scope or specification changes.

## Tasks

- [x] T001: Create the Python source-layout package and `pyproject.toml`.
  - Requirements: REQ-001, REQ-004
  - Validation: unit
- [x] T002: Implement the minimal FastAPI application and health endpoint.
  - Requirements: REQ-002, REQ-003
  - Validation: unit
- [x] T003: Add application unit and integration tests while preserving framework tests.
  - Requirements: REQ-003, REQ-009
  - Validation: unit, integration
- [x] T004: Configure executable Make quality gates and repository quality policy.
  - Requirements: REQ-004, REQ-005, REQ-006, REQ-009, REQ-010
  - Validation: unit, integration, full
- [x] T005: Update read-only GitHub Actions and developer documentation.
  - Requirements: REQ-007, REQ-008
  - Validation: full
- [x] T006: Run doctor, build, runtime health smoke test, and full validation.
  - Requirements: REQ-003, REQ-010
  - Validation: integration, full
