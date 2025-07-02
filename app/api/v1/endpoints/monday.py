"""Monday.com API endpoints"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import logger
from app.schemas.monday import (
    MondayCreateItemRequest,
    MondayUpdateItemRequest,
    MondayDeleteItemRequest,
    MondaySearchRequest,
    MondayBoardDetailsRequest,
    MondayProjectSummaryRequest,
    MondayResponse,
    MondayItemResponse,
    MondayBoardResponse,
    MondaySearchResponse,
    MondayProjectSummaryResponse
)
from app.mcp.monday_client import MondayClient
from app.api.v1.dependencies import get_current_user


router = APIRouter()


def get_monday_client() -> MondayClient:
    """Get Monday.com client instance"""
    if not settings.mcp_monday_enabled:
        raise HTTPException(status_code=503, detail="Monday.com integration is disabled")
    
    if not settings.monday_api_key:
        raise HTTPException(status_code=503, detail="Monday.com API key not configured")
    
    return MondayClient()


@router.get("/health")
async def monday_health():
    """Check Monday.com integration health"""
    try:
        if not settings.mcp_monday_enabled:
            return JSONResponse(
                status_code=503,
                content={"status": "disabled", "message": "Monday.com integration is disabled"}
            )
        
        if not settings.monday_api_key:
            return JSONResponse(
                status_code=503,
                content={"status": "misconfigured", "message": "Monday.com API key not configured"}
            )
        
        client = MondayClient()
        workspaces = client.get_workspaces()
        
        return {
            "status": "healthy",
            "message": "Monday.com integration is working",
            "workspaces_count": len(workspaces)
        }
        
    except Exception as e:
        logger.error(f"Monday.com health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "message": str(e)}
        )


@router.get("/workspaces")
async def get_workspaces(client: MondayClient = Depends(get_monday_client)):
    """Get all Monday.com workspaces"""
    try:
        workspaces = client.get_workspaces()
        return {
            "workspaces": workspaces,
            "total_count": len(workspaces)
        }
    except Exception as e:
        logger.error(f"Error fetching workspaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards")
async def get_boards(
    workspace_id: Optional[str] = None,
    client: MondayClient = Depends(get_monday_client)
):
    """Get all Monday.com boards"""
    try:
        boards = client.get_boards(workspace_id)
        return {
            "boards": boards,
            "total_count": len(boards)
        }
    except Exception as e:
        logger.error(f"Error fetching boards: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards/{board_id}/items")
async def get_board_items(
    board_id: str,
    limit: int = 50,
    client: MondayClient = Depends(get_monday_client)
):
    """Get items from a specific board"""
    try:
        items = client.get_board_items(board_id, limit)
        return {
            "items": items,
            "total_count": len(items),
            "board_id": board_id
        }
    except Exception as e:
        logger.error(f"Error fetching board items: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/project-summary", response_model=MondayProjectSummaryResponse)
async def get_project_summary(
    request: MondayProjectSummaryRequest,
    client: MondayClient = Depends(get_monday_client)
):
    """Get project summary"""
    try:
        summary = client.get_project_summary(request.board_id)
        
        if "error" in summary:
            return MondayProjectSummaryResponse(
                success=False,
                message="Failed to get project summary",
                error=summary["error"]
            )
        
        return MondayProjectSummaryResponse(
            success=True,
            message="Project summary retrieved successfully",
            summary=summary
        )
        
    except Exception as e:
        logger.error(f"Error getting project summary: {e}")
        return MondayProjectSummaryResponse(
            success=False,
            message="Failed to get project summary",
            error=str(e)
        )


@router.post("/items", response_model=MondayItemResponse)
async def create_item(
    request: MondayCreateItemRequest,
    client: MondayClient = Depends(get_monday_client)
):
    """Create a new Monday.com item"""
    try:
        # Prepare column values
        column_values = {}
        
        if request.description:
            column_values["text"] = request.description
        
        if request.status:
            column_values["status"] = {"label": request.status}
        
        if request.assignee:
            column_values["person"] = {"personsAndTeams": [{"id": request.assignee}]}
        
        if request.due_date:
            column_values["date4"] = {"date": request.due_date}
        
        result = client.create_item(
            board_id=request.board_id,
            item_name=request.item_name,
            column_values=column_values if column_values else None
        )
        
        if result and result.get('id'):
            return MondayItemResponse(
                success=True,
                message="Item created successfully",
                data=result
            )
        else:
            return MondayItemResponse(
                success=False,
                message="Failed to create item",
                error="No item data returned"
            )
            
    except Exception as e:
        logger.error(f"Error creating item: {e}")
        return MondayItemResponse(
            success=False,
            message="Failed to create item",
            error=str(e)
        )


@router.put("/items/{item_id}", response_model=MondayItemResponse)
async def update_item(
    item_id: str,
    request: MondayUpdateItemRequest,
    client: MondayClient = Depends(get_monday_client)
):
    """Update a Monday.com item"""
    try:
        column_values = {}
        
        if request.status:
            column_values["status"] = {"label": request.status}
        
        if request.description:
            column_values["text"] = request.description
        
        if request.assignee:
            column_values["person"] = {"personsAndTeams": [{"id": request.assignee}]}
        
        if request.due_date:
            column_values["date4"] = {"date": request.due_date}
        
        if not column_values:
            return MondayItemResponse(
                success=False,
                message="No update data provided",
                error="At least one field must be provided for update"
            )
        
        result = client.update_item(item_id, column_values)
        
        if result and result.get('id'):
            return MondayItemResponse(
                success=True,
                message="Item updated successfully",
                data=result
            )
        else:
            return MondayItemResponse(
                success=False,
                message="Failed to update item",
                error="No item data returned"
            )
            
    except Exception as e:
        logger.error(f"Error updating item: {e}")
        return MondayItemResponse(
            success=False,
            message="Failed to update item",
            error=str(e)
        )


@router.delete("/items/{item_id}", response_model=MondayResponse)
async def delete_item(
    item_id: str,
    client: MondayClient = Depends(get_monday_client)
):
    """Delete a Monday.com item"""
    try:
        result = client.delete_item(item_id)
        
        if result and result.get('id'):
            return MondayResponse(
                success=True,
                message=f"Item {item_id} deleted successfully",
                data=result
            )
        else:
            return MondayResponse(
                success=False,
                message="Failed to delete item",
                error="No deletion confirmation received"
            )
            
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        return MondayResponse(
            success=False,
            message="Failed to delete item",
            error=str(e)
        )


@router.post("/search", response_model=MondaySearchResponse)
async def search_items(
    request: MondaySearchRequest,
    client: MondayClient = Depends(get_monday_client)
):
    """Search Monday.com items"""
    try:
        results = client.search_items(request.query, request.board_ids)
        
        return MondaySearchResponse(
            success=True,
            message=f"Search completed for '{request.query}'",
            items=results,
            total_count=len(results)
        )
        
    except Exception as e:
        logger.error(f"Error searching items: {e}")
        return MondaySearchResponse(
            success=False,
            message="Search failed",
            error=str(e),
            items=[],
            total_count=0
        )


@router.get("/boards/{board_id}/details", response_model=MondayBoardResponse)
async def get_board_details(
    board_id: str,
    client: MondayClient = Depends(get_monday_client)
):
    """Get detailed information about a board"""
    try:
        # Get board info
        boards = client.get_boards()
        board = next((b for b in boards if b['id'] == board_id), None)
        
        if not board:
            return MondayBoardResponse(
                success=False,
                message="Board not found",
                error=f"Board with ID '{board_id}' not found"
            )
        
        # Get board items for statistics
        items = client.get_board_items(board_id)
        
        # Add item statistics to board data
        board['items'] = items
        board['items_count'] = len(items)
        
        # Calculate status distribution
        status_counts = {}
        for item in items:
            status = item.get('state', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        board['status_distribution'] = status_counts
        
        return MondayBoardResponse(
            success=True,
            message="Board details retrieved successfully",
            board=board
        )
        
    except Exception as e:
        logger.error(f"Error getting board details: {e}")
        return MondayBoardResponse(
            success=False,
            message="Failed to get board details",
            error=str(e)
        )