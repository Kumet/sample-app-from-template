from project_board.api.web_routes import web_index, web_script


def _script() -> str:
    return web_script().body.decode()


def test_tag_crud_maps_owned_routes_and_mutable_payload_only() -> None:
    script = _script()
    payload_start = script.index("function tagPayload(")
    payload_end = script.index("function tagOption(")
    payload = script[payload_start:payload_end]

    assert 'const suffix = tagId === null ? "/tags" : `/tags/${tagId}`' in script
    assert 'requestLatest("tags", tagApiPath(projectId))' in script
    assert 'method: "POST"' in script
    assert 'method: "PATCH"' in script
    assert 'method: "DELETE"' in script
    assert "name:" in payload
    assert "color:" in payload
    for forbidden in ("id:", "project_id:", "normalized_name:", "created_at:"):
        assert forbidden not in payload
    assert 'color === "" ? null : color' in payload
    assert 'dialog.dataset.action = "delete-tag"' in script


def test_task_tag_attach_and_detach_use_existing_owned_route() -> None:
    script = _script()

    assert "`${taskApiPath(projectId, taskId)}/tags/${tagId}`" in script
    assert 'method: "PUT"' in script
    assert "runMutation(`attachTag:${taskId}:${tagId}`" in script
    assert "runMutation(`detachTag:${taskId}:${tagId}`" in script
    assert "!state.tags.some((tag) => tag.id === tagId)" in script
    assert "!state.taskDetail?.tags.some((tag) => tag.id === tagId)" in script


def test_tag_mutations_refresh_embedded_server_authoritative_state() -> None:
    script = _script()

    assert "await Promise.all([loadTags(), loadDashboard()]);" in script
    assert "loadTags(),\n      loadTasks(),\n      loadDashboard()," in script
    assert (
        "await Promise.all([loadTasks(), loadDashboard(), loadTaskDetail(taskId)]);"
        in script
    )
    assert "state.tasks.query.tagId = null" in script
    assert "state.tasks.query.offset = 0" in script


def test_tags_render_as_text_without_user_authored_style_values() -> None:
    script = _script()

    assert 'tag.color === null ? "No color" : tag.color' in script
    assert "displayedColor" in script
    assert ".style" not in script
    assert 'setAttribute("style"' not in script
    assert "textContent" in script


def test_tag_shell_exposes_labelled_crud_and_attachment_controls() -> None:
    document = web_index().body.decode()

    for control_id in (
        'id="tag-create-form"',
        'id="tag-create-name"',
        'id="tag-create-color"',
        'id="tag-list"',
        'id="task-tag-list"',
        'id="task-tag-attach-form"',
        'id="task-tag-select"',
    ):
        assert control_id in document
