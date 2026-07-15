import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.operations import container_smoke
from scripts.operations.container_smoke import ResourceNames, request_http, run_smoke

RUN_ID = "unit-lifecycle"
PREFIX = f"project-board-smoke-{RUN_ID}"


class FakeDocker:
    def __init__(
        self,
        *,
        unsafe_logs: bool = False,
        fail_first_remove_once: bool = False,
        fail_boundary: bool = False,
    ) -> None:
        self.calls: list[tuple[list[str], bool, int]] = []
        self.unsafe_logs = unsafe_logs
        self.fail_first_remove_once = fail_first_remove_once
        self.fail_boundary = fail_boundary

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        args = list(arguments)
        self.calls.append((args, check, timeout))
        stdout = ""
        stderr = ""
        if args[:2] == ["git", "status"]:
            stdout = "?? existing-user-file\n"
        elif args[:3] == ["docker", "image", "inspect"]:
            stdout = json.dumps(
                [
                    {
                        "Config": {
                            "User": "10001:10001",
                            "WorkingDir": "/data",
                            "Env": [
                                "PATH=/usr/local/bin:/usr/bin:/bin",
                                "HOME=/data",
                                "PYTHONDONTWRITEBYTECODE=1",
                                "PYTHONUNBUFFERED=1",
                            ],
                            "Cmd": [
                                "python",
                                "-m",
                                "uvicorn",
                                "project_board.main:app",
                                "--host",
                                "0.0.0.0",
                                "--port",
                                "8000",
                            ],
                            "Healthcheck": {
                                "Test": [
                                    "CMD",
                                    "python",
                                    "-c",
                                    "import urllib.request; response = "
                                    "urllib.request.urlopen("
                                    "'http://127.0.0.1:8000/health'); "
                                    "assert response.status == 200; "
                                    "assert {'status': 'ok'}",
                                ]
                            },
                        }
                    }
                ]
            )
        elif args[:2] == ["docker", "inspect"]:
            stdout = json.dumps(
                [
                    {
                        "State": {
                            "Status": "running",
                            "Health": {"Status": "healthy"},
                        },
                        "Config": {"User": "10001:10001"},
                    }
                ]
            )
        elif args[:2] == ["docker", "exec"]:
            stdout = "10001\n"
        elif args[:2] == ["docker", "port"]:
            port = "49152" if args[2].endswith("-second") else "49151"
            stdout = f"127.0.0.1:{port}\n"
        elif args[:2] == ["docker", "logs"]:
            stderr = (
                "password=should-not-be-logged\n"
                if self.unsafe_logs
                else "Application startup complete.\n"
            )
        returncode = 0
        if (
            args[:2] == ["docker", "run"]
            and f"{PREFIX}-boundary" in args
            and self.fail_boundary
        ):
            returncode = 1
            stderr = "pristine image assertion failed"
        first_remove = ["docker", "rm", "--force", f"{PREFIX}-first"]
        if args == first_remove and self.fail_first_remove_once:
            self.fail_first_remove_once = False
            returncode = 1
            stderr = "induced removal failure"
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)


class FakeHttp:
    def __init__(self, *, lose_persisted_project: bool = False) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []
        self.lose_persisted_project = lose_persisted_project
        self.project: dict[str, object] | None = None

    def __call__(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((url, method, payload))
        if url.endswith("/health"):
            return 200, {"content-type": "application/json"}, b'{"status":"ok"}'
        if url.endswith("/static/app.css"):
            return 200, {"content-type": "text/css"}, b":root { color: black; }"
        if url.endswith("/static/app.js"):
            return 200, {"content-type": "text/javascript"}, b'fetch("/api/projects")'
        if url.endswith("/"):
            return 200, {"content-type": "text/html"}, b"Local Project Board"
        if url.endswith("/api/projects") and method == "POST":
            self.project = {
                "id": 7,
                "name": payload["name"] if payload else "",
                "description": None,
                "created_at": "2026-07-15T00:00:00Z",
                "updated_at": "2026-07-15T00:00:00Z",
            }
            return (
                201,
                {"content-type": "application/json"},
                json.dumps(self.project).encode(),
            )
        if url.endswith("/api/projects/7"):
            project = self.project
            if self.lose_persisted_project and ":49152/" in url:
                project = {"detail": "Project not found"}
                return (
                    404,
                    {"content-type": "application/json"},
                    json.dumps(project).encode(),
                )
            return (
                200,
                {"content-type": "application/json"},
                json.dumps(project).encode(),
            )
        raise AssertionError(f"Unexpected HTTP request: {method} {url}")


def _commands(fake: FakeDocker) -> list[list[str]]:
    return [call[0] for call in fake.calls]


def test_real_container_smoke_builds_and_recreates_persistent_runtime() -> None:
    """Exercise the complete smoke lifecycle against the Docker daemon."""
    result = run_smoke()

    assert result.resources.first_container != result.resources.second_container
    assert result.first_url.startswith("http://127.0.0.1:")
    assert result.second_url.startswith("http://127.0.0.1:")
    assert result.project_id > 0
    assert result.project_name == (
        f"Container smoke {result.resources.first_container}"
    )
    assert result.repository_before.git_status == result.repository_after.git_status
    assert result.repository_before.database == result.repository_after.database


def test_smoke_uses_unique_exact_resources_and_recreates_with_one_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docker = FakeDocker()
    http = FakeHttp()
    local_database = tmp_path / "project_board.sqlite3"
    local_database.write_bytes(b"repository database sentinel")
    monkeypatch.setattr(container_smoke, "LOCAL_DATABASE", local_database)

    result = run_smoke(command=docker, http=http, run_id=RUN_ID)

    commands = _commands(docker)
    assert ["docker", "build", "--tag", f"{PREFIX}:local", "."] in commands
    boundary_run = next(
        command
        for command in commands
        if command[:2] == ["docker", "run"] and "--entrypoint" in command
    )
    assert boundary_run[boundary_run.index("--name") + 1] == f"{PREFIX}-boundary"
    assert boundary_run[boundary_run.index("--network") + 1] == "none"
    assert boundary_run[boundary_run.index("--entrypoint") + 1] == "python"

    runs = [
        command
        for command in commands
        if command[:2] == ["docker", "run"] and "--detach" in command
    ]
    assert len(runs) == 2
    assert runs[0][runs[0].index("--name") + 1] == f"{PREFIX}-first"
    assert runs[1][runs[1].index("--name") + 1] == f"{PREFIX}-second"
    for run in runs:
        assert run[run.index("--publish") + 1] == "127.0.0.1::8000"
        assert (
            run[run.index("--mount") + 1]
            == f"type=volume,source={PREFIX}-data,target=/data"
        )

    first_remove = commands.index(["docker", "rm", "--force", f"{PREFIX}-first"])
    second_run = commands.index(runs[1])
    assert first_remove < second_run
    assert ["docker", "rm", "--force", f"{PREFIX}-second"] in commands
    assert ["docker", "rm", "--force", f"{PREFIX}-boundary"] in commands
    assert ["docker", "network", "rm", f"{PREFIX}-network"] in commands
    assert ["docker", "volume", "rm", f"{PREFIX}-data"] in commands
    assert ["docker", "image", "rm", "--force", f"{PREFIX}:local"] in commands
    assert not any("prune" in argument for command in commands for argument in command)
    assert (
        commands.count(["git", "status", "--porcelain=v1", "--untracked-files=all"])
        == 2
    )
    assert result.repository_before.git_status == "?? existing-user-file\n"
    assert result.repository_before == result.repository_after
    database_exists, database_size, database_digest = result.repository_before.database
    assert database_exists is True
    assert database_size == len(b"repository database sentinel")
    assert len(database_digest) == 64
    assert local_database.read_bytes() == b"repository database sentinel"

    persisted_gets = [
        url for url, method, _ in http.calls if method == "GET" and url.endswith("/7")
    ]
    assert persisted_gets == [
        "http://127.0.0.1:49151/api/projects/7",
        "http://127.0.0.1:49152/api/projects/7",
    ]


def test_repository_local_sqlite_mutation_fails_and_cleans_exact_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docker = FakeDocker()
    local_database = tmp_path / "project_board.sqlite3"
    local_database.write_bytes(b"before smoke")
    monkeypatch.setattr(container_smoke, "LOCAL_DATABASE", local_database)

    class MutatingHttp(FakeHttp):
        def __call__(
            self,
            url: str,
            *,
            method: str = "GET",
            payload: dict[str, str] | None = None,
        ) -> tuple[int, dict[str, str], bytes]:
            response = super().__call__(url, method=method, payload=payload)
            if url == "http://127.0.0.1:49152/api/projects/7":
                local_database.write_bytes(b"changed during smoke")
            return response

    with pytest.raises(AssertionError, match="repository-local SQLite"):
        run_smoke(command=docker, http=MutatingHttp(), run_id=RUN_ID)

    commands = _commands(docker)
    assert (
        commands.count(["git", "status", "--porcelain=v1", "--untracked-files=all"])
        == 2
    )
    assert ["docker", "rm", "--force", f"{PREFIX}-second"] in commands
    assert ["docker", "volume", "rm", f"{PREFIX}-data"] in commands
    assert ["docker", "network", "rm", f"{PREFIX}-network"] in commands
    assert ["docker", "image", "rm", "--force", f"{PREFIX}:local"] in commands


def test_persistence_failure_still_cleans_every_created_exact_resource() -> None:
    docker = FakeDocker()

    with pytest.raises(AssertionError, match="Persisted Project"):
        run_smoke(
            command=docker,
            http=FakeHttp(lose_persisted_project=True),
            run_id=RUN_ID,
        )

    cleanup = [
        command
        for command in _commands(docker)
        if command[:3]
        in (
            ["docker", "rm", "--force"],
            ["docker", "network", "rm"],
            ["docker", "volume", "rm"],
            ["docker", "image", "rm"],
        )
    ]
    assert ["docker", "rm", "--force", f"{PREFIX}-second"] in cleanup
    assert ["docker", "network", "rm", f"{PREFIX}-network"] in cleanup
    assert ["docker", "volume", "rm", f"{PREFIX}-data"] in cleanup
    assert ["docker", "image", "rm", "--force", f"{PREFIX}:local"] in cleanup
    assert all(PREFIX in " ".join(command) for command in cleanup)


def test_image_boundary_failure_cleans_its_container_and_image() -> None:
    docker = FakeDocker(fail_boundary=True)

    with pytest.raises(AssertionError, match="filesystem boundary failed"):
        run_smoke(command=docker, http=FakeHttp(), run_id=RUN_ID)

    commands = _commands(docker)
    assert ["docker", "rm", "--force", f"{PREFIX}-boundary"] in commands
    assert ["docker", "image", "rm", "--force", f"{PREFIX}:local"] in commands
    assert ["docker", "network", "create", f"{PREFIX}-network"] not in commands
    assert ["docker", "volume", "create", f"{PREFIX}-data"] not in commands


def test_sensitive_container_log_failure_is_rejected_after_persistence() -> None:
    docker = FakeDocker(unsafe_logs=True)

    with pytest.raises(AssertionError, match="rejected pattern"):
        run_smoke(command=docker, http=FakeHttp(), run_id=RUN_ID)

    commands = _commands(docker)
    assert ["docker", "rm", "--force", f"{PREFIX}-second"] in commands
    assert ["docker", "volume", "rm", f"{PREFIX}-data"] in commands


def test_failed_intermediate_removal_is_retried_during_final_cleanup() -> None:
    docker = FakeDocker(fail_first_remove_once=True)

    with pytest.raises(AssertionError, match="Could not remove container"):
        run_smoke(command=docker, http=FakeHttp(), run_id=RUN_ID)

    commands = _commands(docker)
    first_remove = ["docker", "rm", "--force", f"{PREFIX}-first"]
    assert commands.count(first_remove) == 2
    assert ["docker", "volume", "rm", f"{PREFIX}-data"] in commands
    assert ["docker", "network", "rm", f"{PREFIX}-network"] in commands
    assert ["docker", "image", "rm", "--force", f"{PREFIX}:local"] in commands


def test_resource_names_reject_shell_or_docker_option_characters() -> None:
    with pytest.raises(ValueError, match="unsupported Docker name"):
        ResourceNames.unique("unsafe/name")


def test_real_http_boundary_rejects_non_loopback_urls_before_requesting() -> None:
    with pytest.raises(AssertionError, match="restricted to loopback"):
        request_http("https://example.com/health")
