# Feature specification: Project bootstrap

## Status

Implemented

## Background

Local Project Board currently contains the reusable AI development automation
framework and project documentation, but no application package or executable
application quality gates. The repository needs a minimal, verified Python and
FastAPI foundation before product features can be developed from approved
specifications.

This specification is approved by the human request that defines the bootstrap
scope, dependencies, CI changes, feature-branch publication, pull request, and
merge after successful CI.

## Goals

- Establish a Python 3.11+ source-layout package for Local Project Board.
- Provide a minimal FastAPI application with a dependency-free health endpoint.
- Add application tests without weakening or replacing framework tests.
- Turn the repository's Make targets and quality policy into executable gates.
- Validate the same quality workflow locally and in read-only GitHub Actions.
- Document setup, testing, startup, health verification, and specification-driven delivery.

## Non-goals

- Project or Task models and CRUD.
- SQLite schema, SQLAlchemy models, or migrations.
- Kanban UI, templates, HTMX, or JavaScript.
- CLI or import/export behavior.
- Authentication, authorization, billing, or external APIs.
- Production deployment, Docker, or Kubernetes.

## Users

- Developers preparing to implement Local Project Board features.
- AI coding agents executing approved specifications.
- Human reviewers validating repository quality and delivery evidence.

## Requirements

### Functional requirements

- REQ-001: Create a Python 3.11 or later source-layout package.
- REQ-002: Create a FastAPI application.
- REQ-003: `GET /health` returns HTTP 200 and `{"status":"ok"}`.
- REQ-004: Configure pytest, Ruff, mypy, and package build.
- REQ-005: Replace placeholder Make quality targets with executable commands.
- REQ-006: Enable the repository lint, typecheck, test, and build quality policy.
- REQ-007: Run setup, `make validate`, and `make qualify-stacks` in GitHub Actions.
- REQ-008: Enable developers to set up, test, and run the app using README instructions.
- REQ-009: Preserve and execute all existing framework tests.
- REQ-010: Make `make doctor` and `make validate` succeed.

### Non-functional requirements

- Runtime dependencies are limited to FastAPI and Uvicorn.
- Development dependencies are limited to pytest, HTTPX, Ruff, mypy, and build,
  plus their transitive dependencies.
- Dependency declarations use bounded, Python 3.11-compatible stable ranges and
  no wildcard or Git URL dependencies.
- The health endpoint accesses no database, external API, environment variable,
  credential, or secret.
- GitHub Actions uses read-only repository contents permission.
- Tests use no external network access and must not be weakened.
- The active repository `.venv` is used locally and is not committed.

## Acceptance criteria

- [x] AC-001: `pyproject.toml` exists and requires Python 3.11 or later.
- [x] AC-002: The `src/project_board` package can be imported.
- [x] AC-003: FastAPI TestClient verifies a successful `GET /health` response.
- [x] AC-004: `make format-check` succeeds.
- [x] AC-005: `make lint` succeeds.
- [x] AC-006: `make typecheck` succeeds.
- [x] AC-007: `make test` runs both framework and application tests.
- [x] AC-008: `make integration-test` succeeds.
- [x] AC-009: `make build` succeeds.
- [x] AC-010: `make validate` succeeds.
- [x] AC-011: `make doctor` reports local work and medium delivery ready.
- [x] AC-012: GitHub Actions succeeds for the pull request HEAD.
- [x] AC-013: README instructions are sufficient for setup and application startup.

## Clarifications

| Question | Answer | Date |
|---|---|---|
| Is the bootstrap scope and specification approved? | Yes; the human explicitly approved the requirements, scope, dependencies, CI change, feature push, PR, and post-CI merge. | 2026-07-12 |
| Which local Python interpreter is authoritative? | The repository `.venv` Python 3.11+ interpreter, invoked through an explicitly prefixed `.venv/bin` PATH. | 2026-07-12 |
| Are deletions of `specs/001-*` through `specs/004-*` intended? | Yes; they are approved removal of template development history whose numbering conflicts with Local Project Board features. `specs/_template/**` and `specs/README.md` remain. | 2026-07-12 |
| Is `.python-version` in scope? | No. It remains untracked and is neither modified nor committed by this feature. | 2026-07-12 |
| Are product data and UI capabilities included? | No. Project/Task/DB/UI/CLI capabilities are deferred to later approved features. | 2026-07-12 |

No material ambiguity remains. Any implementation requiring scope expansion or
a change to these decisions is human-required.

## Scope

### Allowed changes

- `pyproject.toml`
- `Makefile`
- `.agent-policy.toml`
- `.github/workflows/ci.yml`
- `README.md`
- `docs/**`
- `src/**`
- `tests/**`
- `specs/000-project-bootstrap/**`
- Approved deletion of `specs/001-developer-automation-framework/**`
- Approved deletion of `specs/002-autonomous-delivery/**`
- Approved deletion of `specs/003-delivery-smoke-test/**`
- Approved deletion of `specs/004-production-ready-template/**`

### Forbidden changes

- `.env`, `.env.*`, `**/.env`, and `**/.env.*`
- `local.properties`
- `**/*.pem` and `**/*.key`
- `**/credentials.*` and `**/secrets.*`
- `specs/_template/**` and `specs/README.md`
- Existing framework tests, except adding application tests under `tests/app/**`
- Authentication, security, billing, deployment, database, and product-feature code

## Security and privacy

The bootstrap adds no data persistence, user data processing, authentication,
or external service calls. The health endpoint is a constant response. CI is
read-only and receives no new secret or deployment permissions. Secret files,
credentials, production configuration, and `.env` files must not be read or
committed.
