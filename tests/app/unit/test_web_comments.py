from project_board.api.web_routes import web_script


def _script() -> str:
    return web_script().body.decode()


def test_comment_crud_uses_owned_routes_and_body_only_payload() -> None:
    script = _script()
    payload_start = script.index("function commentPayload(")
    payload_end = script.index("async function createComment(")
    payload = script[payload_start:payload_end]

    assert "`${taskApiPath(projectId, taskId)}/${resource}${childSuffix}`" in script
    assert 'resource !== "comments" && resource !== "activities"' in script
    assert 'method: "POST"' in script
    assert 'method: "PATCH"' in script
    assert 'method: "DELETE"' in script
    assert "body:" in payload
    for forbidden in ("id:", "project_id:", "task_id:", "created_at:", "updated_at:"):
        assert forbidden not in payload
    assert 'dialog.dataset.action = "delete-comment"' in script
    assert "runMutation(`createComment:${taskId}`" in script
    assert "runMutation(`updateComment:${taskId}:${commentId}`" in script
    assert "runMutation(`deleteComment:${taskId}:${commentId}`" in script


def test_comment_and_activity_lists_preserve_order_and_pagination() -> None:
    script = _script()

    assert 'order: "asc"' in script
    assert 'parameters.set("limit", String(collection.limit))' in script
    assert 'parameters.set("offset", String(collection.offset))' in script
    assert 'parameters.set("order", collection.order)' in script
    assert 'taskChildListPath(projectId, taskId, "comments", state.comments)' in script
    assert (
        'taskChildListPath(projectId, taskId, "activities", state.activities)' in script
    )
    assert "state.comments.offset += state.comments.limit" in script
    assert "state.activities.offset += state.activities.limit" in script
    assert 'requestLatest(\n    "comments"' in script
    assert 'requestLatest(\n    "activities"' in script


def test_task_selection_resets_and_scopes_comment_activity_requests() -> None:
    script = _script()
    reset_start = script.index("function resetTaskResources()")
    reset_end = script.index("function localDateTimeValue(")
    reset = script[reset_start:reset_end]

    for expression in (
        'cancelResourceRequest("comments")',
        'cancelResourceRequest("activities")',
        "state.comments.items = []",
        "state.comments.offset = 0",
        "state.activities.items = []",
        "state.activities.offset = 0",
    ):
        assert expression in reset
    assert "state.selectedProjectId !== projectId" in script
    assert "state.selectedTaskId !== taskId" in script
    assert "resetTaskResources();\n  state.selectedTaskId = taskId" in script
    assert "loadComments();\n  loadActivities();" in script


def test_comment_mutations_refresh_server_authoritative_related_state() -> None:
    script = _script()

    assert (
        script.count(
            "await Promise.all([loadComments(), loadActivities(), loadDashboard()]);"
        )
        == 3
    )
    assert "submit.disabled = true" in script
    assert "submit.disabled = false" in script
    assert "state.comments.items.length === 1 && state.comments.offset > 0" in script


def test_comment_body_is_literal_multiline_text_and_activity_is_payload_free() -> None:
    script = _script()
    comments_start = script.index("function renderComments()")
    comments_end = script.index("function renderActivities()")
    comments = script[comments_start:comments_end]
    activities_start = comments_end
    activities_end = script.index("async function loadComments()")
    activities = script[activities_start:activities_end]

    assert 'element("pre", comment.body)' in comments
    assert "editor.value = comment.body" in comments
    assert "textContent" in script
    assert "activity.event_type" in activities
    assert "activity.comment_id" in activities
    assert "activity.occurred_at" in activities
    assert "activity.body" not in activities
    for forbidden in (
        "inner" + "HTML",
        "outer" + "HTML",
        "insertAdjacent" + "HTML",
        "document.write",
    ):
        assert forbidden not in script
