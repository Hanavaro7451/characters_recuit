from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.characters import router as characters_router
from app.api.routes.health import router as health_router
from app.api.routes.users import router as user_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(user_router, prefix="/users", tags=["users"])
api_router.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
api_router.include_router(characters_router, prefix="/campaigns", tags=["characters"])
api_router.include_router(catalog_router, prefix="/catalog", tags=["catalog"])
