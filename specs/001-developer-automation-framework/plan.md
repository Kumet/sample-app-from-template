# Implementation plan: Developer Automation Framework

## Status

Implemented

## Summary

Build a Python 3.11 standard-library orchestration package behind stable Make
targets. The package validates a fixed feature contract, selects one task,
invokes Codex without a shell, applies bounded validation/repair loops, checks
scope and Git safety, records evidence, and creates local task commits.

## Existing code investigation

The repository already provides spec templates, `make validate`, a lightweight
secret filename check, CI, and operating rules. It does not contain an agent
runner, task parser, executable validation contract, meaningful unit-test
target, or runtime log model. Existing `.history/` content is unrelated and
must remain untouched.

## Affected files

| File | Change | Risk |
|---|---|---|
| `scripts/agent/*.py` | Add orchestration modules | High |
| `prompts/*.md` | Add task and repair prompt templates | Medium |
| `tests/agent/*` | Add isolated unit/integration tests | Low |
| `Makefile` | Add work targets and real tests | Medium |
| `specs/_template/*` | Define fixed feature contract | Medium |
| `.gitignore` | Ignore runtime evidence | Low |
| docs and CI | Document and validate framework | Low |

## Design

`work.py` owns CLI parsing and orchestration. `parser.py` resolves features,
loads TOML, and parses the constrained Markdown task format. `git_utils.py`
performs read-only Git checks and explicit local commits. `validation.py` runs
named argument-array commands and checks changed paths without opening
forbidden files. `codex_runner.py` renders prompts and invokes `codex exec` with
workspace-write sandboxing and `approval_policy="never"`.

Every run receives a timestamped evidence directory. Dry-run and status paths
must not create it. Initial work requires a clean non-protected branch. A
failed attempt may leave a diff for repair. Successful task validation updates
the task checkbox and validation log before an explicit-path commit.

## Data model impact

No application data. New TOML and Markdown repository contracts plus ignored
runtime evidence under `.agent-work/`.

## API impact

New CLI and Make interfaces: `work`, `work-dry-run`, `work-status`, and
`validate-spec`.

## UI impact

Terminal output only.

## Test strategy

- Unit tests: task parsing, feature resolution, config validation, path rules.
- Integration tests: temporary Git repositories and a stub Codex executable.
- E2E tests: Make target smoke checks through dry-run/status.
- Regression tests: protected branch, dirty tree, repeated failure, task cap.

## Security considerations

Never open forbidden paths, never use a shell, do not implement push/merge or
destructive Git operations, constrain executable configuration, and pass Codex
an explicit sandbox and approval policy.

## Rollback strategy

Revert the feature commits. Runtime evidence is ignored. The framework itself
never performs automated rollback of user or Codex changes.

## Open questions

- None blocking implementation.
