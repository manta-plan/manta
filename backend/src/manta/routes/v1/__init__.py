from fastapi import APIRouter

from manta.routes.v1.health_route import router as health_router
from manta.routes.v1.project_route import router as project_router

router = APIRouter(prefix="/v1")
router.include_router(health_router)
router.include_router(project_router)
