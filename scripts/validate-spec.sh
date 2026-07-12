#!/usr/bin/env bash
set -euo pipefail

SPEC_DIR="${1:-}"

if [[ -z "$SPEC_DIR" ]]; then
  echo "Usage: scripts/validate-spec.sh specs/<number>-<feature>" >&2
  exit 1
fi

for file in spec.md plan.md tasks.md validation.toml validation-log.md; do
  if [[ ! -f "$SPEC_DIR/$file" ]]; then
    echo "Missing required artifact: $SPEC_DIR/$file" >&2
    exit 1
  fi
done

echo "Spec artifacts exist: $SPEC_DIR"
