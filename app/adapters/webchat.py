"""Web Chat adapter implementation with WebSocket support."""

import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

import aiohttp
from aiohttp import web
from fastapi import WebSocket, WebSocketDisconnect

from .base import (
    BaseAdapter,
    PlatformMessage,
    MessageType,
    User,
    Conversation,
    Attachment,
    Button,
    Card,
    AttachmentType,
)


class WebChatConnection:
    """Represents a WebChat connection."""
    
    def __init__(self, websocket: WebSocket, user_id: str, session_id: str):
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = session_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
    
    async def send(self, data: Dict[str, Any]) -> None:
        """Send data through WebSocket."""
        await self.websocket.send_json(data)
        self.last_activity = datetime.utcnow()


class WebChatAdapter(BaseAdapter):
    """Web Chat adapter for embedded widget."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize WebChat adapter."""
        super().__init__(config)
        self.connections: Dict[str, WebChatConnection] = {}
        self.conversations: Dict[str, Conversation] = {}
        self.widget_config = config.get("widget", {})
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> None:
        """Start WebChat service."""
        # Start connection cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_inactive_connections())
    
    async def disconnect(self) -> None:
        """Stop WebChat service."""
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for conn in list(self.connections.values()):
            await conn.websocket.close()
        
        self.connections.clear()
        self.conversations.clear()
    
    async def handle_websocket(self, websocket: WebSocket, session_id: Optional[str] = None) -> None:
        """Handle incoming WebSocket connection."""
        await websocket.accept()
        
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Wait for authentication message
        try:
            auth_data = await websocket.receive_json()
            user_id = auth_data.get("user_id", f"guest_{uuid.uuid4().hex[:8]}")
            user_name = auth_data.get("user_name", "Guest User")
        except Exception:
            user_id = f"guest_{uuid.uuid4().hex[:8]}"
            user_name = "Guest User"
        
        # Create connection
        connection = WebChatConnection(websocket, user_id, session_id)
        self.connections[session_id] = connection
        
        # Create or get conversation
        if session_id not in self.conversations:
            self.conversations[session_id] = Conversation(
                id=session_id,
                platform="webchat",
                type="direct",
                name=f"Chat with {user_name}",
                metadata={"started_at": datetime.utcnow().isoformat()},
            )
        
        # Send welcome message
        print(f"[WebChat] Sending welcome message to {user_id}")
        await self._send_system_message(
            connection,
            "Welcome to MOJI Web Chat! How can I help you today?"
        )
        print(f"[WebChat] Welcome message sent")
        
        try:
            # Handle incoming messages
            while True:
                data = await websocket.receive_json()
                message = await self._process_incoming_message(data, connection)
                
                # Process message with conversation agent
                if message.text and message.text.strip():
                    try:
                        print(f"[WebChat] Processing message: {message.text}")
                        # Process with conversation agent if available
                        if hasattr(self, 'conversation_agent') and self.conversation_agent:
                            print(f"[WebChat] Using conversation agent")
                            try:
                                response_message = await self.conversation_agent.process_message(message)
                                print(f"[WebChat] Agent response: {response_message}")
                                if response_message and response_message.text:
                                    print(f"[WebChat] Sending response: {response_message.text}")
                                    await connection.send({
                                        "id": str(uuid.uuid4()),
                                        "type": "text",
                                        "text": response_message.text,
                                        "timestamp": datetime.utcnow().isoformat(),
                                    })
                                    continue
                                else:
                                    print(f"[WebChat] No valid response from agent")
                            except Exception as agent_error:
                                print(f"[WebChat] Conversation agent error: {agent_error}")
                                import traceback
                                traceback.print_exc()
                                # Continue to fallback processing
                        else:
                            print(f"[WebChat] No conversation agent available")
                        
                        # Fallback to direct processing
                        # Check for RAG commands
                        if message.text.startswith("/rag "):
                            # Handle RAG queries
                            from app.rag.enhanced_rag import rag_pipeline
                            
                            query = message.text[5:].strip()  # Remove "/rag " prefix
                            print(f"[WebChat] RAG query: {query}")
                            
                            # Get answer with confidence
                            result = await rag_pipeline.answer_with_confidence(query)
                            
                            # Format response
                            response_text = f"**답변**: {result['answer']}\n\n"
                            response_text += f"**신뢰도**: {result['confidence']}\n"
                            response_text += f"**근거**: {result['reasoning']}\n"
                            
                            if result['sources']:
                                response_text += f"\n**출처**:\n"
                                for source in result['sources']:
                                    response_text += f"- {source}\n"
                            
                            await connection.send({
                                "id": str(uuid.uuid4()),
                                "type": "text",
                                "text": response_text,
                                "timestamp": datetime.utcnow().isoformat(),
                            })
                        
                        elif message.text == "/rag-stats":
                            # Show RAG statistics
                            from app.rag.enhanced_rag import rag_pipeline
                            
                            stats = rag_pipeline.get_collection_stats()
                            response_text = f"**RAG 시스템 통계**\n"
                            response_text += f"- 총 문서 수: {stats.get('total_documents', 0)}\n"
                            response_text += f"- 청크 크기: {stats.get('chunk_size', 0)}\n"
                            response_text += f"- 청크 오버랩: {stats.get('chunk_overlap', 0)}\n"
                            response_text += f"- 임베딩 모델: {stats.get('embedding_model', 'Unknown')}\n"
                            
                            await connection.send({
                                "id": str(uuid.uuid4()),
                                "type": "text",
                                "text": response_text,
                                "timestamp": datetime.utcnow().isoformat(),
                            })
                        
                        elif message.text == "/rag-help":
                            # Show RAG help
                            help_text = """**RAG 시스템 사용법**

1. **문서 업로드**: API를 통해 문서를 업로드하세요
   - 지원 형식: .txt, .md, .docx

2. **질문하기**: `/rag [질문]`
   예시: `/rag 프로젝트의 주요 목표는 무엇인가요?`

3. **통계 보기**: `/rag-stats`
   현재 저장된 문서 수와 설정을 확인합니다.

4. **일반 대화**: 일반 메시지는 ChatGPT가 답변합니다.

**특징**:
- 질의 재작성으로 검색 정확도 향상
- 신뢰도 점수 제공 (HIGH/MEDIUM/LOW)
- 답변 근거 및 출처 표시"""
                            
                            await connection.send({
                                "id": str(uuid.uuid4()),
                                "type": "text",
                                "text": help_text,
                                "timestamp": datetime.utcnow().isoformat(),
                            })
                        
                        else:
                            # Handle RAG selection logic
                            from app.rag.enhanced_rag import rag_pipeline
                            from app.llm.router import llm_router
                            from langchain_core.messages import HumanMessage
                            
                            # Log incoming message
                            print(f"[WebChat] Received message: {message.text}")
                            
                            # Check RAG setting from client
                            use_rag = data.get('useRag', True)  # Default to True for backward compatibility
                            provider = data.get('provider')
                            model = data.get('model')
                            
                            print(f"[WebChat] RAG setting: {use_rag}, Provider: {provider}, Model: {model}")
                            
                            try:
                                if use_rag:
                                    # Try Hybrid RAG first (improved search)
                                    print("[WebChat] Trying Hybrid RAG search...")
                                    from app.rag.enhanced_rag import get_hybrid_pipeline
                                    hybrid_pipeline = get_hybrid_pipeline()
                                    
                                    rag_result = await hybrid_pipeline.answer_with_hybrid_search(
                                        message.text, 
                                        k=5, 
                                        score_threshold=0.1  # Lower threshold for hybrid search
                                    )
                                    
                                    # Check if RAG found relevant documents
                                    if (rag_result.get('sources') and 
                                        len(rag_result.get('sources', [])) > 0 and
                                        rag_result.get('answer') and 
                                        '관련된 정보를 찾을 수 없습니다' not in rag_result.get('answer', '')):
                                        
                                        print("[WebChat] Using Hybrid RAG response")
                                        # Use Hybrid RAG response
                                        response_text = rag_result['answer']
                                        
                                        # Enhanced metadata with hybrid search info
                                        sources = rag_result.get('sources', [])
                                        confidence = rag_result.get('confidence', 'MEDIUM')
                                        search_metadata = rag_result.get('search_metadata', {})
                                        
                                        metadata = {
                                            "mode": "Hybrid-RAG",
                                            "confidence": confidence,
                                            "sources": len(sources),
                                            "search_type": search_metadata.get('search_type', 'hybrid'),
                                            "total_results": search_metadata.get('total_results', 0)
                                        }
                                        
                                        # Enhanced source info display
                                        search_info = f"신뢰도: {confidence}, 출처: {len(sources)}개"
                                        if search_metadata.get('total_results'):
                                            search_info += f", 검색결과: {search_metadata['total_results']}개"
                                        
                                        response_text += f"\n\n🔍 **하이브리드 검색** ({search_info})"
                                        
                                        await connection.send({
                                            "id": str(uuid.uuid4()),
                                            "type": "text",
                                            "text": response_text,
                                            "timestamp": datetime.utcnow().isoformat(),
                                            "metadata": metadata
                                        })
                                    else:
                                        # No relevant documents found, fallback to LLM
                                        print("[WebChat] No relevant documents found, using regular LLM")
                                        await self._generate_llm_response(connection, message.text, provider, model, "Hybrid")
                                else:
                                    # RAG disabled, use LLM directly
                                    print("[WebChat] RAG disabled, using LLM directly")
                                    await self._generate_llm_response(connection, message.text, provider, model, "LLM")
                                    
                            except Exception as rag_error:
                                print(f"[WebChat] RAG error: {str(rag_error)}, falling back to LLM")
                                # Fallback to LLM on any error
                                await self._generate_llm_response(connection, message.text, provider, model, "Error-Fallback")
                        
                    except Exception as e:
                        print(f"[WebChat] Error processing message: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        await self.handle_error(e)
                        # Send error message to client
                        try:
                            await connection.send({
                                "id": str(uuid.uuid4()),
                                "type": "system",
                                "text": f"죄송합니다. 메시지 처리 중 오류가 발생했습니다: {str(e)}",
                                "timestamp": datetime.utcnow().isoformat(),
                            })
                        except Exception as send_error:
                            print(f"[WebChat] Failed to send error message: {send_error}")
                            # Connection might be broken, let it close naturally
        
        except WebSocketDisconnect:
            # Clean up connection
            del self.connections[session_id]
        except Exception as e:
            await self.handle_error(e)
            if session_id in self.connections:
                del self.connections[session_id]
    
    async def send_message(self, message: PlatformMessage) -> Dict[str, Any]:
        """Send message to WebChat client."""
        if not await self.validate_message(message):
            raise ValueError("Invalid message format")
        
        # Find target connection
        target_session = message.conversation.id if message.conversation else None
        if not target_session or target_session not in self.connections:
            return {
                "id": str(message.id),
                "status": "failed",
                "error": "Connection not found",
            }
        
        connection = self.connections[target_session]
        
        # Convert to WebChat format
        webchat_message = await self._convert_to_webchat_format(message)
        
        # Send through WebSocket
        await connection.send(webchat_message)
        
        return {
            "id": str(message.id),
            "status": "sent",
            "platform": "webchat",
            "timestamp": message.timestamp.isoformat(),
        }
    
    async def receive_message(self, raw_message: Dict[str, Any]) -> PlatformMessage:
        """Convert WebChat message to platform message."""
        msg = PlatformMessage(
            id=raw_message.get("id", str(uuid.uuid4())),
            type=MessageType(raw_message.get("type", "text")),
            text=raw_message.get("text"),
            timestamp=datetime.fromisoformat(raw_message.get("timestamp", datetime.utcnow().isoformat())),
            platform_specific={"webchat_data": raw_message},
        )
        
        # Set user from raw message
        if raw_message.get("user"):
            msg.user = User(
                id=raw_message["user"]["id"],
                name=raw_message["user"]["name"],
                platform="webchat",
                avatar_url=raw_message["user"].get("avatar"),
            )
        
        # Set conversation
        if raw_message.get("session_id"):
            msg.conversation = self.conversations.get(raw_message["session_id"])
        
        # Process attachments
        if raw_message.get("attachments"):
            msg.attachments = [
                Attachment(
                    type=AttachmentType(att["type"]),
                    url=att.get("url"),
                    file_name=att.get("name"),
                    file_size=att.get("size"),
                    mime_type=att.get("mime_type"),
                )
                for att in raw_message["attachments"]
            ]
        
        return msg
    
    async def get_user_info(self, user_id: str) -> User:
        """Get WebChat user information."""
        # Find user in active connections
        for conn in self.connections.values():
            if conn.user_id == user_id:
                return User(
                    id=user_id,
                    name=f"User {user_id}",
                    platform="webchat",
                    metadata={
                        "session_id": conn.session_id,
                        "connected_at": conn.connected_at.isoformat(),
                    }
                )
        
        # Return default user info
        return User(
            id=user_id,
            name=f"User {user_id}",
            platform="webchat",
        )
    
    async def get_conversation_info(self, conversation_id: str) -> Conversation:
        """Get WebChat conversation information."""
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]
        
        return Conversation(
            id=conversation_id,
            platform="webchat",
            type="direct",
        )
    
    async def broadcast_message(self, message: PlatformMessage) -> Dict[str, Any]:
        """Broadcast message to all connected clients."""
        webchat_message = await self._convert_to_webchat_format(message)
        
        # Send to all connections
        results = []
        for session_id, connection in self.connections.items():
            try:
                await connection.send(webchat_message)
                results.append(session_id)
            except Exception as e:
                await self.handle_error(e)
        
        return {
            "status": "broadcast",
            "recipients": len(results),
            "sessions": results,
        }
    
    async def _generate_llm_response(
        self, 
        connection: WebChatConnection, 
        text: str, 
        provider: str = None, 
        model: str = None, 
        mode: str = "LLM"
    ) -> None:
        """Generate LLM response and send to client"""
        from app.llm.router import llm_router
        from langchain_core.messages import HumanMessage
        
        try:
            # Create messages list for LLM
            messages = [HumanMessage(content=text)]
            
            # Generate response with optional provider/model
            print(f"[WebChat] Generating LLM response with provider={provider}, model={model}...")
            response = await llm_router.generate(
                messages=messages,
                provider=provider,
                model=model
            )
            print(f"[WebChat] Generated response: {response.content}")
            
            # Add mode indicator to response
            response_text = response.content
            if mode == "LLM":
                response_text += f"\n\n🤖 **LLM 응답** ({provider or 'default'})"
            elif mode == "Hybrid":
                response_text += f"\n\n🔄 **하이브리드 응답** (RAG → LLM 폴백)"
            elif mode == "Error-Fallback":
                response_text += f"\n\n⚠️ **오류 복구** (LLM 폴백)"
            
            # Send response back to client
            await connection.send({
                "id": str(uuid.uuid4()),
                "type": "text",
                "text": response_text,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {
                    "mode": mode,
                    "provider": provider,
                    "model": model
                }
            })
            
        except Exception as e:
            print(f"[WebChat] LLM generation error: {str(e)}")
            await connection.send({
                "id": str(uuid.uuid4()),
                "type": "text",
                "text": f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            })

    async def _process_incoming_message(
        self, data: Dict[str, Any], connection: WebChatConnection
    ) -> PlatformMessage:
        """Process incoming WebChat message."""
        # Add metadata
        data["user"] = {
            "id": connection.user_id,
            "name": f"User {connection.user_id}",
        }
        data["session_id"] = connection.session_id
        data["timestamp"] = datetime.utcnow().isoformat()
        
        return await self.receive_message(data)
    
    async def _convert_to_webchat_format(self, message: PlatformMessage) -> Dict[str, Any]:
        """Convert platform message to WebChat format."""
        data = {
            "id": str(message.id),
            "type": message.type.value,
            "timestamp": message.timestamp.isoformat(),
        }
        
        if message.text:
            data["text"] = message.text
        
        if message.attachments:
            data["attachments"] = [
                {
                    "type": att.type.value,
                    "url": att.url,
                    "name": att.file_name,
                    "size": att.file_size,
                    "mime_type": att.mime_type,
                }
                for att in message.attachments
            ]
        
        if message.buttons:
            data["buttons"] = [
                {
                    "text": btn.text,
                    "value": btn.value,
                    "action": btn.action,
                }
                for btn in message.buttons
            ]
        
        if message.cards:
            data["cards"] = [
                {
                    "title": card.title,
                    "subtitle": card.subtitle,
                    "text": card.text,
                    "image": card.image_url,
                    "buttons": [
                        {"text": btn.text, "value": btn.value}
                        for btn in card.buttons
                    ],
                }
                for card in message.cards
            ]
        
        return data
    
    async def _send_system_message(self, connection: WebChatConnection, text: str) -> None:
        """Send system message to client."""
        await connection.send({
            "id": str(uuid.uuid4()),
            "type": "system",
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        })
    
    async def _cleanup_inactive_connections(self) -> None:
        """Clean up inactive connections periodically."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                now = datetime.utcnow()
                inactive_threshold = 3600  # 1 hour
                
                for session_id, conn in list(self.connections.items()):
                    if (now - conn.last_activity).total_seconds() > inactive_threshold:
                        await conn.websocket.close()
                        del self.connections[session_id]
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.handle_error(e)
    
    def get_widget_html(self, config: Optional[Dict[str, Any]] = None) -> str:
        """Generate HTML for embeddable widget."""
        widget_config = config or self.widget_config
        
        return f"""
        <!-- MOJI Web Chat Widget -->
        <div id="moji-webchat-widget"></div>
        <script src="{widget_config.get('script_url', '/static/moji-webchat.js')}"></script>
        <script>
          MojiWebChat.init({{
            apiUrl: '{widget_config.get('api_url', '/api/v1/webchat')}',
            theme: '{widget_config.get('theme', 'light')}',
            position: '{widget_config.get('position', 'bottom-right')}',
            title: '{widget_config.get('title', 'MOJI Assistant')}',
            placeholder: '{widget_config.get('placeholder', 'Type your message...')}',
          }});
        </script>
        """
    
    def supports_feature(self, feature: str) -> bool:
        """Check WebChat feature support."""
        features = {
            "buttons": True,
            "cards": True,
            "files": True,
            "images": True,
            "audio": True,
            "video": True,
            "location": False,
            "typing_indicator": True,
            "read_receipts": True,
            "reactions": False,
            "persistent_history": True,
            "file_upload": True,
        }
        return features.get(feature, False)