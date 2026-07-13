"""Errors shared by the Project domain and its callers."""


class ProjectValidationError(ValueError):
    """Raised when Project data violates a domain rule."""


class ProjectNotFound(LookupError):
    """Raised when an integer Project ID does not exist."""

    def __init__(self, project_id: int) -> None:
        self.project_id = project_id
        super().__init__(f"Project {project_id} was not found")


class RepositoryError(RuntimeError):
    """Stable error for unexpected repository failures."""
