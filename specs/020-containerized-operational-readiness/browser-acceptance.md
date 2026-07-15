# Browser acceptance: T009

## Run identity

- Timestamp: `2026-07-15T00:31:48Z` (`2026-07-15T09:31:48+09:00`)
- HEAD: `b62b4e6ff0ee05e26bd2a16f55176ea611d6fe31`
- Requirements: REQ-014, REQ-015, REQ-016
- Named validation: `integration`

## Result

**UNAVAILABLE — not a browser PASS.**

The Codex in-app browser was selected according to the approved browser
clarification, but the browser runtime returned:

```text
Browser is not available: iab
```

The temporary-container prerequisite was also unavailable in this execution
environment. `docker info --format '{{.ServerVersion}}'` returned:

```text
permission denied while trying to connect to the docker API at unix:///Users/kume/.colima/default/docker.sock
```

No temporary container or browser test data was created, so no browser-data or
Docker-resource cleanup was required. No application source, API, Web UI asset,
dependency, schema, migration, framework, policy, or prior evidence was changed.

The following REQ-014 browser checks were **not run** and must not be inferred
to have passed:

- Project creation
- Task creation
- Tag creation and Task attachment
- Comment creation and payload-free Activity display
- Task keyword/status/tag/due-date query behavior
- Project dashboard aggregates
- Reload persistence
- Desktop viewport behavior
- Mobile viewport behavior
- Browser console errors
- External-network requests
- Temporary-data and temporary-resource cleanup

This is the honest REQ-015 outcome for this HEAD. Automated integration and
container validation do not substitute for browser acceptance.

## Named validation result

Command:

```bash
make integration-test
```

Result: **PASS** — `283 passed, 1 warning in 11.02s`. The warning was the
existing Starlette `TestClient` deprecation warning for the installed `httpx`
compatibility layer.

## Reproducible human rerun

Run these steps from this exact HEAD on a workstation where Docker and the
in-app browser are available:

1. Record `git rev-parse HEAD` and confirm it is
   `b62b4e6ff0ee05e26bd2a16f55176ea611d6fe31`.
2. Run `make container-build` and `make container-smoke` to confirm the mandatory
   automated container boundary before browser acceptance.
3. Start an isolated temporary container from `local-project-board:local` with
   a unique container name, a unique named volume mounted at `/data`, and an
   ephemeral loopback publish (`127.0.0.1::8000`). Record the assigned localhost
   port and wait for the container health status to become `healthy`.
4. Open `http://127.0.0.1:<assigned-port>/` in the in-app browser. At a desktop
   viewport, create a uniquely named Project, Task, and Tag; attach the Tag to
   the Task; add a uniquely identifiable synthetic Comment; verify the
   payload-free Comment Activity and Project dashboard; exercise keyword,
   status, Tag, and due-date Task queries; reload and verify persistence.
5. Repeat the layout checks at a mobile viewport. Confirm the browser console
   contains no errors and the page made no requests to non-loopback origins.
6. Delete the temporary Comment, Task, and Project through the UI where the UI
   supports those operations. Stop and remove only the uniquely named container
   and volume (and any uniquely tagged image created for this rerun). Do not use
   prune or mutate unrelated Docker resources.
7. Record each check as PASS or FAIL, the exact HEAD, viewport sizes, console
   result, observed request origins, temporary resource names, and cleanup
   outcome. A failure or unavailable browser must not be reported as PASS.
