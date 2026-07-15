# Project-wide validation interface.

PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif command -v python3.11 >/dev/null 2>&1; then command -v python3.11; else command -v python3; fi)

.PHONY: setup format format-check lint typecheck test-framework test-app test integration-test build container-build container-smoke ci secrets validate clean work work-dry-run work-status validate-spec spec-lint work-resume work-abort deliver deliver-dry-run cleanup-worktree detect-stack init-stack doctor quality-check approve-scope approve-scope-dry-run request-scope request-scope-dry-run approve-recovery-patch approve-recovery-patch-dry-run migrate-contract migrate-contract-dry-run queue-add queue-status queue-run queue-cancel qualify-stacks release-check render-validation-log

setup:
	$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
	$(PYTHON) -m pip install -e '.[dev]'

format:
	$(PYTHON) -m ruff format .

format-check:
	$(PYTHON) -m ruff format --check .

lint:
	$(PYTHON) -m ruff check .

typecheck:
	$(PYTHON) -m mypy src

test-framework:
	$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
	$(PYTHON) -m unittest discover -s tests -p 'test_agent_*.py'
	$(PYTHON) -m unittest discover -s tests -p 'test_autonomous_*.py'
	$(PYTHON) -m unittest discover -s tests -p 'test_production_*.py'
	$(PYTHON) -m unittest discover -s tests -p 'test_spec_*.py'
	$(PYTHON) -m unittest discover -s tests -p 'test_delivery_*.py'

test-app:
	$(PYTHON) -m pytest tests/app/unit tests/app/integration

test: test-framework test-app

integration-test:
	$(PYTHON) -m pytest tests/app/integration

build:
	$(PYTHON) -m build

container-build:
	docker build --tag local-project-board:local .

container-smoke:
	$(PYTHON) -m pytest tests/app/operations/test_container_smoke.py::test_real_container_smoke_builds_and_recreates_persistent_runtime

ci: format-check lint typecheck test integration-test build

secrets:
	./scripts/check-secrets.sh

quality-check:
	$(PYTHON) scripts/agent/work.py quality-check

validate: quality-check secrets ci

clean:
	@echo "Build and cache cleanup is intentionally manual to avoid broad deletion."

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

request-scope:
	$(PYTHON) scripts/agent/work.py request-scope --feature "$(FEATURE)" --path "$(PATH)" --reason "$(REASON)"

request-scope-dry-run:
	$(PYTHON) scripts/agent/work.py request-scope-dry-run --feature "$(FEATURE)" --path "$(PATH)" --reason "$(REASON)"

approve-recovery-patch:
	$(PYTHON) scripts/agent/work.py approve-recovery-patch --feature "$(FEATURE)" --paths "$(PATHS)" --reason "$(REASON)"

approve-recovery-patch-dry-run:
	$(PYTHON) scripts/agent/work.py approve-recovery-patch-dry-run --feature "$(FEATURE)" --paths "$(PATHS)" --reason "$(REASON)"

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
