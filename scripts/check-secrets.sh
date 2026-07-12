#!/usr/bin/env bash
set -euo pipefail

# Lightweight guardrail. Replace or augment with gitleaks/trufflehog in real projects.

echo "Checking for obvious committed secret files..."

for pattern in \
  ".env" \
  ".env.*" \
  "*.pem" \
  "*.key" \
  "*.p12" \
  "*.pfx" \
  "credentials.*" \
  "secrets.*"; do
  if git ls-files --error-unmatch $pattern >/dev/null 2>&1; then
    echo "Potential secret file is tracked: $pattern" >&2
    exit 1
  fi
done

echo "Secret filename check passed."
