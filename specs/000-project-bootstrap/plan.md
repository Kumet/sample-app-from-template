# Implementation plan: Project bootstrap

## Status

Implemented

## Summary

Create the smallest installable Python/FastAPI foundation for Local Project
Board, keep the existing automation framework intact, and make local and CI
quality gates exercise formatting, linting, typing, framework tests,
application tests, integration tests, and package build.

## Existing code investigation

- The repository has no `pyproject.toml` or application `src/` package.
- Framework tests are top-level `tests/test_*.py` unittest-compatible modules:
  agent interfaces, parser, safety, autonomous core/delivery, delivery review
  integrity, production readiness, and spec lint.
- The Makefile retains automation targets but its setup, formatting, linting,
  typing, and build gates are placeholders.
- CI already uses Python 3.11 and validates the framework, but does not install
  the application package before validation.
- Repository policy currently disables lint, typecheck, and build readiness.
- Project documentation is initialized but still describes the application
  foundation as future work.

## Affected files

| File | Change | Risk |
|---|---|---|
| `pyproject.toml` | Define package, bounded dependencies, build, pytest, Ruff, and mypy configuration. | Medium |
| `src/project_board/**` | Add import package and minimal FastAPI health endpoint. | Low |
| `tests/app/**` | Add isolated unit and TestClient integration coverage. | Low |
| `Makefile` | Replace placeholders while preserving framework automation targets. | Medium |
| `.agent-policy.toml` | Enable real lint, typecheck, test, and build gates. | Medium |
| `.github/workflows/ci.yml` | Install dependencies and run validation/stack qualification with read-only permissions. | Medium |
| `README.md`, `docs/**` | Document the now-operational foundation and developer workflow. | Low |
| `specs/000-project-bootstrap/**` | Record approved contract, plan, tasks, and validation evidence. | Low |
| `specs/001-*` through `specs/004-*` | Preserve the human-approved deletions of conflicting template history. | Low |

## Design

Use a standard `src` layout built with setuptools. `project_board.main` owns a
single FastAPI application and a pure health handler returning a typed constant
mapping. No domain, repository, database, CLI, or UI layers are introduced.

Make chooses `.venv/bin/python` when available, then Python 3.11, then `python3`,
and asserts Python 3.11+ during setup/testing. Framework and application test
commands remain distinct and are composed by `make test`. Pytest is restricted
to `tests/app` so it does not duplicate the framework unittest suite.

GitHub Actions sets up Python 3.11 with pip caching, upgrades pip, runs
`make setup`, `make validate`, and `make qualify-stacks`, and grants only
`contents: read`.

## Data model impact

None. No Project, Task, database, schema, migration, or persistence code is
created.

## API impact

Add only `GET /health`, returning HTTP 200, JSON content type, and
`{"status":"ok"}`. The endpoint has no external or environment dependencies.

## UI impact

None. Templates, static assets, Jinja2, HTMX, and JavaScript remain deferred.

## Test strategy

- Unit tests: verify the FastAPI instance, title, and direct health-handler result.
- Integration tests: TestClient verifies status, JSON body, JSON content type,
  and a 404 for an undefined route.
- Regression tests: retain and run every existing top-level framework test once.
- Build validation: create sdist and wheel and confirm the command succeeds.
- Runtime smoke test: start Uvicorn on loopback, curl `/health`, compare the exact
  response, and terminate only that server process.
- CI validation: require the GitHub Actions check for the exact PR HEAD SHA.

## Security considerations

- No secret, `.env`, credential, production configuration, or user-data access.
- No external runtime calls and no network use in tests.
- CI permissions remain `contents: read` with no deployment or release access.
- Dependencies come from bounded package-index releases; no URL or Git sources.

## Rollback strategy

Revert the bootstrap PR through a normal follow-up PR. No data migration or
persistent state requires rollback. Generated build artifacts and local virtual
environments remain untracked.

## Open questions

None. Product behavior beyond the health endpoint is explicitly deferred to
future approved specifications.
