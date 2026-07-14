"""FastAPI routes and sanitized error mapping for Project and Task CRUD."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Response, status

from project_board.api.dependencies import (
    ProjectServiceDependency,
    TaskServiceDependency,
)
from project_board.api.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from project_board.application import UNSET
from project_board.domain import (
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskValidationError,
)
from project_board.repositories import SortOrder, TaskListQuery, TaskSort

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _call_service(operation: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return operation(*args, **kwargs)
    except ProjectNotFound as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="Task not found") from error
    except ProjectHasTasksConflict as error:
        raise HTTPException(status_code=409, detail="Project has tasks") from error
    except (ProjectValidationError, TaskValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=500, detail="An unexpected persistence error occurred"
        ) from error


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: Annotated[ProjectCreate, Body()], service: ProjectServiceDependency
) -> object:
    return _call_service(service.create_project, payload.name, payload.description)


@router.get("", response_model=list[ProjectResponse])
def list_projects(service: ProjectServiceDependency) -> object:
    return _call_service(service.list_projects)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, service: ProjectServiceDependency) -> object:
    return _call_service(service.get_project, project_id)


@router.post(
    "/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    project_id: int,
    payload: Annotated[TaskCreate, Body()],
    service: TaskServiceDependency,
) -> object:
    return _call_service(
        service.create_task,
        project_id,
        payload.title,
        payload.description,
        payload.status,
        payload.priority,
        payload.due_at,
    )


@router.get("/{project_id}/tasks", response_model=list[TaskResponse])
def list_tasks(
    project_id: int,
    service: TaskServiceDependency,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: TaskSort = TaskSort.CREATED_AT,
    order: SortOrder = SortOrder.ASC,
) -> object:
    return _call_service(
        lambda: service.list_tasks(
            project_id,
            TaskListQuery(
                status=status_filter,
                priority=priority,
                due_before=due_before,
                due_after=due_after,
                limit=limit,
                offset=offset,
                sort=sort,
                order=order,
            ),
        )
    )


@router.get("/{project_id}/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    project_id: int,
    task_id: int,
    service: TaskServiceDependency,
) -> object:
    return _call_service(service.get_task, project_id, task_id)


@router.patch(
    "/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
)
def update_task(
    project_id: int,
    task_id: int,
    payload: Annotated[TaskUpdate, Body()],
    service: TaskServiceDependency,
) -> object:
    updates = {
        field_name: getattr(payload, field_name)
        for field_name in payload.model_fields_set
    }
    return _call_service(
        service.update_task,
        project_id,
        task_id,
        **updates,
    )


@router.delete(
    "/{project_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_task(
    project_id: int,
    task_id: int,
    service: TaskServiceDependency,
) -> Response:
    _call_service(service.delete_task, project_id, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    payload: Annotated[ProjectUpdate, Body()],
    service: ProjectServiceDependency,
) -> object:
    name = payload.name if "name" in payload.model_fields_set else UNSET
    description = (
        payload.description if "description" in payload.model_fields_set else UNSET
    )
    return _call_service(
        service.update_project,
        project_id,
        name=name,
        description=description,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, service: ProjectServiceDependency) -> Response:
    _call_service(service.delete_project, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
