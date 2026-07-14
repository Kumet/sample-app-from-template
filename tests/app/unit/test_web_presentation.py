from project_board.api.web_routes import web_stylesheet


def _stylesheet() -> str:
    return web_stylesheet().body.decode()


def test_stylesheet_supports_keyboard_focus_and_explicit_states() -> None:
    stylesheet = _stylesheet()

    assert ":focus-visible" in stylesheet
    assert 'a[href="#main-content"]:focus' in stylesheet
    assert '[id$="-loading"]' in stylesheet
    assert '[id$="-empty"]' in stylesheet
    assert '[id$="-error"]' in stylesheet
    assert '[aria-busy="true"]' in stylesheet
    assert "[hidden]" in stylesheet


def test_stylesheet_wraps_layout_and_content_at_tablet_and_mobile_sizes() -> None:
    stylesheet = _stylesheet()

    assert "grid-template-columns: minmax(13rem, 18rem) minmax(0, 1fr)" in stylesheet
    assert "flex-wrap: wrap" in stylesheet
    assert "overflow-wrap: anywhere" in stylesheet
    assert "@media (max-width: 56rem)" in stylesheet
    assert "@media (max-width: 32rem)" in stylesheet
    assert "grid-template-columns: minmax(0, 1fr)" in stylesheet


def test_stylesheet_honors_reduced_motion_preference() -> None:
    stylesheet = _stylesheet()

    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "transition-duration: 0.01ms !important" in stylesheet
    assert "animation-duration: 0.01ms !important" in stylesheet
