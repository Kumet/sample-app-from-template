# Local Project Board

Local Project Board is a Kanban web application for individuals and small teams
who want to manage projects and tasks locally. The planned product will support
both a web UI and CLI over the same domain and service layer.

This repository is also a real-application test bed for a specification-driven
AI development template. The goal is to verify the path from an approved
specification through bounded implementation, validation, review, pull request,
and CI.

## Current status

The Python 3.11+ development foundation is initialized. The only application
capability currently implemented is `GET /health`; there are no Project or Task
models, CRUD operations, database, Kanban UI, or CLI yet. Project CRUD is the
next product feature and must begin with an approved specification.

## Requirements and setup

Requirements:

- Python 3.11 or later
- Git and Make

Create and activate a virtual environment, then install the application and
development tools:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make setup
```

`make setup` installs the source-layout `project_board` package in editable
mode with the approved development dependencies.

## Run the application

Start the development server from the repository root:

```bash
python3 -m uvicorn project_board.main:app --reload
```

In another terminal, confirm health:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The health endpoint has no database, external API, environment-variable, or
secret dependency.

## Quality commands

```bash
make format          # format supported source and test files
make format-check    # verify formatting without changing files
make lint            # run Ruff checks
make typecheck       # run strict mypy checks for src/
make test-framework  # run the retained automation framework tests
make test-app        # run application unit and integration tests
make test            # run framework and application tests
make integration-test
make build           # build wheel and source distribution
make doctor          # report local and delivery readiness
make validate        # run the complete local quality gate
```

GitHub Actions installs the same development dependencies, runs
`make validate`, and qualifies the automation framework's stack fixtures.

## Intended features

- Create, view, edit, and delete projects.
- Create tasks within projects and move them through Todo, Doing, and Done.
- Set task priority, an optional due date, and tags.
- Search and filter by keyword, status, tag, and due date.
- Use the same local data through the web UI and CLI.
- Import and export recoverable JSON data.
- Back up and restore the local database.

Authentication, billing, external AI or storage services, real-time
collaboration, production deployment, and mobile applications are currently out
of scope.

## Technical stack

- Python 3.11 or later
- FastAPI and Uvicorn for the current bootstrap runtime
- pytest, Ruff, and mypy
- `pyproject.toml` package management
- Make-based quality commands
- GitHub Actions

SQLite, SQLAlchemy, Jinja2, HTMX, and small JavaScript modules remain intended
for later features and are deliberately not installed until an approved
feature uses them.

## Specification-driven development flow

Work follows this sequence:

```text
specification
  -> clarification
  -> technical plan
  -> tasks
  -> task-by-task implementation
  -> validation
  -> review
  -> PR and CI
```

Feature artifacts live under `specs/<feature>/`:

```text
specs/012-feature-name/
  spec.md
  plan.md
  tasks.md
  validation.toml
  validation-log.md
```

Implementation starts only from a human-approved specification on a clean
feature branch. Undefined domain behavior must not be inferred; it is returned
for human clarification and recorded in the specification. The standard final
quality command is intended to be:

```bash
make validate
```

The Python project and quality gates are operational; each product feature must
extend them without weakening existing tests.

## Development automation

The repository includes stack-independent automation that selects one
unfinished task at a time, runs Codex with bounded retries, performs named
validation and safety checks, records evidence, and creates a local commit only
after successful checks.

```text
approved specification
  -> select one unfinished task
  -> implement with Codex
  -> test, scope, and secret-file checks
  -> bounded repair on failure
  -> complete task and create a local commit on success
  -> project-wide validation after all tasks
```

Task prose is never executed as shell input. `tasks.md` references validation
names declared in the version 2 `validation.toml`, and those names map only to
Make targets allowed by `.agent-policy.toml`. Traceability connects
requirements, acceptance criteria, and task IDs.

Before autonomous local work, review and commit the approved feature artifacts,
then use a clean, non-protected feature branch. The local workflow is:

```bash
make validate-spec FEATURE=012-feature-name
make spec-lint FEATURE=012-feature-name
make work-dry-run FEATURE=012-feature-name
make work FEATURE=012-feature-name
make work-status FEATURE=012-feature-name
```

Runtime evidence is stored outside Git under
`.agent-work/<feature>/<timestamp>/`. Long-term results are recorded in the
feature's `validation-log.md`. A failed attempt intentionally leaves its diff
available for repair or human review.

For end-to-end delivery, the framework also provides a dry run and an isolated
delivery workflow:

```bash
make deliver-dry-run FEATURE=012-feature-name
make deliver FEATURE=012-feature-name
```

Delivery can perform specification linting, isolated-worktree implementation,
test-weakening inspection, independent structured review, push, PR creation,
and CI monitoring. Risk policy limits the result: medium risk stops at a
ready-for-review PR, high risk normally stops before push, and low risk can
merge only when both the feature contract and repository policy explicitly
allow it. The framework never pushes directly to `main` or `master`.

Recovery and cleanup commands are available for framework-owned worktrees:

```bash
make work-resume FEATURE=012-feature-name
make work-abort FEATURE=012-feature-name
make cleanup-worktree FEATURE=012-feature-name
```

Resume verifies the saved branch, HEAD, specification digest, and changed
files. Abort changes execution state without deleting the diff. Cleanup removes
only a clean worktree owned by the framework.

Stack detection remains available when reviewing the repository's configured
application stack:

```bash
make detect-stack
make doctor
```

Push, merge, deployment, and specification changes are never implicit. Safety
stops apply to protected branches, dirty worktrees, forbidden paths, repeated
errors, and attempts to access secret files.

Additional framework qualification commands are:

```bash
make quality-check
make qualify-stacks
```

実行証跡は `.agent-work/<feature>/events.jsonl` が正本です。validation、review、
CI、mergeは同一HEAD SHAに揃わない限り合格しません。

```bash
make render-validation-log FEATURE=012-feature
```

scope違反で停止したあと、エラー修正のため別のパス（例:
`.gitignore`）が必要になった場合は、既存eventを編集せず、正式な要求を
dry-runしてから発行します。これは承認ではなく、人間による承認待ちの
evidenceを追加するだけです。

```bash
make request-scope-dry-run FEATURE=012-feature PATH='.gitignore' REASON='ignore generated build metadata'
make request-scope FEATURE=012-feature PATH='.gitignore' REASON='ignore generated build metadata'
```

要求内容を人間が確認してscope拡張を承認した場合は、まず承認変更を
previewします。

```bash
make approve-scope-dry-run FEATURE=012-feature PATH='prompts/**' REASON='review repair'
make approve-scope FEATURE=012-feature PATH='prompts/**' REASON='review repair'
```

`request-scope` と `approve-scope` は、同じfeatureと完全一致する安全な
repository-relative pathを要求します。絶対パス、`..`、制御文字、全体を
許可する `*` / `**`、forbidden pathは拒否されます。承認後は表示された
contract/state差分を確認し、停止中のworktreeを `make work-resume
FEATURE=012-feature` で再開します。壊れた古いscope eventは監査履歴として
保持され、新しい正規requestが追記されます。

version 1契約は実行されません。安全なMakeターゲットだけをversion 2へ移行します。

## Project documentation

- `docs/project-context.md`: purpose, users, workflows, rules, stack, and safety.
- `docs/glossary.md`: domain terminology and decisions AI agents must not infer.
- `docs/architecture.md`: intended pre-implementation architecture.
- `AGENTS.md`: shared operating rules for coding agents.
