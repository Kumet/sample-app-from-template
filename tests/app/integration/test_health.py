from fastapi.testclient import TestClient

from project_board.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"].startswith("application/json")


def test_unknown_endpoint_returns_not_found() -> None:
    response = client.get("/not-defined")

    assert response.status_code == 404
