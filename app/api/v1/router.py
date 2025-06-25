"""API v1 router"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, chat

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])