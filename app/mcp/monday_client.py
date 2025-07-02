"""Monday.com API client for GraphQL operations"""

import json
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.core.config import settings
from app.core.logging import logger


class MondayClient:
    """Monday.com GraphQL API client"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.monday_api_key
        self.api_url = "https://api.monday.com/v2"
        self.headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        
        if not self.api_key:
            logger.warning("Monday.com API key not provided")
    
    def _execute_query(self, query: str, variables: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute GraphQL query"""
        try:
            payload = {
                "query": query,
                "variables": variables or {}
            }
            
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "errors" in result:
                logger.error(f"Monday.com API errors: {result['errors']}")
                raise Exception(f"API Error: {result['errors']}")
            
            return result.get("data", {})
            
        except requests.RequestException as e:
            logger.error(f"Monday.com API request failed: {e}")
            raise Exception(f"API Request Failed: {str(e)}")
        except Exception as e:
            logger.error(f"Monday.com API error: {e}")
            raise
    
    def get_boards(self, workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all boards in workspace"""
        query = """
        query GetBoards($workspace_id: ID) {
            boards(workspace_ids: [$workspace_id]) {
                id
                name
                description
                state
                board_folder_id
                board_kind
                creator {
                    id
                    name
                    email
                }
                owners {
                    id
                    name
                    email
                }
                updated_at
                items_count
                columns {
                    id
                    title
                    type
                    settings_str
                }
            }
        }
        """
        
        variables = {}
        if workspace_id:
            variables["workspace_id"] = workspace_id
        
        result = self._execute_query(query, variables)
        return result.get("boards", [])
    
    def get_board_items(self, board_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get items from a specific board"""
        query = """
        query GetBoardItems($board_id: ID!, $limit: Int) {
            boards(ids: [$board_id]) {
                items_page(limit: $limit) {
                    cursor
                    items {
                        id
                        name
                        state
                        created_at
                        updated_at
                        creator {
                            id
                            name
                            email
                        }
                        column_values {
                            id
                            title
                            text
                            value
                            type
                        }
                        subitems {
                            id
                            name
                            column_values {
                                id
                                title
                                text
                                value
                            }
                        }
                    }
                }
            }
        }
        """
        
        variables = {
            "board_id": board_id,
            "limit": limit
        }
        
        result = self._execute_query(query, variables)
        boards = result.get("boards", [])
        if boards:
            return boards[0].get("items_page", {}).get("items", [])
        return []
    
    def create_item(self, board_id: str, item_name: str, column_values: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a new item in a board"""
        query = """
        mutation CreateItem($board_id: ID!, $item_name: String!, $column_values: JSON) {
            create_item(
                board_id: $board_id,
                item_name: $item_name,
                column_values: $column_values
            ) {
                id
                name
                state
                created_at
                creator {
                    id
                    name
                    email
                }
                column_values {
                    id
                    title
                    text
                    value
                }
            }
        }
        """
        
        variables = {
            "board_id": board_id,
            "item_name": item_name,
            "column_values": json.dumps(column_values) if column_values else None
        }
        
        result = self._execute_query(query, variables)
        return result.get("create_item", {})
    
    def update_item(self, item_id: str, column_values: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing item"""
        query = """
        mutation UpdateItem($item_id: ID!, $column_values: JSON!) {
            change_multiple_column_values(
                item_id: $item_id,
                board_id: null,
                column_values: $column_values
            ) {
                id
                name
                state
                updated_at
                column_values {
                    id
                    title
                    text
                    value
                }
            }
        }
        """
        
        variables = {
            "item_id": item_id,
            "column_values": json.dumps(column_values)
        }
        
        result = self._execute_query(query, variables)
        return result.get("change_multiple_column_values", {})
    
    def delete_item(self, item_id: str) -> Dict[str, Any]:
        """Delete an item"""
        query = """
        mutation DeleteItem($item_id: ID!) {
            delete_item(item_id: $item_id) {
                id
            }
        }
        """
        
        variables = {"item_id": item_id}
        
        result = self._execute_query(query, variables)
        return result.get("delete_item", {})
    
    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Get all workspaces"""
        query = """
        query {
            workspaces {
                id
                name
            }
        }
        """
        
        result = self._execute_query(query)
        return result.get("workspaces", [])
    
    def search_items(self, query_text: str, board_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for items across boards"""
        query = """
        query SearchItems($query: String!, $board_ids: [ID]) {
            items_page_by_column_values(
                query: $query,
                board_ids: $board_ids,
                limit: 50
            ) {
                cursor
                items {
                    id
                    name
                    state
                    board {
                        id
                        name
                    }
                    column_values {
                        id
                        title
                        text
                        value
                    }
                    created_at
                    updated_at
                }
            }
        }
        """
        
        variables = {
            "query": query_text,
            "board_ids": board_ids
        }
        
        result = self._execute_query(query, variables)
        return result.get("items_page_by_column_values", {}).get("items", [])
    
    def get_project_summary(self, board_id: Optional[str] = None) -> Dict[str, Any]:
        """Get project summary with statistics"""
        try:
            # Get boards (specific board or all boards)
            if board_id:
                boards = [board for board in self.get_boards() if board["id"] == board_id]
            else:
                boards = self.get_boards()
            
            if not boards:
                return {"error": "No boards found"}
            
            summary = {
                "total_boards": len(boards),
                "boards": [],
                "total_items": 0,
                "status_distribution": {},
                "recent_updates": []
            }
            
            for board in boards[:10]:  # Limit to 10 boards for performance
                items = self.get_board_items(board["id"], limit=100)
                
                board_summary = {
                    "id": board["id"],
                    "name": board["name"],
                    "description": board.get("description", ""),
                    "items_count": len(items),
                    "last_updated": board.get("updated_at"),
                    "status_counts": {}
                }
                
                # Count status distribution
                for item in items:
                    status = item.get("state", "unknown")
                    board_summary["status_counts"][status] = board_summary["status_counts"].get(status, 0) + 1
                    summary["status_distribution"][status] = summary["status_distribution"].get(status, 0) + 1
                
                summary["boards"].append(board_summary)
                summary["total_items"] += len(items)
                
                # Add recent items to recent updates
                for item in items[:3]:  # Get 3 most recent items per board
                    if item.get("updated_at"):
                        summary["recent_updates"].append({
                            "board_name": board["name"],
                            "item_name": item["name"],
                            "updated_at": item["updated_at"],
                            "status": item.get("state", "unknown")
                        })
            
            # Sort recent updates by date
            summary["recent_updates"].sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            summary["recent_updates"] = summary["recent_updates"][:10]  # Keep only 10 most recent
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting project summary: {e}")
            return {"error": str(e)}