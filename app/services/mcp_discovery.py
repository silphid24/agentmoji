"""
MCP 도구 발견 서비스
MCP 서버에서 도구, 리소스, 프롬프트를 자동으로 발견하고 캐싱하는 서비스
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
import hashlib

from app.mcp.registry import get_mcp_registry, MCPServerInstance
from app.tools.mcp_tool import get_mcp_tool_manager, MCPToolWrapper
from app.core.logging import logger


@dataclass
class MCPResource:
    """MCP 리소스 정보"""
    name: str
    uri: str
    mime_type: Optional[str] = None
    description: Optional[str] = None
    server_name: str = ""
    last_updated: Optional[datetime] = None


@dataclass
class MCPPrompt:
    """MCP 프롬프트 정보"""
    name: str
    description: Optional[str] = None
    arguments: List[str] = None
    server_name: str = ""
    last_updated: Optional[datetime] = None
    
    def __post_init__(self):
        if self.arguments is None:
            self.arguments = []


@dataclass
class MCPTool:
    """MCP 도구 정보"""
    name: str
    description: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    category: str = "general"
    server_name: str = ""
    last_updated: Optional[datetime] = None


@dataclass
class MCPServerCapabilities:
    """MCP 서버 기능 정보"""
    server_name: str
    tools: List[MCPTool] = None
    resources: List[MCPResource] = None
    prompts: List[MCPPrompt] = None
    last_discovery: Optional[datetime] = None
    discovery_hash: Optional[str] = None
    
    def __post_init__(self):
        if self.tools is None:
            self.tools = []
        if self.resources is None:
            self.resources = []
        if self.prompts is None:
            self.prompts = []


class MCPDiscoveryService:
    """MCP 도구 발견 서비스"""
    
    def __init__(self):
        """서비스 초기화"""
        self.capabilities_cache: Dict[str, MCPServerCapabilities] = {}
        self.discovery_lock = asyncio.Lock()
        
        # 설정
        self.cache_ttl = 300  # 5분 캐시 TTL
        self.discovery_timeout = 30  # 30초 발견 타임아웃
        self.auto_discovery_interval = 600  # 10분마다 자동 발견
        
        # 자동 발견 태스크
        self.auto_discovery_task: Optional[asyncio.Task] = None
        self.auto_discovery_running = False
        
        # 변경 감지
        self.change_callbacks: List[callable] = []
    
    async def start_auto_discovery(self):
        """자동 발견 시작"""
        if self.auto_discovery_running:
            return
        
        self.auto_discovery_running = True
        self.auto_discovery_task = asyncio.create_task(self._auto_discovery_loop())
        logger.info("MCP 자동 발견 시작")
    
    async def stop_auto_discovery(self):
        """자동 발견 중지"""
        self.auto_discovery_running = False
        
        if self.auto_discovery_task:
            self.auto_discovery_task.cancel()
            try:
                await self.auto_discovery_task
            except asyncio.CancelledError:
                pass
            self.auto_discovery_task = None
        
        logger.info("MCP 자동 발견 중지")
    
    async def _auto_discovery_loop(self):
        """자동 발견 루프"""
        while self.auto_discovery_running:
            try:
                await self.discover_all_servers()
                await asyncio.sleep(self.auto_discovery_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"자동 발견 중 오류: {e}")
                await asyncio.sleep(60)  # 오류 시 1분 대기
    
    async def discover_all_servers(self, force_refresh: bool = False) -> Dict[str, MCPServerCapabilities]:
        """모든 MCP 서버 발견"""
        async with self.discovery_lock:
            registry = get_mcp_registry()
            healthy_servers = registry.get_healthy_servers()
            
            if not healthy_servers:
                logger.info("발견할 건강한 MCP 서버가 없습니다")
                return {}
            
            logger.info(f"MCP 서버 발견 시작: {len(healthy_servers)}개 서버")
            
            # 병렬로 서버 발견
            discovery_tasks = [
                self.discover_server(server.config.name, force_refresh)
                for server in healthy_servers
            ]
            
            results = await asyncio.gather(*discovery_tasks, return_exceptions=True)
            
            # 결과 처리
            discovered_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    server_name = healthy_servers[i].config.name
                    logger.error(f"서버 발견 실패: {server_name} - {result}")
                elif result:
                    discovered_count += 1
            
            logger.info(f"MCP 서버 발견 완료: {discovered_count}/{len(healthy_servers)}개 성공")
            
            # 변경 알림
            await self._notify_capabilities_changed()
            
            return self.capabilities_cache
    
    async def discover_server(self, server_name: str, force_refresh: bool = False) -> Optional[MCPServerCapabilities]:
        """특정 서버 발견"""
        # 캐시 확인
        if not force_refresh and self._is_cache_valid(server_name):
            return self.capabilities_cache.get(server_name)
        
        try:
            registry = get_mcp_registry()
            server_instance = registry.get_server(server_name)
            
            if not server_instance or not server_instance.is_healthy:
                logger.warning(f"서버가 비활성화 상태: {server_name}")
                return None
            
            logger.debug(f"서버 발견 시작: {server_name}")
            
            # 서버 기능 발견
            capabilities = await self._discover_server_capabilities(server_instance)
            
            if capabilities:
                # 변경 감지를 위한 해시 계산
                capabilities.discovery_hash = self._calculate_capabilities_hash(capabilities)
                capabilities.last_discovery = datetime.now()
                
                # 캐시 업데이트
                old_capabilities = self.capabilities_cache.get(server_name)
                self.capabilities_cache[server_name] = capabilities
                
                # 변경 감지
                if old_capabilities and old_capabilities.discovery_hash != capabilities.discovery_hash:
                    logger.info(f"서버 기능 변경 감지: {server_name}")
                    await self._handle_capabilities_change(server_name, old_capabilities, capabilities)
                
                logger.info(
                    f"서버 발견 완료: {server_name} - "
                    f"도구 {len(capabilities.tools)}개, "
                    f"리소스 {len(capabilities.resources)}개, "
                    f"프롬프트 {len(capabilities.prompts)}개"
                )
                
                return capabilities
            
        except Exception as e:
            logger.error(f"서버 발견 실패: {server_name} - {e}")
        
        return None
    
    async def _discover_server_capabilities(self, server_instance: MCPServerInstance) -> Optional[MCPServerCapabilities]:
        """서버 기능 발견"""
        capabilities = MCPServerCapabilities(server_name=server_instance.config.name)
        client = server_instance.client
        
        if not client:
            return None
        
        try:
            # 도구 발견
            await asyncio.wait_for(
                self._discover_tools(client, capabilities),
                timeout=self.discovery_timeout
            )
            
            # 리소스 발견
            await asyncio.wait_for(
                self._discover_resources(client, capabilities),
                timeout=self.discovery_timeout
            )
            
            # 프롬프트 발견
            await asyncio.wait_for(
                self._discover_prompts(client, capabilities),
                timeout=self.discovery_timeout
            )
            
            return capabilities
            
        except asyncio.TimeoutError:
            logger.warning(f"서버 발견 타임아웃: {server_instance.config.name}")
            return capabilities
        except Exception as e:
            logger.error(f"서버 기능 발견 오류: {server_instance.config.name} - {e}")
            return None
    
    async def _discover_tools(self, client: Any, capabilities: MCPServerCapabilities):
        """도구 발견"""
        try:
            tools_result = None
            
            # 다양한 클라이언트 인터페이스 시도
            if hasattr(client, 'list_tools'):
                tools_result = await client.list_tools()
            elif hasattr(client, 'request'):
                tools_result = await client.request("tools/list", {})
            
            if tools_result:
                tools_list = []
                
                # 결과 형식에 따라 처리
                if hasattr(tools_result, 'tools'):
                    tools_list = [tool.dict() if hasattr(tool, 'dict') else tool for tool in tools_result.tools]
                elif isinstance(tools_result, dict) and 'tools' in tools_result:
                    tools_list = tools_result['tools']
                elif isinstance(tools_result, list):
                    tools_list = tools_result
                
                # MCPTool 객체로 변환
                for tool_data in tools_list:
                    if isinstance(tool_data, dict):
                        tool = MCPTool(
                            name=tool_data.get('name', ''),
                            description=tool_data.get('description'),
                            input_schema=tool_data.get('inputSchema'),
                            category=tool_data.get('category', 'general'),
                            server_name=capabilities.server_name,
                            last_updated=datetime.now()
                        )
                        capabilities.tools.append(tool)
                
                logger.debug(f"도구 발견 완료: {capabilities.server_name} - {len(capabilities.tools)}개")
                
        except Exception as e:
            logger.warning(f"도구 발견 실패: {capabilities.server_name} - {e}")
    
    async def _discover_resources(self, client: Any, capabilities: MCPServerCapabilities):
        """리소스 발견"""
        try:
            resources_result = None
            
            # 다양한 클라이언트 인터페이스 시도
            if hasattr(client, 'list_resources'):
                resources_result = await client.list_resources()
            elif hasattr(client, 'request'):
                resources_result = await client.request("resources/list", {})
            
            if resources_result:
                resources_list = []
                
                # 결과 형식에 따라 처리
                if hasattr(resources_result, 'resources'):
                    resources_list = [res.dict() if hasattr(res, 'dict') else res for res in resources_result.resources]
                elif isinstance(resources_result, dict) and 'resources' in resources_result:
                    resources_list = resources_result['resources']
                elif isinstance(resources_result, list):
                    resources_list = resources_result
                
                # MCPResource 객체로 변환
                for resource_data in resources_list:
                    if isinstance(resource_data, dict):
                        resource = MCPResource(
                            name=resource_data.get('name', ''),
                            uri=resource_data.get('uri', ''),
                            mime_type=resource_data.get('mimeType'),
                            description=resource_data.get('description'),
                            server_name=capabilities.server_name,
                            last_updated=datetime.now()
                        )
                        capabilities.resources.append(resource)
                
                logger.debug(f"리소스 발견 완료: {capabilities.server_name} - {len(capabilities.resources)}개")
                
        except Exception as e:
            logger.warning(f"리소스 발견 실패: {capabilities.server_name} - {e}")
    
    async def _discover_prompts(self, client: Any, capabilities: MCPServerCapabilities):
        """프롬프트 발견"""
        try:
            prompts_result = None
            
            # 다양한 클라이언트 인터페이스 시도
            if hasattr(client, 'list_prompts'):
                prompts_result = await client.list_prompts()
            elif hasattr(client, 'request'):
                prompts_result = await client.request("prompts/list", {})
            
            if prompts_result:
                prompts_list = []
                
                # 결과 형식에 따라 처리
                if hasattr(prompts_result, 'prompts'):
                    prompts_list = [prompt.dict() if hasattr(prompt, 'dict') else prompt for prompt in prompts_result.prompts]
                elif isinstance(prompts_result, dict) and 'prompts' in prompts_result:
                    prompts_list = prompts_result['prompts']
                elif isinstance(prompts_result, list):
                    prompts_list = prompts_result
                
                # MCPPrompt 객체로 변환
                for prompt_data in prompts_list:
                    if isinstance(prompt_data, dict):
                        prompt = MCPPrompt(
                            name=prompt_data.get('name', ''),
                            description=prompt_data.get('description'),
                            arguments=prompt_data.get('arguments', []),
                            server_name=capabilities.server_name,
                            last_updated=datetime.now()
                        )
                        capabilities.prompts.append(prompt)
                
                logger.debug(f"프롬프트 발견 완료: {capabilities.server_name} - {len(capabilities.prompts)}개")
                
        except Exception as e:
            logger.warning(f"프롬프트 발견 실패: {capabilities.server_name} - {e}")
    
    def _calculate_capabilities_hash(self, capabilities: MCPServerCapabilities) -> str:
        """기능 해시 계산 (변경 감지용)"""
        # 기능 정보를 문자열로 직렬화
        data = {
            'tools': [{'name': t.name, 'description': t.description, 'schema': t.input_schema} for t in capabilities.tools],
            'resources': [{'name': r.name, 'uri': r.uri, 'type': r.mime_type} for r in capabilities.resources],
            'prompts': [{'name': p.name, 'description': p.description, 'args': p.arguments} for p in capabilities.prompts]
        }
        
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def _is_cache_valid(self, server_name: str) -> bool:
        """캐시 유효성 확인"""
        capabilities = self.capabilities_cache.get(server_name)
        if not capabilities or not capabilities.last_discovery:
            return False
        
        elapsed = datetime.now() - capabilities.last_discovery
        return elapsed.total_seconds() < self.cache_ttl
    
    async def _handle_capabilities_change(self, 
                                       server_name: str,
                                       old_capabilities: MCPServerCapabilities,
                                       new_capabilities: MCPServerCapabilities):
        """기능 변경 처리"""
        # 도구 관리자 캐시 무효화
        tool_manager = get_mcp_tool_manager()
        tool_manager.clear_cache(server_name)
        
        # 변경 사항 로깅
        old_tool_names = {t.name for t in old_capabilities.tools}
        new_tool_names = {t.name for t in new_capabilities.tools}
        
        added_tools = new_tool_names - old_tool_names
        removed_tools = old_tool_names - new_tool_names
        
        if added_tools:
            logger.info(f"새 도구 발견: {server_name} - {added_tools}")
        if removed_tools:
            logger.info(f"도구 제거됨: {server_name} - {removed_tools}")
    
    async def _notify_capabilities_changed(self):
        """기능 변경 콜백 실행"""
        for callback in self.change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self.capabilities_cache)
                else:
                    callback(self.capabilities_cache)
            except Exception as e:
                logger.error(f"기능 변경 콜백 오류: {e}")
    
    # 조회 메서드
    def get_server_capabilities(self, server_name: str) -> Optional[MCPServerCapabilities]:
        """서버 기능 반환"""
        return self.capabilities_cache.get(server_name)
    
    def get_all_capabilities(self) -> Dict[str, MCPServerCapabilities]:
        """모든 서버 기능 반환"""
        return self.capabilities_cache.copy()
    
    def get_all_tools(self) -> List[MCPTool]:
        """모든 도구 목록 반환"""
        all_tools = []
        for capabilities in self.capabilities_cache.values():
            all_tools.extend(capabilities.tools)
        return all_tools
    
    def get_tools_by_category(self, category: str) -> List[MCPTool]:
        """카테고리별 도구 목록 반환"""
        return [tool for tool in self.get_all_tools() if tool.category == category]
    
    def get_tools_by_server(self, server_name: str) -> List[MCPTool]:
        """서버별 도구 목록 반환"""
        capabilities = self.capabilities_cache.get(server_name)
        return capabilities.tools if capabilities else []
    
    def get_all_resources(self) -> List[MCPResource]:
        """모든 리소스 목록 반환"""
        all_resources = []
        for capabilities in self.capabilities_cache.values():
            all_resources.extend(capabilities.resources)
        return all_resources
    
    def get_all_prompts(self) -> List[MCPPrompt]:
        """모든 프롬프트 목록 반환"""
        all_prompts = []
        for capabilities in self.capabilities_cache.values():
            all_prompts.extend(capabilities.prompts)
        return all_prompts
    
    def search_tools(self, query: str) -> List[MCPTool]:
        """도구 검색"""
        query_lower = query.lower()
        results = []
        
        for tool in self.get_all_tools():
            if (query_lower in tool.name.lower() or 
                (tool.description and query_lower in tool.description.lower())):
                results.append(tool)
        
        return results
    
    def get_discovery_stats(self) -> Dict[str, Any]:
        """발견 통계 반환"""
        total_tools = len(self.get_all_tools())
        total_resources = len(self.get_all_resources())
        total_prompts = len(self.get_all_prompts())
        
        categories = {}
        for tool in self.get_all_tools():
            categories[tool.category] = categories.get(tool.category, 0) + 1
        
        return {
            'total_servers': len(self.capabilities_cache),
            'total_tools': total_tools,
            'total_resources': total_resources,
            'total_prompts': total_prompts,
            'tool_categories': categories,
            'auto_discovery_running': self.auto_discovery_running,
            'cache_ttl_seconds': self.cache_ttl
        }
    
    # 콜백 관리
    def add_change_callback(self, callback: callable):
        """기능 변경 콜백 추가"""
        self.change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: callable):
        """기능 변경 콜백 제거"""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    # 캐시 관리
    def clear_cache(self, server_name: Optional[str] = None):
        """캐시 정리"""
        if server_name:
            self.capabilities_cache.pop(server_name, None)
        else:
            self.capabilities_cache.clear()
    
    def export_capabilities(self) -> Dict[str, Any]:
        """기능 정보 내보내기"""
        export_data = {}
        for server_name, capabilities in self.capabilities_cache.items():
            export_data[server_name] = {
                'tools': [asdict(tool) for tool in capabilities.tools],
                'resources': [asdict(resource) for resource in capabilities.resources],
                'prompts': [asdict(prompt) for prompt in capabilities.prompts],
                'last_discovery': capabilities.last_discovery.isoformat() if capabilities.last_discovery else None,
                'discovery_hash': capabilities.discovery_hash
            }
        return export_data
    
    async def shutdown(self):
        """서비스 종료"""
        logger.info("MCP 발견 서비스 종료")
        await self.stop_auto_discovery()
        self.clear_cache()


# 싱글톤 인스턴스
_discovery_service: Optional[MCPDiscoveryService] = None


def get_mcp_discovery_service() -> MCPDiscoveryService:
    """MCP 발견 서비스 싱글톤 반환"""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = MCPDiscoveryService()
    return _discovery_service