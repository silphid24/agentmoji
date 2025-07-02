"""Monday.com tools for MOJI agents"""

from typing import Optional, List
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.mcp.monday_client import MondayClient


class MondayProjectSummaryInput(BaseModel):
    """Input for Monday.com project summary tool"""
    board_id: Optional[str] = Field(default=None, description="Optional specific board ID to summarize")


class MondayCreateItemInput(BaseModel):
    """Input for Monday.com create item tool"""
    board_id: str = Field(description="Board ID to create item in")
    item_name: str = Field(description="Name of the new item")
    description: Optional[str] = Field(default=None, description="Description of the item")
    status: Optional[str] = Field(default=None, description="Status of the item")
    assignee: Optional[str] = Field(default=None, description="Assignee name or ID")
    due_date: Optional[str] = Field(default=None, description="Due date in YYYY-MM-DD format")


class MondayUpdateItemInput(BaseModel):
    """Input for Monday.com update item tool"""
    item_id: str = Field(description="ID of the item to update")
    status: Optional[str] = Field(default=None, description="New status")
    description: Optional[str] = Field(default=None, description="New description")
    assignee: Optional[str] = Field(default=None, description="New assignee")
    due_date: Optional[str] = Field(default=None, description="New due date in YYYY-MM-DD format")


class MondayDeleteItemInput(BaseModel):
    """Input for Monday.com delete item tool"""
    item_id: str = Field(description="ID of the item to delete")


class MondaySearchInput(BaseModel):
    """Input for Monday.com search tool"""
    query: str = Field(description="Search query text")
    board_ids: Optional[List[str]] = Field(default=None, description="Optional list of board IDs to search in")


class MondayBoardDetailsInput(BaseModel):
    """Input for Monday.com board details tool"""
    board_id: str = Field(description="ID of the board to get details for")


class MondayProjectSummaryTool(BaseTool):
    """Tool to get Monday.com project summary"""
    
    name: str = "monday_project_summary"
    description: str = "Get a comprehensive summary of Monday.com projects including boards, items count, status distribution, and recent updates"
    args_schema: type = MondayProjectSummaryInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(self, board_id: Optional[str] = None) -> str:
        """Get project summary"""
        try:
            monday_client = self._get_monday_client()
            summary = monday_client.get_project_summary(board_id)
            
            if "error" in summary:
                return f"❌ 오류 발생: {summary['error']}"
            
            # Format summary for better readability
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
            
        except Exception as e:
            logger.error(f"Error in Monday project summary tool: {e}")
            return f"❌ 프로젝트 요약을 가져오는 중 오류가 발생했습니다: {str(e)}"


class MondayCreateItemTool(BaseTool):
    """Tool to create Monday.com items"""
    
    name: str = "monday_create_item"
    description: str = "Create a new project item in Monday.com with optional description, status, assignee, and due date"
    args_schema: type = MondayCreateItemInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(
        self,
        board_id: str,
        item_name: str,
        description: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None
    ) -> str:
        """Create a new item"""
        try:
            # Prepare column values
            column_values = {}
            
            if description:
                column_values["text"] = description
            
            if status:
                column_values["status"] = {"label": status}
            
            if assignee:
                column_values["person"] = {"personsAndTeams": [{"id": assignee}]}
            
            if due_date:
                column_values["date4"] = {"date": due_date}
            
            monday_client = self._get_monday_client()
            result = monday_client.create_item(
                board_id=board_id,
                item_name=item_name,
                column_values=column_values if column_values else None
            )
            
            if result and result.get('id'):
                return f"✅ 새로운 프로젝트 아이템이 성공적으로 생성되었습니다!\n\n📝 **아이템 정보:**\n- ID: {result['id']}\n- 이름: {result['name']}\n- 생성일: {result.get('created_at', 'N/A')}"
            else:
                return "❌ 아이템 생성에 실패했습니다."
                
        except Exception as e:
            logger.error(f"Error creating Monday item: {e}")
            return f"❌ 프로젝트 아이템 생성 중 오류가 발생했습니다: {str(e)}"


class MondayUpdateItemTool(BaseTool):
    """Tool to update Monday.com items"""
    
    name: str = "monday_update_item"
    description: str = "Update an existing Monday.com project item with new status, description, assignee, or due date"
    args_schema: type = MondayUpdateItemInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(
        self,
        item_id: str,
        status: Optional[str] = None,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        due_date: Optional[str] = None
    ) -> str:
        """Update an existing item"""
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
            
            monday_client = self._get_monday_client()
            result = monday_client.update_item(item_id, column_values)
            
            if result and result.get('id'):
                return f"✅ 프로젝트 아이템이 성공적으로 업데이트되었습니다!\n\n📝 **업데이트된 아이템:**\n- ID: {result['id']}\n- 이름: {result['name']}\n- 수정일: {result.get('updated_at', 'N/A')}"
            else:
                return "❌ 아이템 업데이트에 실패했습니다."
                
        except Exception as e:
            logger.error(f"Error updating Monday item: {e}")
            return f"❌ 프로젝트 아이템 업데이트 중 오류가 발생했습니다: {str(e)}"


class MondayDeleteItemTool(BaseTool):
    """Tool to delete Monday.com items"""
    
    name: str = "monday_delete_item"
    description: str = "Delete a Monday.com project item by ID"
    args_schema: type = MondayDeleteItemInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(self, item_id: str) -> str:
        """Delete an item"""
        try:
            monday_client = self._get_monday_client()
            result = monday_client.delete_item(item_id)
            
            if result and result.get('id'):
                return f"✅ 프로젝트 아이템 (ID: {result['id']})이 성공적으로 삭제되었습니다."
            else:
                return "❌ 아이템 삭제에 실패했습니다."
                
        except Exception as e:
            logger.error(f"Error deleting Monday item: {e}")
            return f"❌ 프로젝트 아이템 삭제 중 오류가 발생했습니다: {str(e)}"


class MondaySearchTool(BaseTool):
    """Tool to search Monday.com items"""
    
    name: str = "monday_search"
    description: str = "Search for Monday.com project items across boards"
    args_schema: type = MondaySearchInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(self, query: str, board_ids: Optional[List[str]] = None) -> str:
        """Search for items"""
        try:
            monday_client = self._get_monday_client()
            results = monday_client.search_items(query, board_ids)
            
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
            logger.error(f"Error searching Monday items: {e}")
            return f"❌ 프로젝트 검색 중 오류가 발생했습니다: {str(e)}"


class MondayBoardDetailsTool(BaseTool):
    """Tool to get Monday.com board details"""
    
    name: str = "monday_board_details"
    description: str = "Get detailed information about a specific Monday.com board including items and statistics"
    args_schema: type = MondayBoardDetailsInput
    
    def __init__(self):
        super().__init__()
    
    def _get_monday_client(self):
        """Get Monday.com client instance"""
        return MondayClient()
    
    def _run(self, board_id: str) -> str:
        """Get board details"""
        try:
            # Get board info
            monday_client = self._get_monday_client()
            boards = monday_client.get_boards()
            board = next((b for b in boards if b['id'] == board_id), None)
            
            if not board:
                return f"❌ 보드 ID '{board_id}'를 찾을 수 없습니다."
            
            # Get board items
            items = monday_client.get_board_items(board_id)
            
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
            logger.error(f"Error getting Monday board details: {e}")
            return f"❌ 보드 상세 정보 조회 중 오류가 발생했습니다: {str(e)}"