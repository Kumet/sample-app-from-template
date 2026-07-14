from project_board.api.web_routes import web_script


def _script() -> str:
    return web_script().body.decode()


def test_project_navigation_maps_existing_crud_routes_and_payloads() -> None:
    script = _script()

    assert 'requestLatest("projects", "/api/projects")' in script
    assert 'apiRequest("/api/projects", {' in script
    assert 'method: "POST"' in script
    assert 'method: "PATCH"' in script
    assert 'method: "DELETE"' in script
    assert 'name: String(data.get("name") ?? "")' in script
    assert 'description: String(data.get("description") ?? "")' in script
    assert 'dialog.dataset.action = "delete-project"' in script
    assert 'dialog.returnValue === "confirm"' in script


def test_project_selection_resets_all_dependent_cross_project_state() -> None:
    script = _script()

    reset_start = script.index("function resetProjectDependents()")
    reset_end = script.index("function renderProjectList()")
    reset = script[reset_start:reset_end]

    for state_expression in (
        "state.dashboard = null",
        "state.tasks.items = []",
        "state.tasks.query.offset = 0",
        "state.selectedTaskId = null",
        "state.taskDetail = null",
        "state.tags = []",
        "state.comments.items = []",
        "state.activities.items = []",
    ):
        assert state_expression in reset
    assert "active.controller.abort()" in script
    assert "resetProjectDependents();" in script


def test_dashboard_renders_every_existing_response_group_as_text() -> None:
    script = _script()

    for response_field in (
        "dashboard.as_of",
        "dashboard.tasks.total",
        "dashboard.tasks.by_status.todo",
        "dashboard.tasks.by_status.in_progress",
        "dashboard.tasks.by_status.done",
        "dashboard.tasks.by_priority.low",
        "dashboard.tasks.by_priority.medium",
        "dashboard.tasks.by_priority.high",
        "dashboard.due.active_total",
        "dashboard.due.overdue",
        "dashboard.due.due_today",
        "dashboard.due.upcoming_7_days",
        "dashboard.due.later",
        "dashboard.due.no_due_date",
        "dashboard.comments.total",
        "dashboard.comments.tasks_with_comments",
        "dashboard.tags",
        "dashboard.recent_activities",
        "activity.event_type",
        "activity.task_id",
        "activity.comment_id",
        "activity.occurred_at",
    ):
        assert response_field in script

    assert 'projectApiPath(projectId, "/dashboard")' in script
    assert "await loadDashboard();" in script
    assert "textContent" in script
    assert "replaceChildren" in script


def test_project_and_dashboard_have_explicit_loading_empty_and_error_states() -> None:
    script = _script()

    assert 'setExplicitState("projects", state.projects.length)' in script
    assert 'setExplicitState("dashboard", state.dashboard === null ? 0 : 1)' in script
    assert 'list.setAttribute("aria-busy", String(state.loading.projects))' in script
    assert (
        'content.setAttribute("aria-busy", String(state.loading.dashboard))' in script
    )
    assert "showError(error)" in script
