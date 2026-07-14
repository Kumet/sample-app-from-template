# Feature specification: Container validation target policy

## Status

Approved

## Purpose

Allow an approved version 2 validation contract to request dedicated container
build and smoke targets without making Docker part of the repository's ordinary
validation path or weakening exact Make-target allowlist enforcement.

## Requirements

- REQ-001: Repository policy MUST allow the exact Make targets
  `container-build` and `container-smoke` in version 2 validation contracts.
- REQ-002: Every previously allowed Make target MUST remain allowed with
  unchanged command construction.
- REQ-003: Target authorization MUST remain exact, case-sensitive membership;
  prefixes, suffixes, partial matches, and case variants MUST be rejected.
- REQ-004: Unsafe target strings, including shell syntax, whitespace, arguments,
  or attempts to expand to multiple targets, MUST fail closed.
- REQ-005: Container targets MUST run only when explicitly named by a validation
  contract and MUST NOT become dependencies of ordinary `make validate`.
- REQ-006: Features that do not request container validation MUST retain their
  existing validation commands and MUST remain independent of Docker.
- REQ-007: Policy enforcement, spec lint, validation, review, and approval gates
  MUST remain unchanged except for the two exact additions to the allowlist.

## Acceptance criteria

- [x] AC-001: Version 2 contracts can map one or more validation names to
  `container-build` and `container-smoke`, producing only the corresponding
  `make` command tuples.
- [x] AC-002: Existing allowed targets remain accepted and arbitrary targets,
  `container-build-extra`, and `Container-Build` remain rejected.
- [x] AC-003: Injection-shaped targets such as `container-build; command`, target
  strings with arguments, and multiple-target strings are rejected.
- [x] AC-004: A contract without container targets has identical parsed command
  behavior, and the ordinary `validate` target has no Docker dependency.
- [ ] AC-005: Targeted regression tests, full validation, all review shards, and
  CI pass on the same reviewed HEAD before merge.

## Clarifications

- The approved human prompt is the source of truth; no GitHub Issue is required.
- Existing allowlist enforcement is correct and remains authoritative. No
  wildcard, alias, normalization, or prefix matching is introduced.
- This Feature authorizes validation command construction only. It does not add
  container Make recipes and does not execute Docker by itself.
- Container validation remains opt-in per validation contract. `make validate`
  retains its current dependency graph and behavior.
- The sample repository and Feature 020 artifacts are read-only and out of
  scope until this template Feature is merged.

## Scope

Allowed: `.agent-policy.toml`, policy/spec-lint regression tests, this Feature
directory, and minimal repository-neutral documentation.

Forbidden: `scripts/agent/**`, Makefile behavior changes, Docker requirements,
sample repository changes, runtime evidence rewriting, wildcard authorization,
or weakening validation, review, and approval gates.

## Definition of done

The exact targets are allowlisted, all acceptance criteria are covered by
regressions, `make validate` remains Docker-independent, exact-HEAD review and CI
pass, and the reviewed branch is merged through a pull request.
