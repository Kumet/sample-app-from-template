from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
DOCKERFILE = PROJECT_ROOT / "Dockerfile"
DOCKERIGNORE = PROJECT_ROOT / ".dockerignore"


def test_dockerfile_builds_wheels_in_a_pinned_separate_stage() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert dockerfile.count("FROM python:3.11.11-slim-bookworm") == 2
    assert "FROM python:3.11.11-slim-bookworm AS builder" in dockerfile
    assert "FROM python:3.11.11-slim-bookworm AS runtime" in dockerfile
    assert "COPY pyproject.toml README.md ./" in dockerfile
    assert "COPY src/ ./src/" in dockerfile
    assert "python -m pip wheel --wheel-dir /wheels ." in dockerfile
    assert "COPY --from=builder /wheels /wheels" in dockerfile
    assert (
        "python -m pip install --no-index --find-links=/wheels "
        "local-project-board" in dockerfile
    )
    assert "COPY ." not in dockerfile


def test_runtime_is_fixed_non_root_and_uses_data_as_its_working_directory() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "groupadd --gid 10001 project-board" in dockerfile
    assert "useradd --uid 10001 --gid 10001" in dockerfile
    assert "chown 10001:10001 /data" in dockerfile
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
    assert "PYTHONUNBUFFERED=1" in dockerfile
    assert "WORKDIR /data" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "project_board.sqlite3" not in dockerfile
    assert (
        'CMD ["python", "-m", "uvicorn", "project_board.main:app", '
        '"--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    )
    assert "--reload" not in dockerfile
    assert "--workers" not in dockerfile


def test_healthcheck_uses_only_python_standard_library_and_exact_response() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    healthcheck = next(
        line for line in dockerfile.splitlines() if "urllib.request.urlopen" in line
    )
    assert "http://127.0.0.1:8000/health" in healthcheck
    assert "response.status == 200" in healthcheck
    assert "json.load(response) == {'status': 'ok'}" in healthcheck
    assert "curl" not in dockerfile
    assert "wget" not in dockerfile
    assert "apt-get" not in dockerfile


def test_build_context_is_an_explicit_wheel_input_allowlist() -> None:
    rules = [
        line
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]

    assert rules[:5] == ["**", "!pyproject.toml", "!README.md", "!src/", "!src/**"]

    required_denies = {
        ".git/**",
        "tests/**",
        "specs/**",
        ".agent-work/**",
        ".agent-worktree-owned",
        ".agents/**",
        ".codex/**",
        ".env.*",
        ".venv/**",
        "venv/**",
        "env/**",
        "*.pem",
        "*.key",
        "**/__pycache__/**",
        ".pytest_cache/**",
        ".mypy_cache/**",
        ".ruff_cache/**",
        "build/**",
        "dist/**",
        "**/*.egg-info/**",
        "artifacts/**",
        "htmlcov/**",
        ".coverage.*",
        "coverage.xml",
        "*.sqlite",
        "*.sqlite3",
        "*.db",
    }
    assert required_denies <= set(rules)
    assert all(rule in rules[5:] for rule in required_denies)
