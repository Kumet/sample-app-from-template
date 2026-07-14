# Validation log: 018-project-dashboard-analytics

## Specification phase

- Source: human-approved Feature 018 prompt dated 2026-07-15; no GitHub Issue.
- Clarification: identifier 018 avoids occupied framework Features 006-017.
- Existing contracts fixed: integer IDs, `/api/projects` prefix,
  `TaskStatus.DONE` terminal policy, enum ordering, normalized Tag ordering,
  payload-free Activity response, request-scoped Session, and UTC helper.
- Risk: medium; infrastructure domain; auto-merge disabled.
- Schema/migration/dependency changes: forbidden and not planned.
- Implementation: not started at this snapshot.
| 1 | T001 | PASS | task validation passed |
| 1 | T002 | PASS | task validation passed |
| 1 | T003 | PASS | task validation passed |
| 1 | T004 | FAIL | uery_rejects_unbounded_or_non_integer_limits( + limit: object, +) -> None: + repository = SQLAlchemyProjectDashboardRepository( + cast(Session, QueryForbiddenSession()) + ) + + with pytest.raises(DashboardInvariantError, match="activity limit"): + repository.list_recent_activities(1, limit) # type: ignore[arg-type] ERROR: Selected model is at capacity. Please try a different model. ERROR: Selected model is at capacity. Please try a different model. tokens used 64,088 |
| 2 | T004 | PASS | task validation passed |
| 1 | T005 | PASS | task validation passed |
| 1 | T006 | PASS | task validation passed |
| 1 | T007 | PASS | task validation passed |
| 1 | T008 | PASS | task validation passed |
