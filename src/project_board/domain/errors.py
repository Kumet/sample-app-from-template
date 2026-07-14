"""Stable domain errors shared with application callers."""


class ProjectValidationError(ValueError):
    """Raised when Project data violates a domain rule."""


class ProjectNotFound(LookupError):
    """Raised when an integer Project ID does not exist."""

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} was not found")


class TaskValidationError(ValueError):
    """Raised when Task data violates a domain rule."""


class TaskNotFound(LookupError):
    """Raised when a Task is absent from the requested Project."""

    def __init__(self, project_id: int, task_id: int) -> None:
        self.project_id = project_id
        self.task_id = task_id
        super().__init__(f"Task {task_id} was not found in Project {project_id}")


class TagValidationError(ValueError):
    """Raised when Tag data violates a domain rule."""


class TagNotFound(LookupError):
    """Raised when a Tag is absent from the requested Project."""

    def __init__(self, project_id: int, tag_id: int) -> None:
        self.project_id = project_id
        self.tag_id = tag_id
        super().__init__(f"Tag {tag_id} was not found in Project {project_id}")


class DuplicateTagName(RuntimeError):
    """Raised when a Project already owns a Tag with the same normalized name."""

    def __init__(self, project_id: int, name: str) -> None:
        self.project_id = project_id
        self.name = name
        super().__init__(f"Tag name {name!r} already exists in Project {project_id}")


class ProjectHasTasksConflict(RuntimeError):
    """Raised when deletion is blocked because a Project owns Tasks."""

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} still has Tasks")


class RepositoryError(RuntimeError):
    """Stable error for unexpected repository failures."""
