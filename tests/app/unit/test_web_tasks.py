from project_board.api.web_routes import web_index, web_script


def _script() -> str:
    return web_script().body.decode()


def test_task_query_uses_only_existing_parameters_and_defaults() -> None:
    script = _script()
    query_start = script.index("function taskQueryParameters()")
    query_end = script.index("function taskListPath(")
    query = script[query_start:query_end]

    for parameter in (
        'parameters.set("q"',
        'parameters.append("status"',
        'parameters.append("priority"',
        'parameters.set("tag_id"',
        'parameters.set("due_after"',
        'parameters.set("due_before"',
        'parameters.set("sort"',
        'parameters.set("order"',
        'parameters.set("limit"',
        'parameters.set("offset"',
    ):
        assert parameter in query

    assert "new URLSearchParams()" in query
    assert 'sort: "created_at"' in script
    assert 'order: "asc"' in script
    assert "limit: 50" in script
    assert "offset: 0" in script
    assert "state.tasks.query.offset = 0" in script


def test_task_lists_cancel_and_reject_stale_responses() -> None:
    script = _script()
    load_start = script.index("async function loadTasks()")
    load_end = script.index("async function loadTaskDetail(")
    load_tasks = script[load_start:load_end]

    assert 'requestLatest("tasks", taskListPath(projectId))' in load_tasks
    assert "!result.accepted" in load_tasks
    assert "state.selectedProjectId !== projectId" in load_tasks
    assert "previous.controller.abort()" in script


def test_task_crud_maps_owned_routes_and_mutable_payload_only() -> None:
    script = _script()
    payload_start = script.index("function taskPayload(")
    payload_end = script.index("function taskQueryFromForm(")
    payload = script[payload_start:payload_end]

    for field in ("title", "description", "status", "priority", "due_at"):
        assert f"{field}:" in payload
    for forbidden in ("id:", "project_id:", "created_at:", "updated_at:", "tags:"):
        assert forbidden not in payload

    assert 'method: "POST"' in script
    assert 'method: "PATCH"' in script
    assert 'method: "DELETE"' in script
    assert 'description === "" ? null : description' in script
    assert 'value === "" ? null' in script
    assert 'dialog.dataset.action = "delete-task"' in script
    assert "runMutation(`updateTask:${taskId}`" in script
    assert "runMutation(`deleteTask:${taskId}`" in script


def test_task_mutations_refresh_only_after_success() -> None:
    script = _script()

    assert "await Promise.all([loadTasks(), loadDashboard()]);" in script
    assert (
        "await Promise.all([loadTasks(), loadDashboard(), loadTaskDetail(taskId)]);"
        in script
    )
    assert "submit.disabled = true" in script
    assert "submit.disabled = false" in script


def test_task_shell_uses_the_existing_in_progress_enum_value() -> None:
    document = web_index().body.decode()

    assert 'value="in_progress"' in document
    assert 'value="doing"' not in document
