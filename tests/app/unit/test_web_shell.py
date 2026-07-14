from html.parser import HTMLParser

from project_board.api.web_routes import web_index


class ShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs)))


def _shell() -> tuple[str, ShellParser]:
    document = web_index().body.decode()
    parser = ShellParser()
    parser.feed(document)
    return document, parser


def test_shell_has_semantic_landmarks_and_ordered_headings() -> None:
    _, parser = _shell()
    tags = [tag for tag, _ in parser.elements]
    headings = [tag for tag in tags if tag in {"h1", "h2", "h3"}]
    levels = [int(tag[1]) for tag in headings]

    assert tags.count("header") == 1
    assert tags.count("main") == 1
    assert tags.count("nav") >= 1
    assert headings[0] == "h1"
    assert headings.count("h1") == 1
    assert all(
        current <= previous + 1
        for previous, current in zip(levels, levels[1:], strict=False)
    )


def test_shell_id_references_are_unique_and_resolve() -> None:
    _, parser = _shell()
    element_ids = [
        attrs["id"] for _, attrs in parser.elements if attrs.get("id") is not None
    ]
    references = {
        reference
        for _, attrs in parser.elements
        for name in ("aria-controls", "aria-describedby", "aria-labelledby")
        for reference in (attrs.get(name) or "").split()
    }

    assert len(element_ids) == len(set(element_ids))
    assert references <= set(element_ids)


def test_shell_labels_controls_and_names_buttons() -> None:
    _, parser = _shell()
    elements = parser.elements
    ids = {attrs["id"] for _, attrs in elements if attrs.get("id") is not None}
    label_targets = {
        attrs["for"]
        for tag, attrs in elements
        if tag == "label" and attrs.get("for") is not None
    }
    labelled_controls = {
        attrs["id"]
        for tag, attrs in elements
        if tag in {"input", "select", "textarea"} and attrs.get("id") is not None
    }

    assert labelled_controls <= label_targets
    assert label_targets <= ids
    assert all(
        attrs.get("type") is not None for tag, attrs in elements if tag == "button"
    )


def test_shell_exposes_live_and_explicit_application_states() -> None:
    _, parser = _shell()
    by_id = {
        attrs["id"]: attrs
        for _, attrs in parser.elements
        if attrs.get("id") is not None
    }

    assert by_id["global-status"]["role"] == "status"
    assert by_id["global-status"]["aria-live"] == "polite"
    assert by_id["global-error"]["role"] == "alert"
    for resource in ("projects", "dashboard", "tasks", "tags", "comments", "activity"):
        assert f"{resource}-loading" in by_id
        assert f"{resource}-empty" in by_id
        assert f"{resource}-error" in by_id


def test_shell_has_accessible_destructive_confirmation() -> None:
    _, parser = _shell()
    by_id = {
        attrs["id"]: (tag, attrs)
        for tag, attrs in parser.elements
        if attrs.get("id") is not None
    }
    tag, dialog = by_id["destructive-confirmation-dialog"]

    assert tag == "dialog"
    assert dialog["aria-labelledby"] == "confirmation-heading"
    assert dialog["aria-describedby"] == "confirmation-message"
    assert "confirm-delete-button" in by_id


def test_shell_contains_no_inline_or_unsafe_browser_code() -> None:
    document, parser = _shell()

    assert "<style" not in document
    assert "javascript:" not in document.lower()
    assert all(
        name != "style" and not name.startswith("on")
        for _, attrs in parser.elements
        for name in attrs
    )
    assert all(
        not (value or "").startswith(("http://", "https://", "//"))
        for _, attrs in parser.elements
        for name, value in attrs.items()
        if name in {"action", "href", "src"}
    )
