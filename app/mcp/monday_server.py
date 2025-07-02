"""Monday.com MCP Server implementation"""

import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.models import InitializationOptions
from mcp.types import Resource, Tool, Prompt

from app.core.config import settings
from app.core.logging import logger
from .monday_client import MondayClient


class MondayMCPServer:
    """Monday.com Model Context Protocol Server"""
    
    def __init__(self):
        self.app = FastMCP("Monday.com MCP Server")
        self.monday_client = MondayClient()
        self._setup_resources()
        self._setup_tools()
        self._setup_prompts()
        
        logger.info("Monday.com MCP Server initialized")
    
    def _setup_resources(self):
        """Setup MCP resources for Monday.com data"""
        
        @self.app.resource("monday://boards")
        async def get_boards_resource() -> str:
            """Get all boards as a resource"""
            try:
                boards = self.monday_client.get_boards()
                return json.dumps({
                    "boards": boards,
                    "total_count": len(boards),
                    "fetched_at": datetime.now().isoformat()
                }, indent=2)
            except Exception as e:
                logger.error(f"Error fetching boards resource: {e}")
                return json.dumps({"error": str(e)})
        
        @self.app.resource("monday://workspaces")
        async def get_workspaces_resource() -> str:
            """Get all workspaces as a resource"""
            try:
                workspaces = self.monday_client.get_workspaces()
                return json.dumps({
                    "workspaces": workspaces,
                    "total_count": len(workspaces),
                    "fetched_at": datetime.now().isoformat()
                }, indent=2)
            except Exception as e:
                logger.error(f"Error fetching workspaces resource: {e}")
                return json.dumps({"error": str(e)})
        
        @self.app.resource("monday://project-summary")
        async def get_project_summary_resource() -> str:
            """Get project summary as a resource"""
            try:
                summary = self.monday_client.get_project_summary()
                return json.dumps(summary, indent=2)
            except Exception as e:
                logger.error(f"Error fetching project summary: {e}")
                return json.dumps({"error": str(e)})
    
    def _setup_tools(self):
        """Setup MCP tools for Monday.com operations"""
        
        @self.app.tool()
        async def get_project_summary(board_id: Optional[str] = None) -> str:
            """
            Get a comprehensive summary of projects
            
            Args:
                board_id: Optional specific board ID to summarize. If not provided, summarizes all boards.
            
            Returns:
                JSON string with project summary including boards, items count, status distribution, and recent updates
            """
            try:
                summary = self.monday_client.get_project_summary(board_id)
                
                # Format summary for better readability
                if "error" not in summary:
                    readable_summary = f"""
📊 **프로젝트 요약**

**전체 현황:**
- 총 보드 수: {summary.get('total_boards', 0)}개
- 총 아이템 수: {summary.get('total_items', 0)}개

**상태별 분포:**
"""
                    for status, count in summary.get('status_distribution', {}).items():
                        readable_summary += f"- {status}: {count}개\n"
                    
                    readable_summary += "\n**보드별 현황:**\n"
                    for board in summary.get('boards', [])[:5]:  # Show top 5 boards
                        readable_summary += f"- {board['name']}: {board['items_count']}개 아이템\n"
                    
                    if summary.get('recent_updates'):
                        readable_summary += "\n**최근 업데이트:**\n"
                        for update in summary.get('recent_updates', [])[:3]:
                            readable_summary += f"- {update['board_name']}: {update['item_name']} ({update['status']})\n"
                    
                    return readable_summary
                else:
                    return f"❌ 오류 발생: {summary.get('error', '알 수 없는 오류')}"
                    
            except Exception as e:
                logger.error(f"Error in get_project_summary tool: {e}")
                return f"❌ 프로젝트 요약을 가져오는 중 오류가 발생했습니다: {str(e)}"
        
        @self.app.tool()
        async def create_project_item(
            board_id: str,
            item_name: str,
            description: Optional[str] = None,
            status: Optional[str] = None,
            assignee: Optional[str] = None,
            due_date: Optional[str] = None
        ) -> str:
            """
            Create a new project item in Monday.com
            
            Args:
                board_id: The ID of the board to create the item in
                item_name: Name of the new item
                description: Optional description for the item
                status: Optional status value
                assignee: Optional assignee name or ID
                due_date: Optional due date in YYYY-MM-DD format
            
            Returns:
                Success message with item details or error message
            """
            try:
                # Prepare column values
                column_values = {}
                
                if description:
                    # Assuming there's a text column for description
                    column_values["text"] = description
                
                if status:
                    # Assuming there's a status column
                    column_values["status"] = {"label": status}
                
                if assignee:
                    # Assuming there's a person column
                    column_values["person"] = {"personsAndTeams": [{"id": assignee}]}
                
                if due_date:
                    # Assuming there's a date column
                    column_values["date4"] = {"date": due_date}
                
                result = self.monday_client.create_item(
                    board_id=board_id,
                    item_name=item_name,
                    column_values=column_values if column_values else None
                )
                
                if result and result.get('id'):
                    return f"✅ 새로운 프로젝트 아이템이 성공적으로 생성되었습니다!\n\n📝 **아이템 정보:**\n- ID: {result['id']}\n- 이름: {result['name']}\n- 생성일: {result.get('created_at', 'N/A')}"
                else:
                    return "❌ 아이템 생성에 실패했습니다."
                    
            except Exception as e:
                logger.error(f"Error creating project item: {e}")
                return f"❌ 프로젝트 아이템 생성 중 오류가 발생했습니다: {str(e)}"
        
        @self.app.tool()
        async def update_project_item(
            item_id: str,
            status: Optional[str] = None,
            description: Optional[str] = None,
            assignee: Optional[str] = None,
            due_date: Optional[str] = None
        ) -> str:
            """
            Update an existing project item
            
            Args:
                item_id: The ID of the item to update
                status: Optional new status
                description: Optional new description
                assignee: Optional new assignee
                due_date: Optional new due date in YYYY-MM-DD format
            
            Returns:
                Success message with updated details or error message
            """
            try:
                column_values = {}
                
                if status:
                    column_values["status"] = {"label": status}
                
                if description:
                    column_values["text"] = description
                
                if assignee:
                    column_values["person"] = {"personsAndTeams": [{"id": assignee}]}
                
                if due_date:
                    column_values["date4"] = {"date": due_date}
                
                if not column_values:
                    return "❌ 업데이트할 내용이 없습니다."
                
                result = self.monday_client.update_item(item_id, column_values)
                
                if result and result.get('id'):
                    return f"✅ 프로젝트 아이템이 성공적으로 업데이트되었습니다!\n\n📝 **업데이트된 아이템:**\n- ID: {result['id']}\n- 이름: {result['name']}\n- 수정일: {result.get('updated_at', 'N/A')}"
                else:
                    return "❌ 아이템 업데이트에 실패했습니다."
                    
            except Exception as e:
                logger.error(f"Error updating project item: {e}")
                return f"❌ 프로젝트 아이템 업데이트 중 오류가 발생했습니다: {str(e)}"
        
        @self.app.tool()
        async def delete_project_item(item_id: str) -> str:
            """
            Delete a project item
            
            Args:
                item_id: The ID of the item to delete
            
            Returns:
                Success or error message
            """
            try:
                result = self.monday_client.delete_item(item_id)
                
                if result and result.get('id'):
                    return f"✅ 프로젝트 아이템 (ID: {result['id']})이 성공적으로 삭제되었습니다."
                else:
                    return "❌ 아이템 삭제에 실패했습니다."
                    
            except Exception as e:
                logger.error(f"Error deleting project item: {e}")
                return f"❌ 프로젝트 아이템 삭제 중 오류가 발생했습니다: {str(e)}"
        
        @self.app.tool()
        async def search_projects(query: str, board_ids: Optional[List[str]] = None) -> str:
            """
            Search for project items
            
            Args:
                query: Search query text
                board_ids: Optional list of board IDs to search in
            
            Returns:
                Formatted search results
            """
            try:
                results = self.monday_client.search_items(query, board_ids)
                
                if not results:
                    return f"🔍 '{query}' 검색 결과가 없습니다."
                
                search_summary = f"🔍 **'{query}' 검색 결과** ({len(results)}개 항목)\n\n"
                
                for item in results[:10]:  # Limit to 10 results
                    board_name = item.get('board', {}).get('name', 'Unknown Board')
                    search_summary += f"📋 **{item['name']}**\n"
                    search_summary += f"   보드: {board_name}\n"
                    search_summary += f"   상태: {item.get('state', 'N/A')}\n"
                    search_summary += f"   ID: {item['id']}\n\n"
                
                return search_summary
                
            except Exception as e:
                logger.error(f"Error searching projects: {e}")
                return f"❌ 프로젝트 검색 중 오류가 발생했습니다: {str(e)}"
        
        @self.app.tool()
        async def get_board_details(board_id: str) -> str:
            """
            Get detailed information about a specific board
            
            Args:
                board_id: The ID of the board
            
            Returns:
                Detailed board information
            """
            try:
                # Get board info
                boards = self.monday_client.get_boards()
                board = next((b for b in boards if b['id'] == board_id), None)
                
                if not board:
                    return f"❌ 보드 ID '{board_id}'를 찾을 수 없습니다."
                
                # Get board items
                items = self.monday_client.get_board_items(board_id)
                
                details = f"📋 **보드 상세 정보**\n\n"
                details += f"**이름:** {board['name']}\n"
                details += f"**설명:** {board.get('description', 'N/A')}\n"
                details += f"**상태:** {board.get('state', 'N/A')}\n"
                details += f"**아이템 수:** {len(items)}개\n"
                
                if board.get('owners'):
                    owners = [owner['name'] for owner in board['owners']]
                    details += f"**소유자:** {', '.join(owners)}\n"
                
                # Status distribution
                status_counts = {}
                for item in items:
                    status = item.get('state', 'unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                if status_counts:
                    details += f"\n**상태별 분포:**\n"
                    for status, count in status_counts.items():
                        details += f"- {status}: {count}개\n"
                
                # Recent items
                if items:
                    details += f"\n**최근 아이템들:**\n"
                    for item in items[:5]:
                        details += f"- {item['name']} ({item.get('state', 'N/A')})\n"
                
                return details
                
            except Exception as e:
                logger.error(f"Error getting board details: {e}")
                return f"❌ 보드 상세 정보 조회 중 오류가 발생했습니다: {str(e)}"
    
    def _setup_prompts(self):
        """Setup MCP prompts for Monday.com operations"""
        
        @self.app.prompt()
        async def project_management_prompt() -> str:
            """Create a project management assistant prompt"""
            return """You are a helpful project management assistant integrated with Monday.com. 
            
You can help users with:
- 📊 Get project summaries and status updates
- 📝 Create new project items and tasks
- ✏️ Update existing project items
- 🗑️ Delete project items
- 🔍 Search for specific projects or tasks
- 📋 Get detailed board information

Always provide clear, actionable responses in Korean and use emojis to make the information more readable.
When creating or updating items, ask for clarification if important details are missing.
"""
        
        @self.app.prompt()
        async def project_creation_prompt() -> str:
            """Create a prompt for project creation guidance"""
            return """프로젝트 생성 도우미입니다. 새로운 프로젝트를 만들 때 다음 정보를 제공해주세요:

필수 정보:
- 📝 프로젝트 이름
- 📋 어떤 보드에 생성할지

선택 정보:
- 📄 프로젝트 설명
- 🎯 상태 (예: "진행중", "완료", "대기")
- 👤 담당자
- 📅 마감일 (YYYY-MM-DD 형식)

예시: "웹사이트 리뉴얼 프로젝트를 개발 보드에 만들어주세요. 담당자는 김개발이고 마감일은 2024-03-15입니다."
"""
    
    def get_app(self):
        """Get the FastMCP app instance"""
        return self.app
    
    async def run(self, host: str = "localhost", port: int = 3001):
        """Run the MCP server"""
        try:
            logger.info(f"Starting Monday.com MCP server on {host}:{port}")
            await self.app.run(host=host, port=port)
        except Exception as e:
            logger.error(f"Error running MCP server: {e}")
            raise


# Global instance
monday_mcp_server = MondayMCPServer()