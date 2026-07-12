#!/usr/bin/env bash
set -euo pipefail

cat <<'MSG'
Initializing AI development template.

This script can initialize GitHub Spec Kit integrations for Claude Code and Codex.
It uses uvx to run GitHub's spec-kit installer.

Review this script before running in security-sensitive environments.
MSG

if ! command -v uvx >/dev/null 2>&1; then
  echo "uvx is not installed. Install uv first: https://docs.astral.sh/uv/" >&2
  echo "Skipping Spec Kit initialization."
  exit 0
fi

read -r -p "Initialize Spec Kit for Claude Code? [y/N] " init_claude
if [[ "$init_claude" =~ ^[Yy]$ ]]; then
  uvx --from git+https://github.com/github/spec-kit.git specify init --integration claude --script sh --here
fi

read -r -p "Initialize Spec Kit for Codex? [y/N] " init_codex
if [[ "$init_codex" =~ ^[Yy]$ ]]; then
  uvx --from git+https://github.com/github/spec-kit.git specify init --integration codex --script sh --here
fi

cat <<'MSG'

Next steps:
1. Fill docs/project-context.md
2. Fill docs/glossary.md
3. Customize Makefile for your stack
4. Create the first GitHub Issue
5. Start from specification, not implementation
MSG
