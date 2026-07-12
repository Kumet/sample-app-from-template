# Glossary

These definitions establish shared language for Local Project Board. They do
not replace feature specifications. If required behavior is absent or
ambiguous, an AI agent must not infer it; the point is **Human-required** and
must be resolved in an **Approved specification** before implementation.

| Term | Meaning | Notes and boundaries |
|---|---|---|
| Project | A named container used to organize related Tasks. | A name is required. The behavior of related Tasks when a Project is deleted is not yet defined and must be decided in an Approved specification. |
| Task | A unit of work belonging to an existing Project. | A title is required. A Task cannot be added to a Project that does not exist. Any fields or lifecycle behavior not documented here require a specification. |
| Task status | The current Kanban stage of a Task. | Exactly one of `todo`, `doing`, or `done`. Transition restrictions, if any, are not yet defined. |
| Todo | The Task status `todo`, representing work that has not started. | Ordering and limits within this column are not yet defined. |
| Doing | The Task status `doing`, representing work currently in progress. | Work-in-progress limits are not yet defined. |
| Done | The Task status `done`, representing completed work. | Completion timestamps and reopening behavior are not yet defined. |
| Priority | A classification of a Task's relative importance. | Exactly one of `low`, `medium`, or `high`. The default priority and sort behavior must be decided in a specification. |
| Due date | An optional date or date-time by which a Task is expected to be completed. | Values are handled internally in UTC. Input precision and user-facing timezone behavior are not yet defined. |
| Tag | A non-empty label assigned to a Task for organization and filtering. | The same Tag cannot be assigned to one Task more than once. Case sensitivity, normalization, and global uniqueness are not yet defined. |
| Overdue | A possible classification for a Task whose Due date has passed. | Whether Done Tasks are overdue, and the exact timezone and comparison boundary, must be decided in an Approved specification. AI agents must not infer these rules. |
| Import | Loading application data from a user-selected local JSON file. | The operation is atomic: on any failure, existing data remains unchanged. Validation, conflict, and compatibility policies require an Approved specification. |
| Export | Writing application data to a user-selected local JSON file. | Exported data must be restorable through Import. The schema and versioning policy require an Approved specification. |
| Backup | Creating a recoverable local copy of application data. | Format, retention, overwrite, and consistency behavior are not yet defined. |
| Restore | Replacing or recovering local application data from a Backup. | Validation, confirmation, rollback, and conflict behavior are not yet defined. |
| Human-required | A decision or action that an AI agent must stop and refer to a human because behavior is ambiguous, sensitive, or outside the approved scope. | This includes undefined domain rules and any requested specification or scope expansion. |
| Approved specification | A feature contract that a human has reviewed and explicitly approved as the source of truth for implementation. | It defines requirements, acceptance criteria, scope, risks, tasks, and validation. Approval must not be inferred from an unreviewed draft. |

## Rules AI agents must not infer

At minimum, AI agents must seek human clarification and specification approval
for the following:

- What happens to Tasks when their Project is deleted.
- The user-facing timezone and Due date precision.
- The exact definition of Overdue.
- Defaults, ordering, normalization, transition restrictions, and conflict
  behavior not explicitly documented in an Approved specification.
- Import/export schemas and compatibility behavior, and Backup/Restore safety
  behavior.
- Any behavior that expands the stated product scope.
