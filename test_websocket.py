#!/usr/bin/env python3
"""
Simple WebSocket test for MOJI WebChat
"""

import asyncio
import websockets
import json

async def test_webchat():
    uri = "ws://localhost:8000/api/v1/adapters/webchat/ws"
    
    try:
        print("Connecting to WebSocket...")
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            # Send authentication
            auth_message = {
                "user_id": "test_user",
                "user_name": "Test User"
            }
            await websocket.send(json.dumps(auth_message))
            print("Sent auth message")
            
            # Wait for welcome message
            response = await websocket.recv()
            print(f"Received: {response}")
            
            # Send test message
            test_message = {
                "type": "text",
                "text": "안녕하세요",
                "timestamp": "2025-07-02T19:45:00Z"
            }
            await websocket.send(json.dumps(test_message))
            print("Sent test message: 안녕하세요")
            
            # Wait for response
            response = await websocket.recv()
            print(f"Received response: {response}")
            
            # Send Monday.com test message
            monday_message = {
                "type": "text", 
                "text": "프로젝트 현황을 알려주세요",
                "timestamp": "2025-07-02T19:45:10Z"
            }
            await websocket.send(json.dumps(monday_message))
            print("Sent Monday.com message: 프로젝트 현황을 알려주세요")
            
            # Wait for Monday.com response
            response = await websocket.recv()
            print(f"Received Monday.com response: {response}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_webchat())