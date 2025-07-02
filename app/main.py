"""Main FastAPI application"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import ValidationError as PydanticValidationError

from app.core.config import settings
from app.core.logging import logger
from app.core.middleware import RequestIDMiddleware, LoggingMiddleware
from app.core.exceptions import MojiException
from app.core.error_handlers import (
    moji_exception_handler,
    validation_exception_handler,
    general_exception_handler
)
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    
    # Initialize MCP system (before LLM and agents)
    mcp_config = None
    registry = None
    discovery_service = None
    
    try:
        # 1. MCP 설정 초기화
        from app.core.mcp_config import initialize_mcp_config
        mcp_config = await initialize_mcp_config()
        logger.info("MCP 설정 초기화 완료")
        
        # 2. MCP 서버 레지스트리 초기화
        from app.mcp.registry import get_mcp_registry
        registry = get_mcp_registry()
        await registry.initialize(mcp_config)
        logger.info("MCP 서버 레지스트리 초기화 완료")
        
        # 3. MCP 발견 서비스 초기화
        from app.services.mcp_discovery import get_mcp_discovery_service
        discovery_service = get_mcp_discovery_service()
        await discovery_service.start_auto_discovery()
        logger.info("MCP 발견 서비스 초기화 완료")
        
        # 4. 도구 레지스트리에 MCP 도구 로드
        from app.agents.tools import tool_registry
        await tool_registry.load_mcp_tools()
        logger.info("MCP 도구 로드 완료")
        
    except Exception as e:
        logger.warning(f"MCP 시스템 초기화 실패 (계속 진행): {e}")
    
    # Initialize LLM router
    from app.llm.router import llm_router
    await llm_router.initialize()
    
    # Initialize agent system
    from app.agents.manager import agent_manager
    await agent_manager.initialize_default_agents()
    
    yield
    
    # Cleanup MCP system
    logger.info("Shutting down application")
    
    try:
        # MCP 시스템 정리
        if discovery_service:
            await discovery_service.shutdown()
            logger.info("MCP 발견 서비스 종료")
        
        if registry:
            await registry.shutdown()
            logger.info("MCP 서버 레지스트리 종료")
        
        # MCP 설정 관리자 정리
        from app.core.mcp_config import get_mcp_config_manager
        config_manager = get_mcp_config_manager()
        await config_manager.shutdown()
        logger.info("MCP 설정 관리자 종료")
        
    except Exception as e:
        logger.error(f"MCP 시스템 종료 중 오류: {e}")
    
    logger.info("애플리케이션 종료 완료")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
app.exception_handler(MojiException)(moji_exception_handler)
app.exception_handler(PydanticValidationError)(validation_exception_handler)
app.exception_handler(Exception)(general_exception_handler)


# Include routers
app.include_router(api_router, prefix="/api/v1")

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")