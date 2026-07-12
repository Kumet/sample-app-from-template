# Project context

## Project purpose

**Local Project Board** is a Kanban web application for individuals and small
teams who want to manage projects and tasks in a local environment. It is also
a sample application for verifying that the AI development template can carry
work from an approved specification through implementation, pull request, and
CI while respecting its quality and safety gates.

The application is in its initial development stage. Product behavior that is
not defined here must be decided in an approved feature specification before it
is implemented.

## Users

- Individual developers.
- Small development teams.
- People who want simple task management in a local environment.

## Core workflows

- Create, view, edit, and delete projects.
- Add tasks to an existing project.
- Move tasks between Todo, Doing, and Done.
- Assign a priority, optional due date, and tags to a task.
- Search and filter tasks by keyword, status, tag, and due date.
- Operate on the same data through the web UI and CLI.
- Export application data to JSON and restore it through JSON import.
- Back up and restore local data.

## Domain rules

- A Project name is required.
- A Task title is required.
- A Task status must be `todo`, `doing`, or `done`.
- A Task priority must be `low`, `medium`, or `high`.
- A due date is optional.
- A Tag name must not be empty.
- The same Tag must not be assigned to one Task more than once.
- A Task cannot be added to a Project that does not exist.
- The handling of related Tasks when a Project is deleted must be defined in an
  approved specification; it must not be inferred.
- A failed import must leave existing data unchanged. An import is one atomic
  transaction.
- Exported data must be restorable through import.
- The web UI and CLI must use the same application service and domain layers.
- Date and time values are handled internally in UTC. The timezone policy for
  user-facing values must be decided in an approved specification.
- Unknown domain behavior must not be inferred and requires human clarification.

## Technical stack

The intended stack, to be confirmed as implementation specifications are
approved, is:

- Python 3.11 or later.
- FastAPI for the web and API boundary.
- Jinja2 with HTMX or a small amount of JavaScript for the web UI.
- SQLite for local persistence.
- SQLAlchemy and Pydantic.
- pytest, Ruff, and mypy for quality checks.
- Package management through `pyproject.toml`.
- GitHub Actions for CI.
- Make targets as the common interface to quality commands.

## Data sensitivity

- Application data is stored in a local SQLite database.
- User data, including complete Task bodies, must not be sent to external
  services.
- The application does not handle personal information, authentication data,
  credentials, or secrets.
- Test data must not contain real people or real secrets.
- Logs must not emit complete Task bodies unconditionally.
- Import and export operate only on local files explicitly selected by the user.

## Forbidden actions

- Do not read `.env` files, tokens, credentials, private keys, secrets, or
  production configuration.
- Do not add authentication, authorization, OAuth, billing, email, external AI
  APIs, external cloud storage, multi-tenancy, real-time collaboration,
  production deployment, Kubernetes, mobile applications, or automatic sending
  to external services without an approved scope change.
- Do not store personal information or send application data externally.
- Do not change authentication, authorization, billing, security, deployment,
  database migration logic, CI/CD secrets, repository settings, or production
  configuration without explicit human approval.
- Do not infer undefined domain rules; mark them human-required and resolve them
  in an approved specification.

## Validation command

The standard validation command is:

```bash
make validate
```
