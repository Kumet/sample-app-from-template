#!/usr/bin/env python3
"""Run an isolated real-container HTTP and SQLite persistence smoke test."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_DATABASE = PROJECT_ROOT / "project_board.sqlite3"
CONTAINER_PORT = "8000/tcp"
COMMAND_TIMEOUT_SECONDS = 30
BUILD_TIMEOUT_SECONDS = 900
HEALTH_TIMEOUT_SECONDS = 90
HTTP_TIMEOUT_SECONDS = 10
LOG_REJECTIONS = (
    re.compile(r"traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"-----begin (?:[a-z ]+ )?private key-----", re.IGNORECASE),
    re.compile(
        r"\b(?:password|passwd|secret|client[_-]?secret|private[_-]?key|"
        r"api[_-]?key|access[_-]?token|auth(?:orization)?)\b"
        r"\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
)


class Command(Protocol):
    """A subprocess-compatible command boundary used by lifecycle unit tests."""

    def __call__(
        self,
        arguments: Sequence[str],
        *,
        check: bool = True,
        timeout: int = COMMAND_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]: ...


class HttpRequest(Protocol):
    """A small HTTP boundary that keeps lifecycle tests Docker-independent."""

    def __call__(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]: ...


@dataclass(frozen=True)
class ResourceNames:
    """Exact Docker resource names owned by one smoke run."""

    image: str
    network: str
    volume: str
    boundary_container: str
    first_container: str
    second_container: str

    @classmethod
    def unique(cls, run_id: str | None = None) -> ResourceNames:
        suffix = run_id or uuid.uuid4().hex
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", suffix):
            raise ValueError("Smoke run ID contains unsupported Docker name characters")
        prefix = f"project-board-smoke-{suffix}"
        return cls(
            image=f"{prefix}:local",
            network=f"{prefix}-network",
            volume=f"{prefix}-data",
            boundary_container=f"{prefix}-boundary",
            first_container=f"{prefix}-first",
            second_container=f"{prefix}-second",
        )


@dataclass
class CreatedResources:
    """Track only successfully created resources for exact cleanup."""

    image: bool = False
    network: bool = False
    volume: bool = False
    boundary_container: bool = False
    first_container: bool = False
    second_container: bool = False


@dataclass(frozen=True)
class RepositoryFingerprint:
    """Observable repository state that a container smoke must not mutate."""

    git_status: str
    database: tuple[bool, int, str]


@dataclass(frozen=True)
class SmokeResult:
    """Observable evidence produced by one successful real-container smoke."""

    resources: ResourceNames
    repository_before: RepositoryFingerprint
    repository_after: RepositoryFingerprint
    first_url: str
    second_url: str
    project_id: int
    project_name: str


def run_command(
    arguments: Sequence[str],
    *,
    check: bool = True,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run a bounded local command from the repository root."""
    return subprocess.run(
        list(arguments),
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def request_http(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """Make one bounded standard-library HTTP request."""
    parsed_url = urllib.parse.urlsplit(url)
    if (
        parsed_url.scheme != "http"
        or parsed_url.hostname != "127.0.0.1"
        or parsed_url.port is None
    ):
        raise AssertionError(f"Smoke HTTP is restricted to loopback: {url!r}")
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            response_headers = {
                key.lower(): value for key, value in response.headers.items()
            }
            return response.status, response_headers, response.read()
    except urllib.error.HTTPError as error:
        body = error.read()
        raise AssertionError(
            f"HTTP {method} {url} returned {error.code}: {body[:500]!r}"
        ) from error
    except urllib.error.URLError as error:
        raise AssertionError(f"HTTP {method} {url} failed: {error.reason}") from error


def _database_fingerprint(path: Path) -> tuple[bool, int, str]:
    if not path.exists():
        return False, 0, ""
    digest = hashlib.sha256()
    with path.open("rb") as database:
        for chunk in iter(lambda: database.read(1024 * 1024), b""):
            digest.update(chunk)
    return True, path.stat().st_size, digest.hexdigest()


def fingerprint_repository(command: Command) -> RepositoryFingerprint:
    """Fingerprint Git state and the unchanged local SQLite contract path."""
    status = command(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"]
    ).stdout
    return RepositoryFingerprint(status, _database_fingerprint(LOCAL_DATABASE))


def _inspect_container(command: Command, container: str) -> dict[str, Any]:
    output = command(["docker", "inspect", container]).stdout
    inspected = json.loads(output)
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise AssertionError(f"Docker returned invalid inspection data for {container}")
    result = inspected[0]
    if not isinstance(result, dict):
        raise AssertionError(f"Docker returned invalid inspection data for {container}")
    return result


def _inspect_image(command: Command, image: str) -> dict[str, Any]:
    output = command(["docker", "image", "inspect", image]).stdout
    inspected = json.loads(output)
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise AssertionError(f"Docker returned invalid inspection data for {image}")
    result = inspected[0]
    if not isinstance(result, dict):
        raise AssertionError(f"Docker returned invalid inspection data for {image}")
    return result


def _verify_image_boundary(
    command: Command,
    names: ResourceNames,
    created: CreatedResources,
) -> None:
    """Inspect the built image and its pristine runtime filesystem."""
    inspected = _inspect_image(command, names.image)
    config = inspected.get("Config", {})
    if config.get("User") != "10001:10001":
        raise AssertionError("Built image is not configured for UID/GID 10001:10001")
    if config.get("WorkingDir") != "/data":
        raise AssertionError("Built image working directory is not /data")

    environment = set(config.get("Env", []))
    required_environment = {
        "HOME=/data",
        "PYTHONDONTWRITEBYTECODE=1",
        "PYTHONUNBUFFERED=1",
    }
    if not required_environment.issubset(environment):
        raise AssertionError("Built image is missing required runtime environment")

    expected_command = [
        "python",
        "-m",
        "uvicorn",
        "project_board.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    if config.get("Cmd") != expected_command:
        raise AssertionError("Built image command does not match the runtime contract")

    health_test = config.get("Healthcheck", {}).get("Test", [])
    health_contract = " ".join(str(part) for part in health_test)
    if (
        not health_test
        or health_test[0] != "CMD"
        or "urllib.request" not in health_contract
        or "http://127.0.0.1:8000/health" not in health_contract
        or "response.status == 200" not in health_contract
        or "{'status': 'ok'}" not in health_contract
    ):
        raise AssertionError("Built image healthcheck does not match the HTTP contract")

    boundary_script = (
        "import os; from pathlib import Path; "
        "assert (os.getuid(), os.getgid()) == (10001, 10001); "
        "assert Path.cwd() == Path('/data'); "
        "assert not any(Path('/data').iterdir()); "
        "forbidden = ('/build', '/wheels', '/src', '/tests', '/specs', '/.git', "
        "'/.env', '/project_board.sqlite3'); "
        "assert not any(Path(path).exists() for path in forbidden)"
    )
    result = command(
        [
            "docker",
            "run",
            "--name",
            names.boundary_container,
            "--network",
            "none",
            "--entrypoint",
            "python",
            names.image,
            "-c",
            boundary_script,
        ],
        check=False,
    )
    created.boundary_container = True
    if result.returncode != 0:
        detail = (
            result.stderr.strip() or result.stdout.strip() or str(result.returncode)
        )
        raise AssertionError(f"Built image filesystem boundary failed: {detail}")


def _wait_for_healthy(
    command: Command,
    container: str,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    deadline = monotonic() + HEALTH_TIMEOUT_SECONDS
    last_status = "not inspected"
    while monotonic() < deadline:
        inspected = _inspect_container(command, container)
        state = inspected.get("State", {})
        last_status = str(state.get("Health", {}).get("Status", "missing"))
        if state.get("Status") == "running" and last_status == "healthy":
            configured_user = inspected.get("Config", {}).get("User")
            if configured_user != "10001:10001":
                raise AssertionError(
                    f"Container configured user is {configured_user!r}, not 10001:10001"
                )
            uid = command(["docker", "exec", container, "id", "-u"]).stdout.strip()
            gid = command(["docker", "exec", container, "id", "-g"]).stdout.strip()
            if (uid, gid) != ("10001", "10001"):
                raise AssertionError(f"Container runtime identity is {uid}:{gid}")
            return
        if state.get("Status") in {"dead", "exited"}:
            raise AssertionError(
                f"Container {container} stopped before becoming healthy ({last_status})"
            )
        pause(1)
    raise AssertionError(
        f"Container {container} did not become healthy within "
        f"{HEALTH_TIMEOUT_SECONDS}s (last status: {last_status})"
    )


def _localhost_base_url(command: Command, container: str) -> str:
    result = command(["docker", "port", container, CONTAINER_PORT])
    bindings = result.stdout.splitlines()
    if len(bindings) != 1:
        raise AssertionError(f"Expected one published {CONTAINER_PORT} binding")
    match = re.fullmatch(r"127\.0\.0\.1:(\d+)", bindings[0].strip())
    if match is None or not (1 <= int(match.group(1)) <= 65535):
        raise AssertionError(f"Container port is not loopback-only: {bindings[0]!r}")
    return f"http://127.0.0.1:{match.group(1)}"


def _expect_http(
    http: HttpRequest,
    url: str,
    *,
    status: int,
    content_type: str | None = None,
) -> bytes:
    actual_status, headers, body = http(url)
    if actual_status != status:
        raise AssertionError(
            f"GET {url} returned HTTP {actual_status}, expected {status}"
        )
    if not body:
        raise AssertionError(f"GET {url} returned an empty response")
    if content_type is not None and content_type not in headers.get("content-type", ""):
        raise AssertionError(f"GET {url} did not return {content_type}")
    return body


def _verify_http_surface(http: HttpRequest, base_url: str) -> None:
    health = _expect_http(http, f"{base_url}/health", status=200)
    if json.loads(health) != {"status": "ok"}:
        raise AssertionError("Health response was not exactly {'status': 'ok'}")
    html = _expect_http(
        http, f"{base_url}/", status=200, content_type="text/html"
    ).decode("utf-8")
    if "Local Project Board" not in html:
        raise AssertionError("Web UI HTML did not contain its application title")
    css = _expect_http(
        http, f"{base_url}/static/app.css", status=200, content_type="text/css"
    )
    javascript = _expect_http(
        http,
        f"{base_url}/static/app.js",
        status=200,
        content_type="javascript",
    )
    if b":root" not in css or b"/api/projects" not in javascript:
        raise AssertionError("Packaged Web UI assets did not contain expected content")


def _create_project(http: HttpRequest, base_url: str, name: str) -> dict[str, Any]:
    status, _, body = http(
        f"{base_url}/api/projects", method="POST", payload={"name": name}
    )
    if status != 201:
        raise AssertionError(f"Project creation returned HTTP {status}, expected 201")
    project = json.loads(body)
    if not isinstance(project, dict) or project.get("name") != name:
        raise AssertionError("Project creation returned an unexpected representation")
    project_id = project.get("id")
    if not isinstance(project_id, int) or project_id <= 0:
        raise AssertionError("Project creation did not return a positive integer ID")
    _verify_project(http, base_url, project)
    return project


def _verify_project(http: HttpRequest, base_url: str, expected: dict[str, Any]) -> None:
    status, _, body = http(f"{base_url}/api/projects/{expected['id']}")
    if status != 200 or json.loads(body) != expected:
        raise AssertionError(
            "Persisted Project did not match its created representation"
        )


def _assert_safe_logs(logs: str) -> None:
    for rejection in LOG_REJECTIONS:
        if rejection.search(logs):
            raise AssertionError(
                f"Container logs matched rejected pattern {rejection.pattern!r}"
            )


def _start_container(
    command: Command,
    *,
    name: str,
    names: ResourceNames,
) -> None:
    command(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--network",
            names.network,
            "--mount",
            f"type=volume,source={names.volume},target=/data",
            "--publish",
            "127.0.0.1::8000",
            names.image,
        ]
    )


def _remove_container(command: Command, container: str) -> None:
    result = command(["docker", "rm", "--force", container], check=False)
    if result.returncode != 0:
        detail = result.stderr.strip() or str(result.returncode)
        raise AssertionError(f"Could not remove container {container}: {detail}")


def _container_logs(command: Command, container: str) -> str:
    result = command(["docker", "logs", container])
    return f"{result.stdout}\n{result.stderr}"


def _cleanup(command: Command, names: ResourceNames, created: CreatedResources) -> None:
    """Remove only exact resources successfully created by this smoke run."""
    cleanup_actions: list[tuple[bool, list[str]]] = [
        (
            created.second_container,
            ["docker", "rm", "--force", names.second_container],
        ),
        (
            created.first_container,
            ["docker", "rm", "--force", names.first_container],
        ),
        (
            created.boundary_container,
            ["docker", "rm", "--force", names.boundary_container],
        ),
        (created.volume, ["docker", "volume", "rm", names.volume]),
        (created.network, ["docker", "network", "rm", names.network]),
        (
            created.image,
            ["docker", "image", "rm", "--force", names.image],
        ),
    ]
    errors: list[str] = []
    for was_created, arguments in cleanup_actions:
        if not was_created:
            continue
        try:
            result = command(arguments, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append(f"{' '.join(arguments)}: {error}")
        else:
            if result.returncode != 0:
                detail = result.stderr.strip() or str(result.returncode)
                errors.append(f"{' '.join(arguments)}: {detail}")
    if errors:
        raise AssertionError("Container cleanup failed: " + "; ".join(errors))


def run_smoke(
    *,
    command: Command = run_command,
    http: HttpRequest = request_http,
    run_id: str | None = None,
) -> SmokeResult:
    """Build and verify one isolated container lifecycle, then always clean it."""
    names = ResourceNames.unique(run_id)
    created = CreatedResources()
    before = fingerprint_repository(command)
    first_logs = ""

    try:
        command(
            ["docker", "build", "--tag", names.image, "."],
            timeout=BUILD_TIMEOUT_SECONDS,
        )
        created.image = True
        _verify_image_boundary(command, names, created)
        command(["docker", "network", "create", names.network])
        created.network = True
        command(["docker", "volume", "create", names.volume])
        created.volume = True

        _start_container(command, name=names.first_container, names=names)
        created.first_container = True
        _wait_for_healthy(command, names.first_container)
        first_url = _localhost_base_url(command, names.first_container)
        _verify_http_surface(http, first_url)
        project = _create_project(
            http, first_url, f"Container smoke {names.first_container}"
        )
        first_logs = _container_logs(command, names.first_container)
        _remove_container(command, names.first_container)
        created.first_container = False

        _start_container(command, name=names.second_container, names=names)
        created.second_container = True
        _wait_for_healthy(command, names.second_container)
        second_url = _localhost_base_url(command, names.second_container)
        _verify_http_surface(http, second_url)
        _verify_project(http, second_url, project)
        second_logs = _container_logs(command, names.second_container)
        _assert_safe_logs(f"{first_logs}\n{second_logs}")

        after = fingerprint_repository(command)
        if after != before:
            raise AssertionError(
                "Container smoke changed Git state or repository-local SQLite data"
            )
        result = SmokeResult(
            resources=names,
            repository_before=before,
            repository_after=after,
            first_url=first_url,
            second_url=second_url,
            project_id=project["id"],
            project_name=project["name"],
        )
    finally:
        _cleanup(command, names, created)
    return result


def main() -> int:
    try:
        run_smoke()
    except (AssertionError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"container smoke failed: {error}", file=sys.stderr)
        return 1
    print("container smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
