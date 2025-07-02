#!/usr/bin/env python3
"""
Simple WebSocket test for basic functionality
"""

import asyncio
import websockets
import json

async def test_simple_chat():
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
            
            # Test basic chat
            messages = [
                "안녕하세요",
                "날씨는 어떤가요?",
                "계산기를 써서 2+2를 계산해주세요",
                "오늘 날짜를 알려주세요"
            ]
            
            for msg in messages:
                test_message = {
                    "type": "text",
                    "text": msg,
                    "timestamp": "2025-07-02T19:45:00Z"
                }
                await websocket.send(json.dumps(test_message))
                print(f"Sent: {msg}")
                
                # Wait for response
                response = await websocket.recv()
                response_data = json.loads(response)
                print(f"Response: {response_data['text']}")
                print("---")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_simple_chat())