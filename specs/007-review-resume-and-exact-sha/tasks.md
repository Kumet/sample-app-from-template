# Tasks: Review resume and exact-SHA validation

## Tasks

- [x] T001: Define canonical review identity and event-backed reuse
  - Requirements: REQ-001, REQ-002, REQ-003, REQ-004, REQ-011, REQ-012, REQ-019, REQ-020
  - Validation: unit
- [x] T002: Implement bounded shard retry and integration ordering
  - Requirements: REQ-005, REQ-006, REQ-007, REQ-008, REQ-009, REQ-010
  - Validation: unit
- [x] T003: Add timeout diagnostics and process-group termination
  - Requirements: REQ-013, REQ-014, REQ-015, REQ-016, REQ-017, REQ-018
  - Validation: unit, integration
- [x] T004: Implement exact-HEAD validation finalization and delivery gates
  - Requirements: REQ-021, REQ-022, REQ-023, REQ-024, REQ-025, REQ-026, REQ-027, REQ-028, REQ-029
  - Validation: unit, integration
- [x] T005: Complete regression tests, documentation, and final validation
  - Requirements: REQ-001, REQ-029
  - Validation: unit, integration, full
- [x] T006: Implement tracked evidence snapshot and dedicated final-validation events
  - Requirements: REQ-030, REQ-031, REQ-032, REQ-033, REQ-034
  - Validation: unit, integration
- [ ] T007: Extend canonical review identity and fail-closed prerequisite checks
  - Requirements: REQ-034, REQ-035
  - Validation: unit, integration
- [ ] T008: Centralize review exception redaction at persistence boundaries
  - Requirements: REQ-036
  - Validation: unit
- [ ] T009: Complete mutation, evidence, redaction, and regression tests
  - Requirements: REQ-030, REQ-031, REQ-032, REQ-033, REQ-034, REQ-035, REQ-036
  - Validation: unit, integration, full
