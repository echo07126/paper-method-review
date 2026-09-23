from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "app_env": settings.app_env, "docs_enabled": settings.docs_enabled}
