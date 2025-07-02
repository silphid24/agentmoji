"""Agent tools for enhanced capabilities"""

from typing import Optional, Dict, Any, List
from langchain.tools import Tool, BaseTool
from pydantic import BaseModel, Field
import json
import re
from datetime import datetime
import asyncio

from app.core.logging import logger
from app.core.config import settings


class CalculatorInput(BaseModel):
    """Input for calculator tool"""
    expression: str = Field(description="Mathematical expression to evaluate")


class SearchInput(BaseModel):
    """Input for search tool"""
    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Number of results")


def calculator_func(expression: str) -> str:
    """Simple calculator function"""
    try:
        # Remove any non-mathematical characters for safety
        safe_expr = re.sub(r'[^0-9+\-*/().\s]', '', expression)
        result = eval(safe_expr)
        return f"The result of {expression} is {result}"
    except Exception as e:
        return f"Error calculating {expression}: {str(e)}"


def datetime_func(format: Optional[str] = None) -> str:
    """Get current date and time"""
    now = datetime.now()
    if format:
        try:
            return now.strftime(format)
        except:
            pass
    return now.strftime("%Y-%m-%d %H:%M:%S")


def search_func(query: str, limit: int = 5) -> str:
    """Mock search function"""
    # TODO: Integrate with actual search service
    results = [
        {
            "title": f"Result {i+1} for '{query}'",
            "snippet": f"This is a placeholder result for your search query: {query}",
            "url": f"https://example.com/result{i+1}"
        }
        for i in range(min(limit, 3))
    ]
    return json.dumps(results, indent=2)


# Import Monday.com tools conditionally
MONDAY_TOOLS = {}
if settings.mcp_monday_enabled and settings.monday_api_key:
    try:
        from app.tools.monday.monday_tools import (
            MondayProjectSummaryTool,
            MondayCreateItemTool,
            MondayUpdateItemTool,
            MondayDeleteItemTool,
            MondaySearchTool,
            MondayBoardDetailsTool
        )
        
        MONDAY_TOOLS = {
            "monday_project_summary": MondayProjectSummaryTool(),
            "monday_create_item": MondayCreateItemTool(),
            "monday_update_item": MondayUpdateItemTool(),
            "monday_delete_item": MondayDeleteItemTool(),
            "monday_search": MondaySearchTool(),
            "monday_board_details": MondayBoardDetailsTool()
        }
        logger.info("Monday.com tools loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load Monday.com tools: {e}")


# Define available tools
AVAILABLE_TOOLS = {
    "calculator": Tool(
        name="Calculator",
        func=calculator_func,
        description="Useful for mathematical calculations. Input should be a mathematical expression."
    ),
    
    "datetime": Tool(
        name="DateTime",
        func=datetime_func,
        description="Get the current date and time. Optionally provide a format string."
    ),
    
    "search": Tool(
        name="Search",
        func=search_func,
        description="Search for information. Provide a query and optional result limit."
    ),
    
    **MONDAY_TOOLS  # Add Monday.com tools if available
}


class ToolRegistry:
    """Registry for managing agent tools (기존 도구 + 새로운 MCP 도구 통합)"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.mcp_tools_loaded = False
        self._load_default_tools()
    
    def _load_default_tools(self):
        """Load default tools"""
        for tool_name, tool in AVAILABLE_TOOLS.items():
            self.register_tool(tool_name, tool)
    
    def register_tool(self, name: str, tool: BaseTool):
        """Register a new tool"""
        self.tools[name] = tool
        logger.debug(f"Registered tool: {name}")
    
    def unregister_tool(self, name: str):
        """Unregister a tool"""
        if name in self.tools:
            del self.tools[name]
            logger.debug(f"Unregistered tool: {name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self.tools.get(name)
    
    async def load_mcp_tools(self) -> bool:
        """MCP 도구 로드"""
        if self.mcp_tools_loaded:
            return True
        
        try:
            from app.tools.mcp_tool import get_mcp_tool_manager
            
            tool_manager = get_mcp_tool_manager()
            mcp_tools = await tool_manager.get_all_tools()
            
            # 기존 MCP 도구 제거 (중복 방지)
            tools_to_remove = [name for name in self.tools.keys() if name.startswith('mcp_')]
            for tool_name in tools_to_remove:
                self.unregister_tool(tool_name)
            
            # 새 MCP 도구 등록
            for mcp_tool in mcp_tools:
                self.register_tool(mcp_tool.name, mcp_tool)
            
            self.mcp_tools_loaded = True
            logger.info(f"MCP 도구 로드 완료: {len(mcp_tools)}개 도구")
            return True
            
        except Exception as e:
            logger.warning(f"MCP 도구 로드 실패: {e}")
            return False
    
    async def refresh_mcp_tools(self):
        """MCP 도구 새로고침"""
        self.mcp_tools_loaded = False
        await self.load_mcp_tools()
    
    def get_tools_for_agent(self, agent_type: str) -> List[BaseTool]:
        """Get appropriate tools for agent type (MCP 도구 포함)"""
        # 기본 도구 세트
        monday_tools = []
        if settings.mcp_monday_enabled and settings.monday_api_key:
            monday_tools = [
                "monday_project_summary", 
                "monday_create_item", 
                "monday_update_item", 
                "monday_delete_item", 
                "monday_search", 
                "monday_board_details"
            ]
        
        # MCP 도구 포함 (mcp_ 접두어로 시작하는 도구들)
        mcp_tools = [name for name in self.tools.keys() if name.startswith('mcp_')]
        
        tool_sets = {
            "general": ["calculator", "datetime"] + monday_tools + mcp_tools,
            "task": ["calculator", "datetime", "search"] + monday_tools + mcp_tools,
            "knowledge": ["search", "datetime"] + monday_tools + mcp_tools,
            "technical": ["calculator", "search"] + monday_tools + mcp_tools,
            "creative": ["search"] + monday_tools + mcp_tools,
            "project_manager": ["datetime", "search"] + monday_tools + mcp_tools
        }
        
        tool_names = tool_sets.get(agent_type, ["datetime"])
        available_tools = [self.tools[name] for name in tool_names if name in self.tools]
        
        logger.debug(f"Agent '{agent_type}'에 {len(available_tools)}개 도구 제공")
        return available_tools
    
    async def get_tools_for_agent_async(self, agent_type: str) -> List[BaseTool]:
        """비동기로 에이전트용 도구 가져오기 (MCP 도구 자동 로드)"""
        # MCP 도구가 로드되지 않았으면 로드 시도
        if not self.mcp_tools_loaded:
            await self.load_mcp_tools()
        
        return self.get_tools_for_agent(agent_type)
    
    def get_mcp_tools(self) -> List[BaseTool]:
        """MCP 도구만 반환"""
        return [tool for name, tool in self.tools.items() if name.startswith('mcp_')]
    
    def get_legacy_tools(self) -> List[BaseTool]:
        """기존 도구만 반환 (MCP 도구 제외)"""
        return [tool for name, tool in self.tools.items() if not name.startswith('mcp_')]
    
    def list_tools(self) -> Dict[str, str]:
        """List all available tools"""
        return {
            name: tool.description
            for name, tool in self.tools.items()
        }
    
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """카테고리별 도구 반환"""
        matching_tools = []
        
        for tool in self.tools.values():
            # MCP 도구인 경우 tool_info 확인
            if hasattr(tool, 'tool_info') and tool.tool_info:
                tool_category = tool.tool_info.get("category", "general")
                if tool_category == category:
                    matching_tools.append(tool)
            # 기존 도구인 경우 이름으로 카테고리 추정
            else:
                tool_name = getattr(tool, 'name', '').lower()
                if category == "math" and "calculator" in tool_name:
                    matching_tools.append(tool)
                elif category == "utility" and any(keyword in tool_name for keyword in ["datetime", "search"]):
                    matching_tools.append(tool)
                elif category == "project_management" and "monday" in tool_name:
                    matching_tools.append(tool)
        
        return matching_tools
    
    def get_tool_stats(self) -> Dict[str, Any]:
        """도구 통계 반환"""
        total_tools = len(self.tools)
        mcp_tools = len(self.get_mcp_tools())
        legacy_tools = len(self.get_legacy_tools())
        
        # 카테고리별 통계
        categories = {}
        for tool in self.tools.values():
            if hasattr(tool, 'tool_info') and tool.tool_info:
                category = tool.tool_info.get("category", "general")
                categories[category] = categories.get(category, 0) + 1
        
        return {
            "total_tools": total_tools,
            "mcp_tools": mcp_tools,
            "legacy_tools": legacy_tools,
            "mcp_tools_loaded": self.mcp_tools_loaded,
            "categories": categories
        }


# Global tool registry
tool_registry = ToolRegistry()