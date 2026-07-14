from project_board.api.web_routes import web_script


def _script() -> str:
    return web_script().body.decode()


def test_client_owns_all_shared_application_state() -> None:
    script = _script()

    for state_name in (
        "projects",
        "selectedProjectId",
        "dashboard",
        "tasks",
        "selectedTaskId",
        "taskDetail",
        "tags",
        "comments",
        "activities",
        "loading",
        "errors",
        "activeRequests",
        "requestSequence",
        "mutationLocks",
    ):
        assert state_name in script


def test_client_handles_safe_response_and_failure_cases() -> None:
    script = _script()

    assert "response.status === 204" in script
    assert "JSON.parse(body)" in script
    assert "if (!response.ok)" in script
    assert 'response.status === 422 ? "validation"' in script
    assert 'kind: "network"' in script
    assert 'kind: "malformed"' in script
    assert "omitUndefined(options.json)" in script
    assert 'credentials: "same-origin"' in script


def test_client_controls_stale_requests_and_duplicate_mutations() -> None:
    script = _script()

    assert "new AbortController()" in script
    assert "previous.controller.abort()" in script
    assert "isCurrentRequest(handle)" in script
    assert "accepted: false" in script
    assert "DuplicateMutationError" in script
    assert "state.mutationLocks[key] = true" in script
    assert "delete state.mutationLocks[key]" in script


def test_client_uses_safe_dom_construction_contract() -> None:
    script = _script()
    forbidden_tokens = (
        "inner" + "HTML",
        "outer" + "HTML",
        "insertAdjacent" + "HTML",
        "document.write",
        "eval(",
        "new Function",
        'setTimeout("',
        'setInterval("',
    )

    assert "textContent" in script
    assert all(token not in script for token in forbidden_tokens)
