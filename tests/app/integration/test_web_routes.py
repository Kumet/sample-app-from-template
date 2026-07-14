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


def test_openapi_operations_match_the_pre_web_ui_contract() -> None:
    schema = _client().get("/openapi.json").json()
    operations = {
        path: {
            method: operation["operationId"] for method, operation in path_item.items()
        }
        for path, path_item in schema["paths"].items()
    }

    assert operations == {
        "/health": {"get": "health_health_get"},
        "/api/projects": {
            "get": "list_projects_api_projects_get",
            "post": "create_project_api_projects_post",
        },
        "/api/projects/{project_id}": {
            "delete": "delete_project_api_projects__project_id__delete",
            "get": "get_project_api_projects__project_id__get",
            "patch": "update_project_api_projects__project_id__patch",
        },
        "/api/projects/{project_id}/dashboard": {
            "get": "get_project_dashboard_api_projects__project_id__dashboard_get"
        },
        "/api/projects/{project_id}/tasks": {
            "get": "list_tasks_api_projects__project_id__tasks_get",
            "post": "create_task_api_projects__project_id__tasks_post",
        },
        "/api/projects/{project_id}/tasks/{task_id}": {
            "delete": "delete_task_api_projects__project_id__tasks__task_id__delete",
            "get": "get_task_api_projects__project_id__tasks__task_id__get",
            "patch": "update_task_api_projects__project_id__tasks__task_id__patch",
        },
        "/api/projects/{project_id}/tags": {
            "get": "list_tags_api_projects__project_id__tags_get",
            "post": "create_tag_api_projects__project_id__tags_post",
        },
        "/api/projects/{project_id}/tags/{tag_id}": {
            "delete": "delete_tag_api_projects__project_id__tags__tag_id__delete",
            "get": "get_tag_api_projects__project_id__tags__tag_id__get",
            "patch": "update_tag_api_projects__project_id__tags__tag_id__patch",
        },
        "/api/projects/{project_id}/tasks/{task_id}/tags/{tag_id}": {
            "delete": (
                "detach_tag_api_projects__project_id__tasks__task_id__tags__tag_id__delete"
            ),
            "put": (
                "attach_tag_api_projects__project_id__tasks__task_id__tags__tag_id__put"
            ),
        },
        "/api/projects/{project_id}/tasks/{task_id}/comments": {
            "get": (
                "list_comments_api_projects__project_id__tasks__task_id__comments_get"
            ),
            "post": (
                "create_comment_api_projects__project_id__tasks__task_id__comments_post"
            ),
        },
        "/api/projects/{project_id}/tasks/{task_id}/comments/{comment_id}": {
            "delete": (
                "delete_comment_api_projects__project_id__tasks__task_id__comments__comment_id__delete"
            ),
            "get": (
                "get_comment_api_projects__project_id__tasks__task_id__comments__comment_id__get"
            ),
            "patch": (
                "update_comment_api_projects__project_id__tasks__task_id__comments__comment_id__patch"
            ),
        },
        "/api/projects/{project_id}/tasks/{task_id}/activities": {
            "get": (
                "list_activities_api_projects__project_id__tasks__task_id__activities_get"
            )
        },
    }
