"""
범용 MCP 도구 래퍼
모든 MCP 서버의 도구를 LangChain Tool로 변환하여 에이전트에서 사용할 수 있도록 지원
"""
import asyncio
import json
from typing import Any, Dict, List, Optional, Union, Type
from datetime import datetime
import traceback

from langchain.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from app.mcp.registry import get_mcp_registry, MCPServerInstance
from app.core.logging import logger


class MCPToolInput(BaseModel):
    """MCP 도구 입력 기본 모델"""
    server_name: str = Field(description="MCP 서버 이름")
    tool_name: str = Field(description="도구 이름")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="도구 매개변수")


class MCPToolWrapper(BaseTool):
    """범용 MCP 도구 래퍼"""
    
    name: str = "mcp_tool"
    description: str = "MCP 서버의 도구를 실행합니다"
    args_schema: Type[BaseModel] = MCPToolInput
    
    def __init__(self, server_name: str, tool_info: Dict[str, Any], **kwargs):
        """
        Args:
            server_name: MCP 서버 이름
            tool_info: MCP 도구 정보
        """
        self.server_name = server_name
        self.tool_info = tool_info
        self.tool_name = tool_info.get("name", "unknown_tool")
        
        # 도구 이름과 설명 설정
        name = f"mcp_{server_name}_{self.tool_name}"
        description = tool_info.get("description", f"MCP 도구: {self.tool_name}")
        
        # 동적 입력 스키마 생성
        args_schema = self._create_input_schema(tool_info)
        
        super().__init__(
            name=name,
            description=description,
            args_schema=args_schema,
            **kwargs
        )
    
    def _create_input_schema(self, tool_info: Dict[str, Any]) -> Type[BaseModel]:
        """도구 정보에서 동적 입력 스키마 생성"""
        try:
            # 도구의 매개변수 정보 추출
            input_schema = tool_info.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            # Pydantic 필드 생성
            fields = {}
            
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "string")
                param_description = param_info.get("description", f"{param_name} parameter")
                param_default = param_info.get("default")
                
                # 타입 매핑
                python_type = self._map_json_type_to_python(param_type)
                
                # 필드 생성
                if param_name in required:
                    fields[param_name] = (python_type, Field(description=param_description))
                else:
                    fields[param_name] = (Optional[python_type], Field(default=param_default, description=param_description))
            
            # 기본 필드가 없으면 최소한의 입력 스키마 생성
            if not fields:
                fields = {
                    "input": (Optional[str], Field(default=None, description="도구 입력"))
                }
            
            # 동적 모델 생성
            schema_name = f"{self.tool_name.title()}Input"
            return create_model(schema_name, **fields)
            
        except Exception as e:
            logger.warning(f"도구 입력 스키마 생성 실패: {self.tool_name} - {e}")
            # 기본 스키마 반환
            return create_model(
                f"{self.tool_name.title()}Input",
                input=(Optional[str], Field(default=None, description="도구 입력"))
            )
    
    def _map_json_type_to_python(self, json_type: str) -> Type:
        """JSON Schema 타입을 Python 타입으로 매핑"""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": List[Any],
            "object": Dict[str, Any],
            "null": type(None)
        }
        return type_mapping.get(json_type, str)
    
    def _run(self, **kwargs) -> str:
        """동기 실행 (비동기를 동기로 변환)"""
        loop = None
        try:
            # 현재 이벤트 루프 확인
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 이벤트 루프가 없으면 새로 생성
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._arun(**kwargs))
        
        # 이미 실행 중인 루프가 있으면 새 스레드에서 실행
        import concurrent.futures
        import threading
        
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(self._arun(**kwargs))
            finally:
                new_loop.close()
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_thread)
            return future.result()
    
    async def _arun(self, **kwargs) -> str:
        """비동기 실행"""
        try:
            logger.debug(f"MCP 도구 실행: {self.name} - {kwargs}")
            
            # MCP 레지스트리에서 서버 인스턴스 가져오기
            registry = get_mcp_registry()
            server_instance = registry.get_server(self.server_name)
            
            if not server_instance:
                return f"오류: MCP 서버를 찾을 수 없습니다: {self.server_name}"
            
            if not server_instance.is_healthy:
                return f"오류: MCP 서버가 비활성화 상태입니다: {self.server_name}"
            
            if not server_instance.client:
                return f"오류: MCP 클라이언트가 연결되지 않았습니다: {self.server_name}"
            
            # 도구 호출
            result = await self._call_mcp_tool(server_instance, kwargs)
            
            # 결과 포맷팅
            if isinstance(result, dict):
                if "error" in result:
                    return f"도구 실행 오류: {result['error']}"
                elif "content" in result:
                    return self._format_tool_result(result["content"])
                else:
                    return json.dumps(result, ensure_ascii=False, indent=2)
            elif isinstance(result, str):
                return result
            else:
                return str(result)
                
        except Exception as e:
            error_msg = f"MCP 도구 실행 중 오류 발생: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            return error_msg
    
    async def _call_mcp_tool(self, server_instance: MCPServerInstance, parameters: Dict[str, Any]) -> Any:
        """MCP 도구 호출"""
        client = server_instance.client
        
        try:
            # call_tool 메서드 확인 및 호출
            if hasattr(client, 'call_tool'):
                return await client.call_tool(self.tool_name, parameters)
            elif hasattr(client, 'request'):
                # 일반적인 MCP 클라이언트 인터페이스
                return await client.request("tools/call", {
                    "name": self.tool_name,
                    "arguments": parameters
                })
            else:
                # 사용자 정의 클라이언트 처리
                return await self._handle_custom_client(client, parameters)
                
        except Exception as e:
            logger.error(f"MCP 도구 호출 실패: {self.tool_name} - {e}")
            raise e
    
    async def _handle_custom_client(self, client: Any, parameters: Dict[str, Any]) -> Any:
        """사용자 정의 클라이언트 처리"""
        # Monday.com 클라이언트 처리
        if hasattr(client, 'execute_query') and 'monday' in self.server_name.lower():
            return await self._handle_monday_tool(client, parameters)
        
        # 기타 클라이언트 처리
        raise NotImplementedError(f"지원하지 않는 클라이언트 유형: {type(client)}")
    
    async def _handle_monday_tool(self, client: Any, parameters: Dict[str, Any]) -> Any:
        """Monday.com 도구 처리"""
        try:
            # Monday.com 도구별 처리
            if self.tool_name == "get_project_summary":
                board_id = parameters.get("board_id")
                return await client.get_project_summary(board_id)
            elif self.tool_name == "create_item":
                board_id = parameters.get("board_id")
                item_name = parameters.get("item_name", "새 작업")
                column_values = parameters.get("column_values", {})
                return await client.create_item(board_id, item_name, column_values)
            elif self.tool_name == "update_item":
                item_id = parameters.get("item_id")
                column_values = parameters.get("column_values", {})
                return await client.update_item(item_id, column_values)
            elif self.tool_name == "delete_item":
                item_id = parameters.get("item_id")
                return await client.delete_item(item_id)
            elif self.tool_name == "search_items":
                query = parameters.get("query", "")
                board_ids = parameters.get("board_ids", [])
                return await client.search_items(query, board_ids)
            elif self.tool_name == "get_board_details":
                board_id = parameters.get("board_id")
                return await client.get_board_details(board_id)
            else:
                raise ValueError(f"지원하지 않는 Monday.com 도구: {self.tool_name}")
                
        except Exception as e:
            logger.error(f"Monday.com 도구 처리 실패: {self.tool_name} - {e}")
            raise e
    
    def _format_tool_result(self, content: Any) -> str:
        """도구 실행 결과 포맷팅"""
        try:
            if isinstance(content, list):
                if all(isinstance(item, dict) for item in content):
                    # 구조화된 데이터 테이블 형식으로 포맷팅
                    return self._format_table_data(content)
                else:
                    return "\n".join(str(item) for item in content)
            elif isinstance(content, dict):
                return json.dumps(content, ensure_ascii=False, indent=2)
            else:
                return str(content)
        except Exception as e:
            logger.warning(f"결과 포맷팅 실패: {e}")
            return str(content)
    
    def _format_table_data(self, data: List[Dict[str, Any]]) -> str:
        """테이블 형식 데이터 포맷팅"""
        if not data:
            return "결과가 없습니다."
        
        try:
            # 첫 번째 항목에서 키 추출
            headers = list(data[0].keys())
            
            # 테이블 생성
            lines = []
            lines.append(" | ".join(headers))
            lines.append(" | ".join("-" * len(header) for header in headers))
            
            for item in data:
                row = []
                for header in headers:
                    value = item.get(header, "")
                    # 값이 너무 길면 자르기
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + "..."
                    row.append(str(value))
                lines.append(" | ".join(row))
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"테이블 포맷팅 실패: {e}")
            return json.dumps(data, ensure_ascii=False, indent=2)


class MCPToolManager:
    """MCP 도구 관리자"""
    
    def __init__(self):
        """도구 관리자 초기화"""
        self.tools_cache: Dict[str, List[MCPToolWrapper]] = {}
        self.last_update: Dict[str, datetime] = {}
        self.cache_ttl = 300  # 5분 캐시
    
    async def get_tools_for_server(self, server_name: str, force_refresh: bool = False) -> List[MCPToolWrapper]:
        """특정 서버의 도구 목록 반환"""
        # 캐시 확인
        if not force_refresh and self._is_cache_valid(server_name):
            return self.tools_cache.get(server_name, [])
        
        # 도구 목록 새로 생성
        tools = await self._create_tools_for_server(server_name)
        
        # 캐시 업데이트
        self.tools_cache[server_name] = tools
        self.last_update[server_name] = datetime.now()
        
        return tools
    
    async def get_all_tools(self, force_refresh: bool = False) -> List[MCPToolWrapper]:
        """모든 서버의 도구 목록 반환"""
        registry = get_mcp_registry()
        all_tools = []
        
        for server_instance in registry.get_healthy_servers():
            server_tools = await self.get_tools_for_server(
                server_instance.config.name, 
                force_refresh
            )
            all_tools.extend(server_tools)
        
        return all_tools
    
    async def get_tools_by_category(self, category: str) -> List[MCPToolWrapper]:
        """카테고리별 도구 목록 반환"""
        all_tools = await self.get_all_tools()
        
        # 도구 설정에서 카테고리 필터링
        filtered_tools = []
        for tool in all_tools:
            if hasattr(tool, 'tool_info') and tool.tool_info:
                tool_category = tool.tool_info.get("category", "general")
                if tool_category == category:
                    filtered_tools.append(tool)
        
        return filtered_tools
    
    async def get_tools_for_agent(self, agent_type: str) -> List[MCPToolWrapper]:
        """에이전트 타입별 도구 목록 반환"""
        all_tools = await self.get_all_tools()
        
        # 도구 설정에서 에이전트 타입 필터링
        filtered_tools = []
        for tool in all_tools:
            if hasattr(tool, 'tool_info') and tool.tool_info:
                agent_types = tool.tool_info.get("agent_types", ["general"])
                if agent_type in agent_types or "general" in agent_types:
                    filtered_tools.append(tool)
        
        return filtered_tools
    
    async def _create_tools_for_server(self, server_name: str) -> List[MCPToolWrapper]:
        """특정 서버의 도구 래퍼 생성"""
        registry = get_mcp_registry()
        server_instance = registry.get_server(server_name)
        
        if not server_instance or not server_instance.is_healthy:
            logger.warning(f"서버가 비활성화 상태이거나 찾을 수 없습니다: {server_name}")
            return []
        
        tools = []
        
        try:
            # 서버에서 사용 가능한 도구 목록 가져오기
            available_tools = server_instance.available_tools
            
            if not available_tools:
                # 도구 목록을 다시 가져오기 시도
                if server_instance.client and hasattr(server_instance.client, 'list_tools'):
                    tools_result = await server_instance.client.list_tools()
                    if tools_result and hasattr(tools_result, 'tools'):
                        available_tools = [tool.dict() for tool in tools_result.tools]
                    elif isinstance(tools_result, dict) and 'tools' in tools_result:
                        available_tools = tools_result['tools']
                    elif isinstance(tools_result, list):
                        available_tools = tools_result
            
            # 도구 래퍼 생성
            for tool_info in available_tools:
                try:
                    tool_wrapper = MCPToolWrapper(server_name, tool_info)
                    tools.append(tool_wrapper)
                    logger.debug(f"도구 래퍼 생성: {tool_wrapper.name}")
                except Exception as e:
                    logger.warning(f"도구 래퍼 생성 실패: {tool_info.get('name', 'unknown')} - {e}")
            
            logger.info(f"서버 도구 생성 완료: {server_name} - {len(tools)}개 도구")
            
        except Exception as e:
            logger.error(f"서버 도구 생성 실패: {server_name} - {e}")
        
        return tools
    
    def _is_cache_valid(self, server_name: str) -> bool:
        """캐시 유효성 확인"""
        if server_name not in self.last_update:
            return False
        
        elapsed = (datetime.now() - self.last_update[server_name]).total_seconds()
        return elapsed < self.cache_ttl
    
    def clear_cache(self, server_name: Optional[str] = None):
        """캐시 정리"""
        if server_name:
            self.tools_cache.pop(server_name, None)
            self.last_update.pop(server_name, None)
        else:
            self.tools_cache.clear()
            self.last_update.clear()
    
    async def refresh_tools(self, server_name: Optional[str] = None):
        """도구 목록 새로고침"""
        if server_name:
            await self.get_tools_for_server(server_name, force_refresh=True)
        else:
            registry = get_mcp_registry()
            for server_instance in registry.get_all_servers():
                await self.get_tools_for_server(server_instance.config.name, force_refresh=True)


# 싱글톤 인스턴스
_tool_manager: Optional[MCPToolManager] = None


def get_mcp_tool_manager() -> MCPToolManager:
    """MCP 도구 관리자 싱글톤 반환"""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = MCPToolManager()
    return _tool_manager