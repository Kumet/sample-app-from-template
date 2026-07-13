"""FastAPI routes and sanitized error mapping for Project CRUD."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Response, status

from project_board.api.dependencies import ProjectServiceDependency
from project_board.api.schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from project_board.application import UNSET
from project_board.domain import (
    ProjectNotFound,
    ProjectValidationError,
    RepositoryError,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _call_service(operation: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return operation(*args, **kwargs)
    except ProjectNotFound as error:
        raise HTTPException(status_code=404, detail="Project not found") from error
    except ProjectValidationError as error:
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
