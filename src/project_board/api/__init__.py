"""HTTP and Web API boundary for Local Project Board."""

from fastapi import APIRouter

from project_board.api.routes import router as project_router
from project_board.api.web_routes import router as web_router

router = APIRouter()
router.include_router(web_router)
router.include_router(project_router)

__all__ = ["router"]
