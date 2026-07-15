from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
COMPOSE = PROJECT_ROOT / "compose.yaml"


def _child_keys(lines: list[str], parent: str, indent: int) -> list[str]:
    parent_line = f"{' ' * indent}{parent}:"
    parent_index = lines.index(parent_line)
    child_indent = indent + 2
    keys: list[str] = []

    for line in lines[parent_index + 1 :]:
        if line and not line.startswith(" " * child_indent):
            break
        if line.startswith(" " * child_indent) and not line.startswith(
            " " * (child_indent + 1)
        ):
            keys.append(line.strip().removesuffix(":"))
    return keys


def test_compose_defines_only_the_project_board_service() -> None:
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()

    assert _child_keys(lines, "services", 0) == ["project-board"]
    assert "    build:" in lines
    assert "      context: ." in lines
    assert "      dockerfile: Dockerfile" in lines


def test_compose_publishes_only_the_fixed_localhost_port() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert '      - "127.0.0.1:8000:8000"' in compose
    assert '      - "8000:8000"' not in compose
    assert "0.0.0.0:8000:8000" not in compose
    assert "network_mode: host" not in compose


def test_compose_mounts_only_the_named_data_volume() -> None:
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()

    assert "      - project-board-data:/data" in lines
    assert _child_keys(lines, "volumes", 0) == ["project-board-data: {}"]
    assert "project_board.sqlite3" not in "\n".join(lines)


def test_compose_has_bounded_lifecycle_and_runtime_hardening() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "    init: true" in compose
    assert '    restart: "on-failure:3"' in compose
    assert "    cap_drop:\n      - ALL" in compose
    assert "    security_opt:\n      - no-new-privileges:true" in compose
    assert "privileged: true" not in compose


def test_compose_healthcheck_requires_the_exact_local_health_response() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "    healthcheck:" in compose
    assert "      test:\n        - CMD\n        - python\n        - -c" in compose
    assert "http://127.0.0.1:8000/health" in compose
    assert "response.status == 200" in compose
    assert "json.load(response) ==\n          {'status': 'ok'}" in compose
    assert "      interval: 10s" in compose
    assert "      timeout: 3s" in compose
    assert "      start_period: 5s" in compose
    assert "      retries: 3" in compose
    assert "curl" not in compose
    assert "wget" not in compose


def test_compose_introduces_no_external_or_secret_configuration() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "http://" not in compose.replace("http://127.0.0.1:8000/health", "")
    assert "https://" not in compose
    assert "env_file:" not in compose
    assert "environment:" not in compose
    assert "secrets:" not in compose
