"""Monday.com data schemas"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class MondayUser(BaseModel):
    """Monday.com user schema"""
    id: str
    name: str
    email: Optional[str] = None


class MondayColumn(BaseModel):
    """Monday.com column schema"""
    id: str
    title: str
    type: str
    settings_str: Optional[str] = None


class MondayColumnValue(BaseModel):
    """Monday.com column value schema"""
    id: str
    title: str
    text: Optional[str] = None
    value: Optional[str] = None
    type: Optional[str] = None


class MondaySubitem(BaseModel):
    """Monday.com subitem schema"""
    id: str
    name: str
    column_values: List[MondayColumnValue] = []


class MondayItem(BaseModel):
    """Monday.com item schema"""
    id: str
    name: str
    state: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    creator: Optional[MondayUser] = None
    column_values: List[MondayColumnValue] = []
    subitems: List[MondaySubitem] = []


class MondayBoard(BaseModel):
    """Monday.com board schema"""
    id: str
    name: str
    description: Optional[str] = None
    state: Optional[str] = None
    board_folder_id: Optional[str] = None
    board_kind: Optional[str] = None
    creator: Optional[MondayUser] = None
    owners: List[MondayUser] = []
    updated_at: Optional[str] = None
    items_count: Optional[int] = None
    columns: List[MondayColumn] = []


class MondayWorkspace(BaseModel):
    """Monday.com workspace schema"""
    id: str
    name: str
    description: Optional[str] = None
    state: Optional[str] = None
    created_at: Optional[str] = None
    owners: List[MondayUser] = []


class MondayProjectSummary(BaseModel):
    """Monday.com project summary schema"""
    total_boards: int = 0
    total_items: int = 0
    boards: List[Dict[str, Any]] = []
    status_distribution: Dict[str, int] = {}
    recent_updates: List[Dict[str, Any]] = []


class MondayCreateItemRequest(BaseModel):
    """Request schema for creating Monday.com items"""
    board_id: str = Field(description="Board ID to create item in")
    item_name: str = Field(description="Name of the new item")
    description: Optional[str] = Field(default=None, description="Description of the item")
    status: Optional[str] = Field(default=None, description="Status of the item")
    assignee: Optional[str] = Field(default=None, description="Assignee name or ID")
    due_date: Optional[str] = Field(default=None, description="Due date in YYYY-MM-DD format")


class MondayUpdateItemRequest(BaseModel):
    """Request schema for updating Monday.com items"""
    item_id: str = Field(description="ID of the item to update")
    status: Optional[str] = Field(default=None, description="New status")
    description: Optional[str] = Field(default=None, description="New description")
    assignee: Optional[str] = Field(default=None, description="New assignee")
    due_date: Optional[str] = Field(default=None, description="New due date in YYYY-MM-DD format")


class MondayDeleteItemRequest(BaseModel):
    """Request schema for deleting Monday.com items"""
    item_id: str = Field(description="ID of the item to delete")


class MondaySearchRequest(BaseModel):
    """Request schema for searching Monday.com items"""
    query: str = Field(description="Search query text")
    board_ids: Optional[List[str]] = Field(default=None, description="Optional list of board IDs to search in")


class MondayBoardDetailsRequest(BaseModel):
    """Request schema for getting Monday.com board details"""
    board_id: str = Field(description="ID of the board to get details for")


class MondayProjectSummaryRequest(BaseModel):
    """Request schema for getting Monday.com project summary"""
    board_id: Optional[str] = Field(default=None, description="Optional specific board ID to summarize")


class MondayResponse(BaseModel):
    """Base response schema for Monday.com operations"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class MondayItemResponse(MondayResponse):
    """Response schema for Monday.com item operations"""
    item: Optional[MondayItem] = None


class MondayBoardResponse(MondayResponse):
    """Response schema for Monday.com board operations"""
    board: Optional[MondayBoard] = None


class MondaySearchResponse(MondayResponse):
    """Response schema for Monday.com search operations"""
    items: List[MondayItem] = []
    total_count: int = 0


class MondayProjectSummaryResponse(MondayResponse):
    """Response schema for Monday.com project summary"""
    summary: Optional[MondayProjectSummary] = None