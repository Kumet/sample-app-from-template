"""Fixed routes for the packaged browser application assets."""

from importlib.resources import files
from typing import Final

from fastapi import APIRouter, Response

WEB_SECURITY_HEADERS: Final = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self'; "
        "img-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

router = APIRouter(include_in_schema=False)


def _packaged_asset(name: str, media_type: str) -> Response:
    content = files("project_board.web").joinpath(name).read_bytes()
    return Response(
        content=content,
        media_type=media_type,
        headers=WEB_SECURITY_HEADERS,
    )


@router.get("/")
def web_index() -> Response:
    """Return the packaged application document."""
    return _packaged_asset("index.html", "text/html")


@router.get("/static/app.css")
def web_stylesheet() -> Response:
    """Return the fixed packaged stylesheet."""
    return _packaged_asset("app.css", "text/css")


@router.get("/static/app.js")
def web_script() -> Response:
    """Return the fixed packaged browser script."""
    return _packaged_asset("app.js", "text/javascript")
