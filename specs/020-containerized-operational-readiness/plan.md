# Plan: Containerized operational readiness

## Existing architecture

- The application wheel already includes fixed HTML/CSS/JavaScript assets.
- `project_board.main:app` uses `sqlite:///project_board.sqlite3`, initializes
  metadata at startup, and exposes a database-independent `/health` endpoint.
- Ordinary quality runs through `make validate`; Feature 021 permits dedicated
  `container-build` and `container-smoke` contract targets.
- GitHub Actions currently has one validation job using Python 3.11.

## Implementation design

1. Add a pinned two-stage Dockerfile that builds dependency/application wheels,
   installs them in a minimal runtime, creates fixed UID/GID, owns `/data`, and
   starts exec-form Uvicorn as non-root with a standard-library healthcheck.
2. Add a deny-oriented `.dockerignore` retaining only wheel inputs and excluding
   source-control, test/spec/evidence, environment, secret, cache, database, and
   artifact paths.
3. Add a single-service Compose file with localhost publish, named `/data`
   volume, init, health, capability drop, no-new-privileges, and no restart loop.
4. Implement a standard-library smoke helper with unique exact resource names,
   ephemeral port, HTTP/API/persistence/log checks, Git/SQLite fingerprints, and
   unconditional exact-resource cleanup.
5. Add static contract and mocked lifecycle-failure unit tests; CI remains the
   authoritative real Docker smoke evidence.
6. Add opt-in Make targets without changing `validate`; add a separate
   timeout-bound CI job and always cleanup its known local image.
7. Document reproducible local operations, ordinary versus destructive stop,
   persistence, troubleshooting, and safety boundaries.
8. Run targeted/full/container validation, then use the in-app browser against a
   temporary container for the accepted UI flow and clean its test data.
9. Record validation, finalize exact-HEAD evidence, run weakening and five review
   shards, then use the approved high-risk publish flow and stop before merge.

## Rollback

All changes are additive operational files or CI/docs. Rollback is a normal
revert; no application data/schema transformation occurs. Named test resources
are removed by the smoke helper, while user Compose data is removed only by an
explicit warned command.
