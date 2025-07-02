"""API v1 router"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, chat, agents, llm, rag, vectorstore, adapters, monday, mcp

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(llm.router, prefix="/llm", tags=["llm"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(vectorstore.router, prefix="/vectorstore", tags=["vectorstore"])
api_router.include_router(adapters.router, prefix="/adapters", tags=["adapters"])
api_router.include_router(monday.router, prefix="/monday", tags=["monday"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])