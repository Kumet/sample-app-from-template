# Feature specification: Containerized operational readiness

## Status

Approved. The human-approved Feature 020 request dated 2026-07-15 is the source
of truth; there is no GitHub Issue.

## Goal

Provide a reproducible, non-root local container runtime and CI verification for
the existing Local Project Board, including persistent SQLite data, health and
HTTP smoke tests, and browser acceptance, without changing application or
database contracts.

## User stories

- As a local user, I can build and start the complete board with Docker Compose
  on localhost and keep my data across container recreation.
- As a maintainer, I can verify the image boundary, HTTP behavior, persistence,
  cleanup, and Web UI with bounded, isolated test resources.
- As a reviewer, I can rely on CI to run both the ordinary validation suite and
  real container build/smoke checks without registry, secrets, or deployment.

## Requirements

- REQ-001: A pinned Python 3.11 official slim multi-stage Dockerfile MUST build
  the application wheel and install it into a source-free runtime stage.
- REQ-002: Runtime MUST use fixed non-root UID/GID, `/data` as working and sole
  persistent application write location, bytecode-disabled/unbuffered Python,
  and exec-form single-worker Uvicorn on `0.0.0.0:8000` without reload.
- REQ-003: The unchanged `sqlite:///project_board.sqlite3` contract MUST resolve
  to `/data/project_board.sqlite3`; the image MUST contain no local database.
- REQ-004: Healthcheck MUST call `/health` using Python standard library only and
  require HTTP 200 plus `{"status":"ok"}` without adding OS packages.
- REQ-005: Runtime image/build context MUST exclude tests, specs, Git metadata,
  agent/runtime evidence, environments, secrets, caches, artifacts, coverage,
  and SQLite files while retaining build metadata, README, package, and Web UI.
- REQ-006: `compose.yaml` MUST define only `project-board`, publish
  `127.0.0.1:8000`, mount a named volume at `/data`, use `init: true`, bounded
  restart behavior, healthcheck, all capability drop, and no-new-privileges.
- REQ-007: Existing Make targets and `make validate` MUST remain unchanged in
  behavior; dedicated `container-build` and `container-smoke` targets are opt-in.
- REQ-008: Container smoke MUST use unique names and an ephemeral host port,
  build a real image, prove non-root/healthy runtime, and fetch health, HTML,
  CSS, and JavaScript only over localhost.
- REQ-009: Smoke MUST create and retrieve a Project, recreate the container with
  the same volume, and prove the Project persists without touching the
  repository-local SQLite file.
- REQ-010: Smoke MUST reject traceback/sensitive log patterns and always clean
  only its own containers, network, volume, and image on success or failure;
  prune and unrelated resource mutation are forbidden.
- REQ-011: Structural and lifecycle tests MUST verify Dockerfile, ignore,
  Compose, Make, smoke safety, packaging, CI, and README contracts without
  substituting mocks for the real CI smoke.
- REQ-012: CI MUST preserve the existing validation job and add a timeout-bound
  Docker job running `make container-build` and `make container-smoke` with no
  registry login, image push, secret, deployment, or settings mutation.
- REQ-013: README MUST document build, `docker compose up --build`, verification,
  `docker compose down`, persistence, and separately warned destructive volume
  deletion commands.
- REQ-014: When browser control is available, a localhost temporary-container
  flow MUST exercise Project, Task, Tag attachment, Comment/activity, Task
  query, dashboard, reload persistence, cleanup, desktop/mobile, console, and
  external-network checks without new browser dependencies.
- REQ-015: Browser unavailability MUST be recorded honestly; automated HTTP and
  container validation remain mandatory and MUST NOT be reported as browser PASS.
- REQ-016: Existing APIs, Web UI assets, package dependencies, schema,
  migrations, application source, framework, policy, and prior evidence MUST
  remain unchanged.
- REQ-017: Feature risk MUST remain high with infrastructure and ci domains,
  auto-merge false, exact-HEAD evidence, weakening inspection, all review
  shards, high-risk approval, PR CI, and human merge approval.
- REQ-018: No external service, SaaS, CDN, analytics, credentials, production
  configuration, registry push, deployment, or system-wide Docker cleanup may
  be introduced.

## Acceptance criteria

- [ ] AC-001: Dockerfile structure, pinned base, wheel boundary, fixed non-root
  user, environment, `/data`, healthcheck, and exec CMD pass inspection.
- [ ] AC-002: Image inspection proves no repository source/tests/specs/Git/env/
  SQLite evidence and proves packaged Web assets are usable.
- [ ] AC-003: Compose localhost binding, named volume, init, health, capability
  drop, no-new-privileges, and bounded restart contract pass.
- [ ] AC-004: Real smoke proves image build, non-root, healthy status, health/UI/
  assets, Project create/get, container recreation persistence, and safe logs.
- [ ] AC-005: Success and induced-failure tests prove unique-resource cleanup and
  no unrelated Docker resource or repository/local-SQLite mutation.
- [ ] AC-006: Existing validation remains Docker-independent while both dedicated
  container targets are explicit and functional.
- [ ] AC-007: CI retains ordinary validation and runs real build/smoke in a
  separate timeout-bound, secret-free, non-publishing job.
- [ ] AC-008: README commands match implementation and distinguish normal stop
  from destructive volume deletion.
- [ ] AC-009: Browser acceptance completes as specified, or is explicitly
  recorded unavailable with reproducible human instructions.
- [ ] AC-010: Spec-lint, targeted tests, full validation, real container smoke,
  exact-HEAD evidence, weakening, and all five review shards pass.
- [ ] AC-011: Feature PR CI succeeds and the PR remains unmerged pending human
  merge approval.
- [ ] AC-012: Feature 019 and earlier runtime evidence remains byte-for-byte
  unchanged and no forbidden path changes.

## Clarifications

| Question | Fixed answer | Basis |
|---|---|---|
| Runtime command | `python -m uvicorn project_board.main:app --host 0.0.0.0 --port 8000`, one worker, no reload. | Approved request |
| SQLite location | Keep the URL unchanged and set runtime `WORKDIR /data`. | Existing app contract |
| Base image | `python:3.11.11-slim-bookworm`; tag availability was verified, no unverified digest is claimed. | Approved fixed variant rule |
| Health client | Python `urllib.request`; no curl/OS package. | Minimal runtime boundary |
| Compose exposure | Only `127.0.0.1:8000:8000`. | Local-only requirement |
| Smoke port | Docker ephemeral loopback publish, discovered after start. | Avoid fixed-port collision |
| Smoke isolation | Per-run UUID names; cleanup exact names only in `finally`. | No unrelated mutation |
| Migration | None; existing metadata initialization runs in `/data`. | Approved scope |
| Container validation | Dedicated opt-in targets allowed by Feature 021; not dependencies of `validate`. | Policy contract |
| Browser | Use Codex in-app browser when available; never add Playwright/Selenium/Node. | Approved request |

No material ambiguity remains. Any change to these answers requires human
approval.

## Container and persistence boundary

The builder receives only build metadata and `src/`, produces dependency and
application wheels, and is discarded. Runtime receives wheels only, runs as the
fixed unprivileged user, and writes application state only beneath the mounted
`/data`. Named-volume persistence is intentionally local and is not production
backup or migration support.

## Smoke lifecycle and failure behavior

Fingerprint Git status and any repository-local SQLite file; create unique image,
network, volume, and first container; validate runtime and create data; remove the
first container; create the second container on the same volume; validate data;
inspect logs; then remove only those exact resources in reverse order in a
`finally` block. Any failed assertion returns non-zero after cleanup.

## CI contract

The existing `validate` job remains intact. A separate container job uses the
GitHub-hosted Docker daemon, fixed timeout, repository checkout, Python 3.11,
dedicated Make targets, and an always-run cleanup step. It neither authenticates
to a registry nor publishes or deploys.

## Out of scope

Production deployment, orchestration, registry publication, Kubernetes,
multi-worker service, schema/migration changes, database URL configuration,
backup/restore, authentication/authorization, secrets, external services,
application/API/UI changes, and Docker resource pruning.

## Definition of done

All ACs are evidenced on one exact HEAD, the real container persistence smoke
and independent reviews pass, CI succeeds on a ready-for-review PR, prior runtime
evidence is unchanged, and merge awaits explicit human approval.
