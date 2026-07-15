from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

ORIGINAL_VALIDATE_JOB = """  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Upgrade pip
        run: python -m pip install --upgrade pip

      - name: Set up project
        run: make setup

      - name: Validate template files
        run: |
          test -f AGENTS.md
          test -f CLAUDE.md
          test -f Makefile
          test -f .agent-policy.toml
          test -f docs/project-context.md
          test -f .github/pull_request_template.md
          test -f schemas/review-result.schema.json
          test -f adapters/generic.toml

      - name: Check scripts are executable
        run: |
          test -x scripts/init-project.sh
          test -x scripts/check-secrets.sh
          test -x scripts/validate-spec.sh

      - name: Run project validation
        run: make validate

      - name: Qualify stack fixtures
        run: make qualify-stacks"""


def _job_block(workflow: str, job: str) -> str:
    lines = workflow.splitlines()
    start = lines.index(f"  {job}:")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("  ")
            and not lines[index].startswith("    ")
            and lines[index].endswith(":")
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_real_container_checks_run_in_a_separate_bounded_job() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    validate_job = _job_block(workflow, "validate")
    container_job = _job_block(workflow, "container")

    assert "timeout-minutes:" not in validate_job
    assert "make container-build" not in validate_job
    assert "make container-smoke" not in validate_job

    assert "    runs-on: ubuntu-latest" in container_job
    assert "    timeout-minutes: 30" in container_job
    assert "        uses: actions/checkout@v4" in container_job
    assert "        uses: actions/setup-python@v5" in container_job
    assert '          python-version: "3.11"' in container_job
    assert container_job.count("        run: make container-build") == 1
    assert container_job.count("        run: make container-smoke") == 1


def test_existing_validation_job_is_preserved_exactly() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert _job_block(workflow, "validate").rstrip() == ORIGINAL_VALIDATE_JOB


def test_container_job_has_exact_always_run_cleanup_without_forbidden_actions() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    container_job = _job_block(workflow, "container")

    assert "      - name: Remove local build image" in container_job
    assert "        if: always()" in container_job
    assert (
        "        run: docker image rm --force local-project-board:local"
        in container_job
    )
    assert container_job.count("docker ") == 1
    assert [
        line.strip()
        for line in container_job.splitlines()
        if line.strip().startswith("uses:")
    ] == ["uses: actions/checkout@v4", "uses: actions/setup-python@v5"]

    normalized = container_job.lower()
    forbidden = (
        "continue-on-error:",
        "docker login",
        "docker push",
        "docker system prune",
        "docker image prune",
        "docker container prune",
        "docker volume prune",
        "docker network prune",
        "env:",
        "secrets.",
        "environment:",
        "deploy",
        "gh ",
    )
    for unsafe_contract in forbidden:
        assert unsafe_contract not in normalized
