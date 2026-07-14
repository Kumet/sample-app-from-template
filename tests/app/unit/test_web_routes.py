from project_board.api.web_routes import (
    WEB_SECURITY_HEADERS,
    web_index,
    web_script,
    web_stylesheet,
)


def test_fixed_web_handlers_read_packaged_assets() -> None:
    index = web_index()
    stylesheet = web_stylesheet()
    script = web_script()

    assert b'href="/static/app.css"' in index.body
    assert b'src="/static/app.js"' in index.body
    assert stylesheet.body
    assert script.body.startswith(b'"use strict";\n')

    assert index.media_type == "text/html"
    assert stylesheet.media_type == "text/css"
    assert script.media_type == "text/javascript"


def test_fixed_web_handlers_apply_security_headers() -> None:
    for response in (web_index(), web_stylesheet(), web_script()):
        for name, value in WEB_SECURITY_HEADERS.items():
            assert response.headers[name] == value

    policy = WEB_SECURITY_HEADERS["Content-Security-Policy"]
    assert "'unsafe-inline'" not in policy
    assert "'unsafe-eval'" not in policy
