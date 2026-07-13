# Review timeout recovery

## Status

Implemented

## Purpose

Allow complete independent-review inputs to finish without weakening review,
scope, validation, or high-risk approval gates.

## Requirements

- REQ-001: Each Codex review shard may run for up to 600 seconds.
- REQ-002: Review input limits, required shards, fail-closed behavior, and all
  delivery gates remain unchanged.

## Acceptance criteria

- [x] AC-001: The review subprocess uses the named 600-second timeout.
- [x] AC-002: A timeout still raises a closed failure identifying the configured limit.
- [x] AC-003: `make validate` passes.

## Scope

Only `scripts/agent/review.py`, its existing unit test, and the specification
artifacts under `specs/006-review-timeout-recovery/**` may change. Feature 001
risk and scope are unchanged.
