from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from project_board.api.web_routes import WEB_SECURITY_HEADERS
from project_board.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(database_url="sqlite://"))


def test_web_routes_serve_only_fixed_assets_with_expected_media_types() -> None:
    client = _client()

    index = client.get("/")
    stylesheet = client.get("/static/app.css")
    script = client.get("/static/app.js")

    assert index.status_code == 200
    assert index.headers["content-type"].startswith("text/html")
    assert 'href="/static/app.css"' in index.text
    assert 'src="/static/app.js"' in index.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")

    for path in (
        "/static/missing.css",
        "/static/nested/app.css",
        "/static/%2e%2e/app.css",
        "/app.css",
    ):
        assert client.get(path).status_code == 404


def test_web_assets_are_resolved_independently_of_current_directory(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _client().get("/").status_code == 200
    assert _client().get("/static/app.css").status_code == 200


def test_security_headers_are_limited_to_html_and_static_responses() -> None:
    client = _client()

    for path in ("/", "/static/app.css", "/static/app.js"):
        response = client.get(path)
        for name, value in WEB_SECURITY_HEADERS.items():
            assert response.headers[name] == value

    for path in ("/health", "/openapi.json", "/api/not-defined"):
        response = client.get(path)
        for name in WEB_SECURITY_HEADERS:
            assert name not in response.headers


def test_existing_framework_and_api_routes_remain_intact() -> None:
    client = _client()

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/" not in openapi.json()["paths"]
    assert "/static/app.css" not in openapi.json()["paths"]
    assert client.get("/api/not-defined").status_code == 404
