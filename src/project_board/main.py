"""FastAPI composition root for Local Project Board."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from project_board.api import router as project_router
from project_board.infrastructure import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
    initialize_schema,
)

DEFAULT_DATABASE_URL = "sqlite:///project_board.sqlite3"


def health() -> dict[str, str]:
    """Return the process health without consulting external resources."""
    return {"status": "ok"}


def create_app(
    *,
    session_factory: SessionFactory | None = None,
    database_url: str = DEFAULT_DATABASE_URL,
) -> FastAPI:
    """Compose an application with either an injected or development database."""
    engine = None
    if session_factory is None:
        engine = create_database_engine(database_url)
        session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if engine is not None:
            initialize_schema(engine)
        yield
        if engine is not None:
            engine.dispose()

    application = FastAPI(title="Local Project Board", lifespan=lifespan)
    application.state.session_factory = session_factory
    application.add_api_route("/health", health, methods=["GET"])
    application.include_router(project_router)
    return application


app = create_app()
