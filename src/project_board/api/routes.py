"""FastAPI routes and sanitized error mapping for application operations."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Response, status

from project_board.api.dependencies import (
    ProjectServiceDependency,
    TagServiceDependency,
    TaskCommentServiceDependency,
    TaskServiceDependency,
)
from project_board.api.schemas import (
    AwareUtcDatetime,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    TagCreate,
    TagResponse,
    TagUpdate,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from project_board.application import UNSET
from project_board.domain import (
    DuplicateTagName,
    ProjectHasTasksConflict,
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
    TagNotFound,
    TagValidationError,
    TaskCommentNotFound,
    TaskCommentValidationError,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
    TaskValidationError,
)
from project_board.repositories import (
    CommentListQuery,
    SortOrder,
    TaskListQuery,
    TaskSort,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _call_service(operation: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return operation(*args, **kwargs)
    except ProjectNotFound as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except TaskNotFound as error:
        raise HTTPException(status_code=404, detail="Task not found") from error
    except TaskCommentNotFound as error:
        raise HTTPException(status_code=404, detail="Comment not found") from error
    except TagNotFound as error:
        raise HTTPException(status_code=404, detail="Tag not found") from error
    except ProjectHasTasksConflict as error:
        raise HTTPException(status_code=409, detail="Project has tasks") from error
    except DuplicateTagName as error:
        raise HTTPException(
            status_code=409, detail="Tag name already exists"
        ) from error
    except (
        ProjectValidationError,
        TagValidationError,
        TaskCommentValidationError,
        TaskValidationError,
    ) as error:
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
    "/{project_id}/tags",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    project_id: int,
    payload: Annotated[TagCreate, Body()],
    service: TagServiceDependency,
) -> object:
    return _call_service(
        service.create_tag,
        project_id,
        payload.name,
        payload.color,
    )


@router.get("/{project_id}/tags", response_model=list[TagResponse])
def list_tags(project_id: int, service: TagServiceDependency) -> object:
    return _call_service(service.list_tags, project_id)


@router.get("/{project_id}/tags/{tag_id}", response_model=TagResponse)
def get_tag(
    project_id: int,
    tag_id: int,
    service: TagServiceDependency,
) -> object:
    return _call_service(service.get_tag, project_id, tag_id)


@router.patch("/{project_id}/tags/{tag_id}", response_model=TagResponse)
def update_tag(
    project_id: int,
    tag_id: int,
    payload: Annotated[TagUpdate, Body()],
    service: TagServiceDependency,
) -> object:
    updates = {
        field_name: getattr(payload, field_name)
        for field_name in payload.model_fields_set
    }
    return _call_service(service.update_tag, project_id, tag_id, **updates)


@router.delete(
    "/{project_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_tag(
    project_id: int,
    tag_id: int,
    service: TagServiceDependency,
) -> Response:
    _call_service(service.delete_tag, project_id, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{project_id}/tasks/{task_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def attach_tag(
    project_id: int,
    task_id: int,
    tag_id: int,
    service: TagServiceDependency,
) -> Response:
    _call_service(service.attach_tag, project_id, task_id, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{project_id}/tasks/{task_id}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_tag(
    project_id: int,
    task_id: int,
    tag_id: int,
    service: TagServiceDependency,
) -> Response:
    _call_service(service.detach_tag, project_id, task_id, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    q: Annotated[str | None, Query()] = None,
    status_filter: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    priority: Annotated[list[TaskPriority] | None, Query()] = None,
    due_before: Annotated[AwareUtcDatetime | None, Query()] = None,
    due_after: Annotated[AwareUtcDatetime | None, Query()] = None,
    tag_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: TaskSort = TaskSort.CREATED_AT,
    order: SortOrder = SortOrder.ASC,
) -> object:
    statuses = tuple(status_filter or ())
    priorities = tuple(priority or ())
    return _call_service(
        lambda: service.list_tasks(
            project_id,
            TaskListQuery(
                q=q,
                statuses=statuses,
                priorities=priorities,
                status=statuses[0] if len(statuses) == 1 else None,
                priority=priorities[0] if len(priorities) == 1 else None,
                due_before=due_before,
                due_after=due_after,
                tag_id=tag_id,
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


@router.post(
    "/{project_id}/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    project_id: int,
    task_id: int,
    payload: Annotated[CommentCreate, Body()],
    service: TaskCommentServiceDependency,
) -> object:
    return _call_service(service.create_comment, project_id, task_id, payload.body)


@router.get(
    "/{project_id}/tasks/{task_id}/comments",
    response_model=list[CommentResponse],
)
def list_comments(
    project_id: int,
    task_id: int,
    service: TaskCommentServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: SortOrder = SortOrder.ASC,
) -> object:
    return _call_service(
        service.list_comments,
        project_id,
        task_id,
        CommentListQuery(limit=limit, offset=offset, order=order),
    )


@router.get(
    "/{project_id}/tasks/{task_id}/comments/{comment_id}",
    response_model=CommentResponse,
)
def get_comment(
    project_id: int,
    task_id: int,
    comment_id: int,
    service: TaskCommentServiceDependency,
) -> object:
    return _call_service(service.get_comment, project_id, task_id, comment_id)


@router.patch(
    "/{project_id}/tasks/{task_id}/comments/{comment_id}",
    response_model=CommentResponse,
)
def update_comment(
    project_id: int,
    task_id: int,
    comment_id: int,
    payload: Annotated[CommentUpdate, Body()],
    service: TaskCommentServiceDependency,
) -> object:
    return _call_service(
        service.update_comment,
        project_id,
        task_id,
        comment_id,
        body=payload.body,
    )


@router.delete(
    "/{project_id}/tasks/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_comment(
    project_id: int,
    task_id: int,
    comment_id: int,
    service: TaskCommentServiceDependency,
) -> Response:
    _call_service(service.delete_comment, project_id, task_id, comment_id)
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
