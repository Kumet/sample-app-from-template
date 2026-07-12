from fastapi import FastAPI

from project_board.main import app, health


def test_app_is_configured() -> None:
    assert isinstance(app, FastAPI)
    assert app.title == "Local Project Board"


def test_health_handler_returns_ok() -> None:
    assert health() == {"status": "ok"}
