"""Agent tools for enhanced capabilities"""

from typing import Optional, Dict, Any
from langchain.tools import Tool, BaseTool
from pydantic import BaseModel, Field
import json
import re
from datetime import datetime

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
    """Registry for managing agent tools"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._load_default_tools()
    
    def _load_default_tools(self):
        """Load default tools"""
        for tool_name, tool in AVAILABLE_TOOLS.items():
            self.register_tool(tool_name, tool)
    
    def register_tool(self, name: str, tool: BaseTool):
        """Register a new tool"""
        self.tools[name] = tool
        logger.info(f"Registered tool: {name}")
    
    def unregister_tool(self, name: str):
        """Unregister a tool"""
        if name in self.tools:
            del self.tools[name]
            logger.info(f"Unregistered tool: {name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get tool by name"""
        return self.tools.get(name)
    
    def get_tools_for_agent(self, agent_type: str) -> list[BaseTool]:
        """Get appropriate tools for agent type"""
        # Define tool sets for different agent types
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
        
        tool_sets = {
            "general": ["calculator", "datetime"] + monday_tools,
            "task": ["calculator", "datetime", "search"] + monday_tools,
            "knowledge": ["search", "datetime"] + monday_tools,
            "technical": ["calculator", "search"] + monday_tools,
            "creative": ["search"] + monday_tools,
            "project_manager": ["datetime", "search"] + monday_tools  # New agent type for project management
        }
        
        tool_names = tool_sets.get(agent_type, ["datetime"])
        return [self.tools[name] for name in tool_names if name in self.tools]
    
    def list_tools(self) -> Dict[str, str]:
        """List all available tools"""
        return {
            name: tool.description
            for name, tool in self.tools.items()
        }


# Global tool registry
tool_registry = ToolRegistry()