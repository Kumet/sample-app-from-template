# Tasks: Project CRUD

## Rules

- Execute tasks in dependency order and keep each implementation commit focused.
- Use only validations named in `validation.toml`.
- Do not change Makefile, repository policy, CI, production configuration, or
  any path outside the approved scope.
- Do not weaken, skip, delete, or relax tests.
- Stop for human review if scope, migration policy, or the approved
  specification must change.
- Treat the feature as high-risk and do not bypass any pre-push approval gate.

## Tasks

- [x] T001: Add SQLAlchemy and implement database engine, session, and explicit schema initialization.
  - Requirements: REQ-001, REQ-015, REQ-017, REQ-020
  - Validation: integration, full
- [x] T002: Implement the Project domain model and domain errors.
  - Requirements: REQ-002, REQ-003, REQ-004, REQ-015, REQ-019
  - Validation: unit
- [x] T003: Implement the repository interface, SQLAlchemy model, and transactional repository.
  - Requirements: REQ-002, REQ-006, REQ-013, REQ-015, REQ-016, REQ-017, REQ-019
  - Validation: unit, integration
- [ ] T004: Implement the Project application service.
  - Requirements: REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-013, REQ-016, REQ-019
  - Validation: unit
- [ ] T005: Implement API schemas, dependencies, routes, and error mapping while preserving health.
  - Requirements: REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010, REQ-011, REQ-012, REQ-014, REQ-018
  - Validation: integration
- [ ] T006: Complete unit, repository, and API integration coverage with isolated databases.
  - Requirements: REQ-001, REQ-003, REQ-004, REQ-006, REQ-010, REQ-011, REQ-012, REQ-015, REQ-016, REQ-017, REQ-018, REQ-019
  - Validation: unit, integration, full
- [ ] T007: Update architecture and README documentation and run final validation.
  - Requirements: REQ-013, REQ-014, REQ-017, REQ-018, REQ-020
  - Validation: full
