# Project context

Fill this file immediately after creating a new repository from the template.

## Project purpose

Provide a reusable, stack-independent template for specification-driven AI
development. Approved external specifications can be executed one task at a
time by Codex with bounded retries, mechanical validation, evidence logging,
and safety stops.

## Users

- Developers creating Python, Web, AI, CLI, mobile, or other Git projects.
- AI coding agents implementing approved feature contracts.
- Human reviewers approving specifications, risk, and pull requests.

## Core workflows

- Prepare and approve a fixed-format feature specification externally.
- Place spec, plan, tasks, validation contract, and log under `specs/`.
- Run `make work FEATURE=<feature-id>` on a clean feature branch.
- Review local commits, evidence, and validation results before pushing.

## Domain rules

- Specifications are externally produced and are the source of truth.
- Task prose is never executable; tasks reference named validation commands.
- Project stacks adapt through Make targets and `validation.toml`.
- Retries are bounded and safety violations always require human review.

## Technical stack

- Language: Python 3.11+ for template automation; generated projects may vary.
- Framework: None required.
- Database: None required.
- Deployment: Out of scope for automated work.
- Testing: Python standard-library `unittest` plus project-defined Make targets.

## Data sensitivity

Secret files, credentials, tokens, signing material, personal information, and
production configuration must not be read or included in prompts or logs.

## Forbidden actions

- Do not read `.env`.
- Do not log personal information.
- Do not change authentication or authorization without explicit approval.
- Do not change production settings.

## Validation command

The standard validation command is:

```bash
make validate
```
