# Architecture

Document the current architecture here.

## System overview

The repository separates an external fixed-format feature contract, a
stack-independent Python orchestration core, and project-specific validation
commands exposed through Make.

## Main components

- `scripts/agent/parser.py`: feature contract and task parsing.
- `scripts/agent/work.py`: CLI, task loop, retries, state, and evidence.
- `scripts/agent/codex_runner.py`: non-interactive Codex boundary.
- `scripts/agent/validation.py`: command and changed-path gates.
- `scripts/agent/git_utils.py`: protected branch, dirty state, diff, and commit.
- `scripts/agent/spec_lint.py`: approved contract and traceability gate.
- `scripts/agent/state.py`: atomic resume/abort state.
- `scripts/agent/recovery.py`: classified bounded recovery policies.
- `scripts/agent/weakening.py`: structured test and CI weakening evidence.
- `scripts/agent/review.py`: independent schema-constrained Codex review.
- `scripts/agent/delivery.py`: risk-gated PR and CI delivery orchestration.
- `scripts/agent/worktree.py`: isolated framework-owned Git worktrees.
- `scripts/agent/adapters.py`: declarative stack detection and proposals.

## Data flow

Approved spec → next task → Codex → scope/security checks → named validation →
task completion and local commit. After all tasks, project-wide validation runs
with a bounded repair loop.

Autonomous delivery adds spec lint, isolated work, weakening inspection,
independent review, GitHub PR/check operations, monotonic risk escalation, and
optional low-risk PR merge. GitHub credentials remain outside Codex.

Production evidence is an append-only version 1 JSONL event stream. Gate
reduction requires validation, weakening, sharded review, and CI events to match
the exact PR HEAD SHA. Markdown validation logs are generated views. Queue,
approval, doctor, notifications, budgets, adapters, and release checks are
separate standard-library modules around this core.

## External dependencies

- Git
- GNU/BSD-compatible Make
- Python 3.11+
- Codex CLI for `make work` only

## Important constraints

- No shell evaluation of external task text.
- No push, merge, destructive Git cleanup, or secret-file reads.
- Work begins only on a clean, non-protected feature branch.
- Runtime evidence is local and ignored by Git.

## Known risks

- Codex CLI flags and behavior can vary by installed version.
- Command-based checks cannot prove subjective acceptance criteria.
- A failed attempt intentionally leaves its diff for repair or human review.
