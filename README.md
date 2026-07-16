# Local Project Board

Local Project Board is a Kanban web application for individuals and small teams
who want to manage projects and tasks locally. The planned product will support
both a web UI and CLI over the same domain and service layer.

This repository is also a real-application test bed for a specification-driven
AI development template. The goal is to verify the path from an approved
specification through bounded implementation, validation, review, pull request,
and CI.

## Current status

The Python 3.11+ application implements persistent Project CRUD, nested Task
CRUD, Project-scoped Tag CRUD, and Task-Tag assignment through a REST API backed
by local SQLite and SQLAlchemy 2.x. Tasks support Project-scoped Comments and a
read-only history of Comment create, update, and delete activity. Task lists
support filtering (including by Tag), pagination, and deterministic sorting.
Task responses include their Tags but do not embed Comments or Activity.
Projects expose a read-only dashboard of Task, due-date, Tag, Comment, and recent
Comment-activity aggregates.
`GET /health` remains available and does not query the database. The Kanban UI,
served from `GET /`, uses those same APIs for local Project, Task, Tag, Comment,
Activity, dashboard, and Task-query workflows. The CLI, import/export, and
backup/restore are not implemented yet.

## Development result

The sample-application development phase completed at main commit
`27f372ac967a8c684a0294e645a6b81faf611195`. The result is a local-first Project
Board with a REST API, dependency-free browser UI, SQLite persistence,
Project-level analytics, and a reproducible non-root Docker Compose workflow.

The application was built feature by feature from approved specifications. Each
feature followed specification, clarification, plan, task implementation,
validation, exact-HEAD evidence, independent review, pull request, and CI gates.
The same sample delivery also exercised and improved the reusable AI development
framework, including resumable worktrees, bounded review budgets, weakening
detection, review-evidence identity and redaction, and high-risk approval gates.

At completion, the main-branch validation passed 127 framework tests, 601
application tests, and 283 integration tests. The container CI also passed the
real image build, non-root health check, HTTP smoke test, SQLite restart
persistence, and isolated Docker-resource cleanup. All application and framework
PRs through PR #24 were merged through review and CI; no direct main push or
auto-merge was used.

See [Sample application development report](docs/sample-app-development-report.md)
for the implemented scope, architecture, development process, template
assessment, validation evidence, limitations, and recommended next steps.

## Requirements and setup

Requirements:

- Python 3.11 or later
- Git and Make
- Docker with Docker Compose v2 (only for the container workflow)

Create and activate a virtual environment, then install the application and
development tools:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make setup
```

`make setup` installs the source-layout `project_board` package in editable
mode with the approved development dependencies.

## Run with Docker Compose

The container workflow binds the application only to
<http://127.0.0.1:8000/> and keeps its SQLite database in the Compose-managed
`project-board-data` named volume. It is intended for reproducible local use,
not production deployment.

Build the local image without starting a container:

```bash
make container-build
```

Build and start the complete application with Docker Compose:

```bash
docker compose up --build
```

Leave that command running. In another terminal, verify the container status,
health response, and browser UI:

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

The health request must return:

```json
{"status":"ok"}
```

Then open <http://127.0.0.1:8000/>. Data created through the UI or API is stored
at `/data/project_board.sqlite3` inside the named volume, not in the repository.
To verify persistence, create a Project, stop normally, start again with
`docker compose up --build`, and confirm that the Project is still present.

Stop and remove the Compose container and network while preserving application
data:

```bash
docker compose down
```

### Warning: permanently delete container data

The following command is destructive. It removes the Compose container,
network, and the `project-board-data` named volume, permanently deleting the
containerized SQLite database. Use it only when you intentionally want a clean
container data store:

```bash
docker compose down --volumes
```

Neither command performs system-wide Docker cleanup or removes unrelated
resources. The opt-in `make container-smoke` validation uses separate,
uniquely named temporary resources and cleans up only those resources.

## Run the application

Start the development server from the repository root:

```bash
python3 -m uvicorn project_board.main:app --reload
```

On application startup, the development app explicitly creates missing Project,
Task, Tag, Task-Tag association, Task Comment, and Comment Activity tables and
indexes, then stores data in `project_board.sqlite3` in the current working
directory. Existing Project, Task, and Tag schema and rows are preserved.
SQLite foreign-key enforcement is enabled for every application connection so
Tasks cannot reference missing Projects and Task-Tag associations, Comments,
and Activity cannot cross Project and Task ownership boundaries.

Metadata-based schema creation is intended only for development and tests. It
does not version or upgrade an existing production schema, and this feature does
not define a production migration workflow. Stop the server before removing the
local database when a clean development database is needed.

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

### Use the browser UI

With the development server running, open <http://127.0.0.1:8000/>. The
same-origin UI supports Project, Task, Tag, and Comment management; Task search,
filters, sorting, and pagination; dashboard aggregates; and payload-free Comment
Activity. Changes made in the UI and through the REST API use the same local
database and application services.

The UI is packaged with the Python application and uses dependency-free HTML,
CSS, and JavaScript. It does not load assets, analytics, or application data
from external services. Destructive actions require confirmation, and a Project
that still owns Tasks must have those Tasks deleted before the Project can be
deleted.

## Project API

Project names are required, trimmed, and limited to 100 characters.
Descriptions are optional, trimmed, and limited to 1000 characters; a blank
description is stored as `null`. Projects are listed by creation time and then
by ID.

```bash
# Create a Project
curl -X POST http://127.0.0.1:8000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"Sample project","description":"Local planning"}'

# List Projects
curl http://127.0.0.1:8000/api/projects

# Retrieve Project 1
curl http://127.0.0.1:8000/api/projects/1

# Partially update Project 1
curl -X PATCH http://127.0.0.1:8000/api/projects/1 \
  -H 'Content-Type: application/json' \
  -d '{"description":null}'

# Permanently delete Project 1 (only when it has no Tasks)
curl -X DELETE http://127.0.0.1:8000/api/projects/1
```

Create returns HTTP 201, deletion returns HTTP 204 with no body, and operations
on a missing Project return HTTP 404. Invalid input returns HTTP 422. Deleting a
Project that still owns Tasks returns HTTP 409 and leaves both the Project and
its Tasks unchanged; explicitly delete its Tasks before deleting the Project. A
Project with no Tasks can be deleted even when it owns Tags; those Tags and
their associations are deleted with that Project.

### Project dashboard

```bash
# Retrieve Project 1 aggregates (the recent Activity default is 10 rows)
curl 'http://127.0.0.1:8000/api/projects/1/dashboard'

# Return no recent Activity while retaining all other aggregates
curl 'http://127.0.0.1:8000/api/projects/1/dashboard?activity_limit=0'
```

The dashboard returns an aware UTC `as_of` timestamp; zero-inclusive Task
counts by status and priority; mutually exclusive active-Task due buckets; Tag
counts; current Comment totals; and payload-free recent Comment Activity. Done
Tasks remain in Task totals but are excluded from due buckets. Tags are ordered
by case-folded name and ID. Recent Activity is ordered by `occurred_at`
descending, then by ID descending. The `activity_limit` query value defaults to
10 and accepts integers from 0 to 50. A missing Project returns HTTP 404 and an
invalid limit returns HTTP 422.

## Tag API

Every Tag belongs to the Project identified by the nested URL. Names are
required, trimmed, and limited to 50 characters. Names are unique within a
Project using the trimmed name's case-folded value, while different Projects
may use the same name. Colors are optional and must use `#RRGGBB`; lowercase
hex values are returned in uppercase. Tags are listed by case-folded name and
then by ID.

```bash
# Create a Tag in Project 1
curl -X POST http://127.0.0.1:8000/api/projects/1/tags \
  -H 'Content-Type: application/json' \
  -d '{"name":"Backend","color":"#3366cc"}'

# List Project 1 Tags
curl http://127.0.0.1:8000/api/projects/1/tags

# Retrieve Tag 1
curl http://127.0.0.1:8000/api/projects/1/tags/1

# Rename Tag 1 and clear its color
curl -X PATCH http://127.0.0.1:8000/api/projects/1/tags/1 \
  -H 'Content-Type: application/json' \
  -d '{"name":"API","color":null}'

# Permanently delete Tag 1 and its Task associations
curl -X DELETE http://127.0.0.1:8000/api/projects/1/tags/1
```

Create returns HTTP 201, deletion returns HTTP 204 with no body, and a duplicate
name within one Project returns HTTP 409. Missing Tags and cross-Project Tag
lookups return HTTP 404 without disclosing ownership. Invalid input returns HTTP
422. PATCH requires `name` or `color`; IDs, `project_id`, timestamps, and the
internal normalized name cannot be changed or supplied. Deleting a Tag removes
its Task associations but preserves its Tasks and Project.

## Task API

Every Task belongs to the Project identified by the nested URL. Titles are
required, trimmed, and limited to 200 characters. Descriptions are optional,
trimmed, and limited to 2000 characters; a blank description is stored as
`null`. Status is `todo`, `in_progress`, or `done` and defaults to `todo`.
Priority is `low`, `medium`, or `high` and defaults to `medium`. Optional due
dates must include a timezone and are normalized to UTC.

```bash
# Create a Task in Project 1
curl -X POST http://127.0.0.1:8000/api/projects/1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Implement Task CRUD","priority":"high","due_at":"2026-07-31T09:00:00+09:00"}'

# Search Project 1 Tasks across multiple statuses, sorted by title
curl 'http://127.0.0.1:8000/api/projects/1/tasks?q=task&status=todo&status=in_progress&sort=title&order=asc&limit=50&offset=0'

# Retrieve Task 1
curl http://127.0.0.1:8000/api/projects/1/tasks/1

# Attach Tag 1 to Task 1 (safe to repeat)
curl -X PUT http://127.0.0.1:8000/api/projects/1/tasks/1/tags/1

# List only Tasks associated with Tag 1
curl 'http://127.0.0.1:8000/api/projects/1/tasks?tag_id=1&limit=50&offset=0'

# Detach Tag 1 from Task 1 (safe to repeat)
curl -X DELETE http://127.0.0.1:8000/api/projects/1/tasks/1/tags/1

# Partially update Task 1; null clears optional fields
curl -X PATCH http://127.0.0.1:8000/api/projects/1/tasks/1 \
  -H 'Content-Type: application/json' \
  -d '{"status":"in_progress","due_at":null}'

# Permanently delete Task 1
curl -X DELETE http://127.0.0.1:8000/api/projects/1/tasks/1
```

Task create returns HTTP 201 and deletion returns HTTP 204 with no body. Missing
Projects or Tasks and cross-Project Task lookups return HTTP 404 without
disclosing another Project's ownership. Invalid bodies and query values return
HTTP 422. PATCH requires at least one mutable field; `project_id`, IDs, and
timestamps cannot be changed. Attach and detach return HTTP 204 with no body and
are idempotent. Missing or cross-Project Tasks and Tags return HTTP 404. Deleting
a Task removes its Tag associations but preserves its Tags.

Task lists accept a trimmed, case-insensitive substring search `q` from 1 to 100
characters, repeated exact `status` and `priority` filters, strict `due_before`
and `due_after` timestamps, an optional positive `tag_id`, `limit` from 1 to
100 (default 50), and a non-negative `offset`. Repeated values within `status`
or `priority` are ORed; different filter fields compose with AND. Search treats
SQL wildcard characters as literal text. A missing or foreign `tag_id` returns
HTTP 404. Filtering, sorting, and pagination occur before the bounded result is
returned. Sort fields are `created_at`, `updated_at`, `due_at`, `priority`, and
case-insensitive `title`, with `asc` or `desc` order. Results use Task ID
ascending as a stable tie-breaker; due-date nulls are always last and priority
follows `low < medium < high`.

Every Task response contains a `tags` array, including an empty array for an
untagged Task. Tags in Task responses are ordered by case-folded name and ID.
Task lists load Tags in bulk for the returned page rather than issuing one Tag
query per Task.

## Task Comment and Activity API

Every Comment belongs to the Project and Task identified by the nested URL. A
Comment body is required, trimmed, and limited to 2000 characters. Comment
creation, update, and deletion each append a corresponding payload-free
`comment_created`, `comment_updated`, or `comment_deleted` Activity in the same
transaction.

```bash
# Create a Comment on Task 1
curl -X POST http://127.0.0.1:8000/api/projects/1/tasks/1/comments \
  -H 'Content-Type: application/json' \
  -d '{"body":"Ready for review"}'

# List Comments in ascending creation order
curl 'http://127.0.0.1:8000/api/projects/1/tasks/1/comments?order=asc&limit=50&offset=0'

# Retrieve and update Comment 1
curl http://127.0.0.1:8000/api/projects/1/tasks/1/comments/1
curl -X PATCH http://127.0.0.1:8000/api/projects/1/tasks/1/comments/1 \
  -H 'Content-Type: application/json' \
  -d '{"body":"Review complete"}'

# Permanently delete Comment 1
curl -X DELETE http://127.0.0.1:8000/api/projects/1/tasks/1/comments/1

# List only deletion Activity for Task 1
curl 'http://127.0.0.1:8000/api/projects/1/tasks/1/activities?event_type=comment_deleted&order=asc&limit=50&offset=0'
```

Comment creation returns HTTP 201; retrieval, listing, and updates return HTTP
200; deletion returns HTTP 204 with no body. Comment PATCH accepts only the
required `body`. Comment and Activity lists accept `limit` from 1 to 100
(default 50), a non-negative `offset` (default 0), and `order=asc|desc` (default
`asc`). Activity lists additionally accept an optional `event_type` filter.
Missing or cross-Project/Task resources return HTTP 404 without disclosing
ownership, and invalid bodies or query values return HTTP 422.

Activity has no mutation endpoint and never includes a Comment body. Deleting a
Comment retains its deletion Activity while the Task exists. Deleting a Task
cascades all of its Comments and Comment Activity without affecting other Tasks;
the existing rule that a Project with Tasks cannot be deleted remains unchanged.

Tests and other callers can initialize an isolated SQLite database explicitly:

```python
from project_board.infrastructure import create_database_engine, initialize_schema

engine = create_database_engine("sqlite:///test.sqlite3")
initialize_schema(engine)
```

Application integration tests create a separate database under pytest's
temporary directory for every test and inject its session factory into
`create_app`; they never use or modify `project_board.sqlite3`.

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
- Create tasks within projects and move them through Todo, In Progress, and Done.
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
- FastAPI and Uvicorn for the REST API runtime
- Packaged dependency-free HTML, CSS, and JavaScript for the browser UI
- SQLite and SQLAlchemy 2.x for local Project, Task, Tag, Comment, and Activity
  persistence
- pytest, Ruff, and mypy
- `pyproject.toml` package management
- Make-based quality commands
- GitHub Actions

Jinja2 and HTMX are not installed or required by the current browser UI.

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

Independent review is resumable but fail-closed. A shard result is reusable only
when its feature, exact HEAD, shard, prompt/schema versions, model command,
reviewed files, and complete input digest match and the authoritative runtime
event records `PASS`. Failed, timed-out, invalid, or missing shards are rerun
within both configured review budgets. Integration review runs only after every
file-focused shard passes.

If the delivery-wide reviewer-call budget is exhausted, delivery records one
`HUMAN_REQUIRED` event and stops before another reviewer subprocess starts. It
does not retry exhaustion or refill the budget in the same invocation. After
human approval, invoking `make deliver` again creates a fresh bounded budget;
exact-identity PASS shards are reused without spending calls, while pending or
identity-changed shards still require reviewer PASS.

Tracked validation evidence is finalized before exact-HEAD validation. The log
contains snapshot format and event schema versions, its included-event watermark,
generation time, and validation-contract digest—but never its own commit SHA.
After commit, a `tracked-evidence-snapshot` runtime event binds that HEAD to the
log's Git blob SHA. Each command emits `final-validation-attempt`; only a fully
attributed `final-validation-accepted/PASS` references that attempt and snapshot
and opens gates. Review accepts neither ordinary, legacy, attempt, or rejected
validation events nor mismatched blob, contract, event, HEAD, or dirty-worktree
state. This avoids a self-referential tracked commit loop while preserving exact
attribution.

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

人間が確認したrecovery-only差分によって、failed stateに保存された変更パスが
増えた場合は、stateやeventを手編集せず、追加パスを明示して再帰属します。

```bash
make approve-recovery-patch-dry-run \
  FEATURE=123-feature-name \
  PATHS='path/to/recovered-file.ext path/to/recovery-test.ext' \
  REASON='Human-approved format-only recovery'

make approve-recovery-patch \
  FEATURE=123-feature-name \
  PATHS='path/to/recovered-file.ext path/to/recovery-test.ext' \
  REASON='Human-approved format-only recovery'

make deliver-dry-run FEATURE=123-feature-name
make deliver FEATURE=123-feature-name
```

`PATHS` はglobsではなく、停止後に新たに変更された明示的な相対パスだけを
指定します。承認時はHEADを変更しないでください。ownership、branch、HEAD、
contract、scope、全変更パス、working treeとindexを含むdiff digestが一致した
場合だけstateを更新します。承認後に内容やindexだけが変わった場合もdeliveryは
停止します。

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
- `docs/architecture.md`: implemented Project architecture and intended future layers.
- `AGENTS.md`: shared operating rules for coding agents.
