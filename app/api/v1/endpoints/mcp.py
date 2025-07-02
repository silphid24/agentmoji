"""
MCP 관리 API 엔드포인트
MCP 서버 관리, 도구 조회, 동적 설정을 위한 REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Path
from pydantic import BaseModel, Field
import json

from app.mcp.registry import get_mcp_registry, MCPServerInstance
from app.core.mcp_config import get_mcp_config_manager
from app.services.mcp_discovery import get_mcp_discovery_service
from app.tools.mcp_tool import get_mcp_tool_manager
from app.schemas.mcp_config import MCPServerConfig, MCPConfig
from app.api.v1.dependencies import get_current_user
from app.core.logging import logger

router = APIRouter()


# Pydantic 모델들
class ServerStatusResponse(BaseModel):
    """서버 상태 응답"""
    name: str
    display_name: str
    status: str
    enabled: bool
    is_healthy: bool
    uptime_seconds: Optional[float] = None
    tools_count: int
    resources_count: int
    prompts_count: int
    error_message: Optional[str] = None


class RegistryStatsResponse(BaseModel):
    """레지스트리 통계 응답"""
    total_servers: int
    running_servers: int
    healthy_servers: int
    total_starts: int
    total_stops: int
    total_errors: int
    health_check_running: bool


class ToolInfo(BaseModel):
    """도구 정보"""
    name: str
    description: Optional[str] = None
    server_name: str
    category: str = "general"
    agent_types: List[str] = Field(default_factory=list)


class ServerControlRequest(BaseModel):
    """서버 제어 요청"""
    action: str = Field(..., description="start, stop, restart 중 하나")


class DiscoveryStatsResponse(BaseModel):
    """발견 통계 응답"""
    total_servers: int
    total_tools: int
    total_resources: int
    total_prompts: int
    tool_categories: Dict[str, int]
    auto_discovery_running: bool
    cache_ttl_seconds: int


# 서버 관리 엔드포인트
@router.get("/servers", response_model=List[ServerStatusResponse])
async def get_servers(
    status_filter: Optional[str] = Query(None, description="상태 필터 (running, stopped, error)")
):
    """모든 MCP 서버 목록 조회"""
    try:
        registry = get_mcp_registry()
        servers = registry.get_all_servers()
        
        result = []
        for server in servers:
            server_info = server.get_info()
            
            # 상태 필터 적용
            if status_filter and server_info["status"] != status_filter:
                continue
            
            result.append(ServerStatusResponse(
                name=server_info["name"],
                display_name=server_info["display_name"],
                status=server_info["status"],
                enabled=server_info["enabled"],
                is_healthy=server_info["is_healthy"],
                uptime_seconds=server_info["uptime_seconds"],
                tools_count=server_info["tools_count"],
                resources_count=server_info["resources_count"],
                prompts_count=server_info["prompts_count"],
                error_message=server_info["error_message"]
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"서버 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servers/{server_name}", response_model=ServerStatusResponse)
async def get_server(server_name: str = Path(..., description="서버 이름")):
    """특정 MCP 서버 정보 조회"""
    try:
        registry = get_mcp_registry()
        server = registry.get_server(server_name)
        
        if not server:
            raise HTTPException(status_code=404, detail=f"서버를 찾을 수 없습니다: {server_name}")
        
        server_info = server.get_info()
        
        return ServerStatusResponse(
            name=server_info["name"],
            display_name=server_info["display_name"],
            status=server_info["status"],
            enabled=server_info["enabled"],
            is_healthy=server_info["is_healthy"],
            uptime_seconds=server_info["uptime_seconds"],
            tools_count=server_info["tools_count"],
            resources_count=server_info["resources_count"],
            prompts_count=server_info["prompts_count"],
            error_message=server_info["error_message"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"서버 정보 조회 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/servers/{server_name}/control")
async def control_server(
    server_name: str = Path(..., description="서버 이름"),
    request: ServerControlRequest = ...,
    background_tasks: BackgroundTasks = ...,
    current_user: dict = Depends(get_current_user)
):
    """MCP 서버 제어 (시작/중지/재시작)"""
    try:
        registry = get_mcp_registry()
        server = registry.get_server(server_name)
        
        if not server:
            raise HTTPException(status_code=404, detail=f"서버를 찾을 수 없습니다: {server_name}")
        
        action = request.action.lower()
        
        if action == "start":
            background_tasks.add_task(registry.start_server, server_name)
            message = f"서버 시작 요청이 접수되었습니다: {server_name}"
        elif action == "stop":
            background_tasks.add_task(registry.stop_server, server_name)
            message = f"서버 중지 요청이 접수되었습니다: {server_name}"
        elif action == "restart":
            background_tasks.add_task(registry.restart_server, server_name)
            message = f"서버 재시작 요청이 접수되었습니다: {server_name}"
        else:
            raise HTTPException(status_code=400, detail="지원하지 않는 액션입니다. start, stop, restart 중 하나를 사용하세요.")
        
        logger.info(f"서버 제어 요청: {server_name} - {action} (사용자: {current_user['username']})")
        
        return {"message": message, "action": action, "server": server_name}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"서버 제어 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/registry/stats", response_model=RegistryStatsResponse)
async def get_registry_stats():
    """레지스트리 통계 조회"""
    try:
        registry = get_mcp_registry()
        stats = registry.get_registry_stats()
        
        return RegistryStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"레지스트리 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 도구 관리 엔드포인트
@router.get("/tools", response_model=List[ToolInfo])
async def get_tools(
    server_name: Optional[str] = Query(None, description="서버별 필터"),
    category: Optional[str] = Query(None, description="카테고리별 필터"),
    agent_type: Optional[str] = Query(None, description="에이전트 타입별 필터")
):
    """MCP 도구 목록 조회"""
    try:
        tool_manager = get_mcp_tool_manager()
        
        if server_name:
            tools = await tool_manager.get_tools_for_server(server_name)
        elif category:
            tools = await tool_manager.get_tools_by_category(category)
        elif agent_type:
            tools = await tool_manager.get_tools_for_agent(agent_type)
        else:
            tools = await tool_manager.get_all_tools()
        
        result = []
        for tool in tools:
            if hasattr(tool, 'tool_info') and tool.tool_info:
                result.append(ToolInfo(
                    name=tool.name,
                    description=tool.description,
                    server_name=tool.server_name,
                    category=tool.tool_info.get("category", "general"),
                    agent_types=tool.tool_info.get("agent_types", ["general"])
                ))
        
        return result
        
    except Exception as e:
        logger.error(f"도구 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/refresh")
async def refresh_tools(
    server_name: Optional[str] = Query(None, description="특정 서버만 새로고침"),
    background_tasks: BackgroundTasks = ...,
    current_user: dict = Depends(get_current_user)
):
    """도구 캐시 새로고침"""
    try:
        tool_manager = get_mcp_tool_manager()
        
        background_tasks.add_task(tool_manager.refresh_tools, server_name)
        
        message = f"도구 새로고침 요청이 접수되었습니다"
        if server_name:
            message += f": {server_name}"
        
        logger.info(f"도구 새로고침 요청 (사용자: {current_user['username']})")
        
        return {"message": message}
        
    except Exception as e:
        logger.error(f"도구 새로고침 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/{server_name}/{tool_name}/call")
async def call_tool(
    server_name: str = Path(..., description="서버 이름"),
    tool_name: str = Path(..., description="도구 이름"),
    parameters: Dict[str, Any] = ...,
    current_user: dict = Depends(get_current_user)
):
    """MCP 도구 직접 호출"""
    try:
        tool_manager = get_mcp_tool_manager()
        tools = await tool_manager.get_tools_for_server(server_name)
        
        # 해당 도구 찾기
        target_tool = None
        for tool in tools:
            if tool.tool_name == tool_name:
                target_tool = tool
                break
        
        if not target_tool:
            raise HTTPException(
                status_code=404, 
                detail=f"도구를 찾을 수 없습니다: {server_name}/{tool_name}"
            )
        
        # 도구 실행
        result = await target_tool._arun(**parameters)
        
        logger.info(f"도구 호출: {server_name}/{tool_name} (사용자: {current_user['username']})")
        
        return {
            "tool": tool_name,
            "server": server_name,
            "parameters": parameters,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"도구 호출 실패: {server_name}/{tool_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 발견 서비스 엔드포인트
@router.get("/discovery/stats", response_model=DiscoveryStatsResponse)
async def get_discovery_stats():
    """발견 서비스 통계 조회"""
    try:
        discovery_service = get_mcp_discovery_service()
        stats = discovery_service.get_discovery_stats()
        
        return DiscoveryStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"발견 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discovery/refresh")
async def refresh_discovery(
    background_tasks: BackgroundTasks = ...,
    current_user: dict = Depends(get_current_user)
):
    """발견 서비스 새로고침"""
    try:
        discovery_service = get_mcp_discovery_service()
        
        background_tasks.add_task(discovery_service.discover_all_servers, True)
        
        logger.info(f"발견 새로고침 요청 (사용자: {current_user['username']})")
        
        return {"message": "발견 새로고침 요청이 접수되었습니다"}
        
    except Exception as e:
        logger.error(f"발견 새로고침 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discovery/capabilities")
async def get_capabilities():
    """모든 서버 기능 정보 조회"""
    try:
        discovery_service = get_mcp_discovery_service()
        capabilities = discovery_service.export_capabilities()
        
        return capabilities
        
    except Exception as e:
        logger.error(f"기능 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discovery/capabilities/{server_name}")
async def get_server_capabilities(server_name: str = Path(..., description="서버 이름")):
    """특정 서버 기능 정보 조회"""
    try:
        discovery_service = get_mcp_discovery_service()
        capabilities = discovery_service.get_server_capabilities(server_name)
        
        if not capabilities:
            raise HTTPException(status_code=404, detail=f"서버 기능 정보를 찾을 수 없습니다: {server_name}")
        
        return {
            "server_name": capabilities.server_name,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "last_updated": tool.last_updated.isoformat() if tool.last_updated else None
                }
                for tool in capabilities.tools
            ],
            "resources": [
                {
                    "name": resource.name,
                    "uri": resource.uri,
                    "mime_type": resource.mime_type,
                    "description": resource.description,
                    "last_updated": resource.last_updated.isoformat() if resource.last_updated else None
                }
                for resource in capabilities.resources
            ],
            "prompts": [
                {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": prompt.arguments,
                    "last_updated": prompt.last_updated.isoformat() if prompt.last_updated else None
                }
                for prompt in capabilities.prompts
            ],
            "last_discovery": capabilities.last_discovery.isoformat() if capabilities.last_discovery else None,
            "discovery_hash": capabilities.discovery_hash
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"서버 기능 정보 조회 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 설정 관리 엔드포인트
@router.get("/config")
async def get_config():
    """현재 MCP 설정 조회"""
    try:
        config_manager = get_mcp_config_manager()
        config = config_manager.get_config()
        
        if not config:
            raise HTTPException(status_code=404, detail="설정이 로드되지 않았습니다")
        
        return config.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"설정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config")
async def update_config(
    config: MCPConfig = ...,
    current_user: dict = Depends(get_current_user)
):
    """MCP 설정 업데이트"""
    try:
        config_manager = get_mcp_config_manager()
        
        # 설정 저장
        await config_manager.save_config(config)
        
        logger.info(f"MCP 설정 업데이트 (사용자: {current_user['username']})")
        
        return {"message": "설정이 업데이트되었습니다"}
        
    except Exception as e:
        logger.error(f"설정 업데이트 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/reload")
async def reload_config(
    background_tasks: BackgroundTasks = ...,
    current_user: dict = Depends(get_current_user)
):
    """설정 파일 다시 로드"""
    try:
        config_manager = get_mcp_config_manager()
        
        background_tasks.add_task(config_manager.load_config)
        
        logger.info(f"설정 리로드 요청 (사용자: {current_user['username']})")
        
        return {"message": "설정 리로드 요청이 접수되었습니다"}
        
    except Exception as e:
        logger.error(f"설정 리로드 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/servers/{server_name}")
async def get_server_config(server_name: str = Path(..., description="서버 이름")):
    """특정 서버 설정 조회"""
    try:
        config_manager = get_mcp_config_manager()
        server_config = config_manager.get_server_config(server_name)
        
        if not server_config:
            raise HTTPException(status_code=404, detail=f"서버 설정을 찾을 수 없습니다: {server_name}")
        
        return server_config.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"서버 설정 조회 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/servers/{server_name}")
async def update_server_config(
    server_name: str = Path(..., description="서버 이름"),
    updates: Dict[str, Any] = ...,
    current_user: dict = Depends(get_current_user)
):
    """특정 서버 설정 업데이트"""
    try:
        config_manager = get_mcp_config_manager()
        
        await config_manager.update_server_config(server_name, updates)
        
        logger.info(f"서버 설정 업데이트: {server_name} (사용자: {current_user['username']})")
        
        return {"message": f"서버 설정이 업데이트되었습니다: {server_name}"}
        
    except Exception as e:
        logger.error(f"서버 설정 업데이트 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/servers")
async def add_server_config(
    server_config: MCPServerConfig = ...,
    current_user: dict = Depends(get_current_user)
):
    """새 서버 설정 추가"""
    try:
        config_manager = get_mcp_config_manager()
        
        await config_manager.add_server_config(server_config)
        
        logger.info(f"새 서버 설정 추가: {server_config.name} (사용자: {current_user['username']})")
        
        return {"message": f"새 서버 설정이 추가되었습니다: {server_config.name}"}
        
    except Exception as e:
        logger.error(f"서버 설정 추가 실패: {server_config.name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/config/servers/{server_name}")
async def remove_server_config(
    server_name: str = Path(..., description="서버 이름"),
    current_user: dict = Depends(get_current_user)
):
    """서버 설정 제거"""
    try:
        config_manager = get_mcp_config_manager()
        
        await config_manager.remove_server_config(server_name)
        
        logger.info(f"서버 설정 제거: {server_name} (사용자: {current_user['username']})")
        
        return {"message": f"서버 설정이 제거되었습니다: {server_name}"}
        
    except Exception as e:
        logger.error(f"서버 설정 제거 실패: {server_name} - {e}")
        raise HTTPException(status_code=500, detail=str(e))


# 헬스 체크 엔드포인트
@router.get("/health")
async def health_check():
    """MCP 시스템 헬스 체크"""
    try:
        registry = get_mcp_registry()
        config_manager = get_mcp_config_manager()
        discovery_service = get_mcp_discovery_service()
        
        # 각 컴포넌트 상태 확인
        config = config_manager.get_config()
        stats = registry.get_registry_stats()
        discovery_stats = discovery_service.get_discovery_stats()
        
        healthy = (
            config is not None and
            config.global_config.enabled and
            stats["running_servers"] > 0
        )
        
        return {
            "status": "healthy" if healthy else "degraded",
            "config_loaded": config is not None,
            "servers_running": stats["running_servers"],
            "servers_healthy": stats["healthy_servers"],
            "total_tools": discovery_stats["total_tools"],
            "auto_discovery_running": discovery_stats["auto_discovery_running"],
            "timestamp": "2025-01-07T10:00:00Z"  # 실제 구현에서는 datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": "2025-01-07T10:00:00Z"
        }