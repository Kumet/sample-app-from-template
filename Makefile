# Project-wide validation interface.
# Override these commands for your actual stack.

PYTHON := $(shell command -v python3.11 2>/dev/null || command -v python3)

.PHONY: setup lint typecheck test ci secrets validate format clean work work-dry-run work-status validate-spec spec-lint work-resume work-abort deliver deliver-dry-run cleanup-worktree detect-stack init-stack doctor quality-check approve-scope approve-scope-dry-run migrate-contract migrate-contract-dry-run queue-add queue-status queue-run queue-cancel qualify-stacks release-check render-validation-log

setup:
	@echo "TODO: replace with project setup command, e.g. npm ci / uv sync / pip install -e ."

lint:
	@echo "TODO: replace with lint command"

format:
	@echo "TODO: replace with format command"

typecheck:
	@echo "TODO: replace with typecheck command"

test:
	$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py'

ci: lint typecheck test

secrets:
	./scripts/check-secrets.sh

quality-check:
	$(PYTHON) scripts/agent/work.py quality-check

validate: quality-check secrets ci

clean:
	@echo "TODO: replace with clean command"

work:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py run --feature "$(FEATURE)"

work-dry-run:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py dry-run --feature "$(FEATURE)"

work-status:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py status --feature "$(FEATURE)"

validate-spec:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	./scripts/validate-spec.sh "specs/$(FEATURE)"

spec-lint:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py spec-lint --feature "$(FEATURE)"

work-resume:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py resume --feature "$(FEATURE)"

work-abort:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py abort --feature "$(FEATURE)"

deliver:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py deliver --feature "$(FEATURE)"

deliver-dry-run:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py deliver-dry-run --feature "$(FEATURE)"

cleanup-worktree:
	@test -n "$(FEATURE)" || (echo "FEATURE is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py cleanup-worktree --feature "$(FEATURE)"

detect-stack:
	$(PYTHON) scripts/agent/work.py detect-stack

init-stack:
	@test -n "$(STACK)" || (echo "STACK is required" >&2; exit 2)
	$(PYTHON) scripts/agent/work.py init-stack --stack "$(STACK)"

doctor:
	$(PYTHON) scripts/agent/work.py doctor

approve-scope:
	$(PYTHON) scripts/agent/work.py approve-scope --feature "$(FEATURE)" --path "$(PATH)" --reason "$(REASON)"

approve-scope-dry-run:
	$(PYTHON) scripts/agent/work.py approve-scope-dry-run --feature "$(FEATURE)" --path "$(PATH)" --reason "$(REASON)"

migrate-contract:
	$(PYTHON) scripts/agent/work.py migrate-contract --feature "$(FEATURE)"

migrate-contract-dry-run:
	$(PYTHON) scripts/agent/work.py migrate-contract-dry-run --feature "$(FEATURE)"

queue-add:
	$(PYTHON) scripts/agent/work.py queue-add --feature "$(FEATURE)"

queue-status:
	$(PYTHON) scripts/agent/work.py queue-status

queue-run:
	$(PYTHON) scripts/agent/work.py queue-run

queue-cancel:
	$(PYTHON) scripts/agent/work.py queue-cancel --feature "$(FEATURE)"

qualify-stacks:
	$(PYTHON) scripts/agent/work.py qualify-stacks

release-check: validate
	$(PYTHON) scripts/agent/work.py release-check

render-validation-log:
	$(PYTHON) scripts/agent/work.py render-validation-log --feature "$(FEATURE)"
