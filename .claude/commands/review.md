# Claude review command

Use this prompt to review a PR or working diff.

```text
Read AGENTS.md, CLAUDE.md, docs/project-context.md, and the relevant specs directory.
Review the current diff against spec.md, plan.md, tasks.md, and validation-log.md.
Focus on:

- Spec compliance
- Scope creep
- Regression risk
- Security/privacy risk
- Test quality
- Whether tests were weakened
- Documentation gaps

Do not modify files. Return findings grouped by severity.
```
