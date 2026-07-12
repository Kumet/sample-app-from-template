# Specs

Each feature gets its own directory.

```text
specs/012-feature-name/
  spec.md
  plan.md
  tasks.md
  validation.toml
  validation-log.md
```

## Rules

- Do not implement without a spec.
- Do not plan without resolving major ambiguities.
- Do not implement without tasks.
- Keep validation evidence in `validation-log.md`.
- Task `Validation` fields reference named argument-array commands from
  `validation.toml`; task prose is never executable.
- Version 2 maps validation names to repository-allowlisted Make targets and
  declares requirement/acceptance/task traceability.
- Run `make spec-lint FEATURE=<feature>` before autonomous work.
