# Migration to template v1.0.0

## Feature contracts

Version 1 `validation.toml` contracts are rejected by default because they can
contain arbitrary executable arrays. Preview and migrate safe Make-only
contracts with:

```bash
make migrate-contract-dry-run FEATURE=<feature>
make migrate-contract FEATURE=<feature>
```

Unknown executables require human configuration and are never run.

## Repository policy

Add explicit quality gate enablement or a disabled reason, queue/call budgets,
and notification sinks to `.agent-policy.toml`.

## Runtime state

State version 1 remains readable. New authoritative evidence is stored in
version 1 `events.jsonl`; `validation-log.md` is generated from it.
