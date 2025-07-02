"""Simple conversation agent for WebChat testing."""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from app.adapters import PlatformMessage, MessageType, Button, Card
from app.agents.manager import agent_manager
from app.core.config import settings
from app.core.logging import logger


class ConversationAgent:
    """Basic conversation agent for handling chat messages."""
    
    def __init__(self):
        """Initialize conversation agent."""
        self.agent_manager = agent_manager  # Use singleton instance
        self.conversations: Dict[str, list] = {}
        self._initialized = False
        
    async def process_message(self, message: PlatformMessage) -> Optional[PlatformMessage]:
        """Process incoming message and generate response."""
        if not message.text:
            return None
        
        # Initialize agent manager if needed
        if not self._initialized:
            try:
                if not self.agent_manager.agents:
                    print("[ConversationAgent] Initializing default agents...")
                    await self.agent_manager.initialize_default_agents()
                    print(f"[ConversationAgent] Initialized {len(self.agent_manager.agents)} agents")
                self._initialized = True
            except Exception as e:
                print(f"[ConversationAgent] Failed to initialize agents: {e}")
                import traceback
                traceback.print_exc()
                return self._create_error_response(message, f"Agent initialization failed: {str(e)}")
            
        # Get conversation ID
        conv_id = message.conversation.id if message.conversation else "default"
        
        # Initialize conversation history if not exists
        if conv_id not in self.conversations:
            self.conversations[conv_id] = []
        
        # Add user message to history
        self.conversations[conv_id].append({
            "role": "user",
            "content": message.text,
            "timestamp": message.timestamp.isoformat()
        })
        
        # Handle special commands
        if message.text.lower().startswith("/"):
            return await self._handle_command(message)
        
        # Generate response using agent
        try:
            # Get the default agent (chat_agent with Monday.com tools)
            print(f"[ConversationAgent] Available agents: {list(self.agent_manager.agents.keys())}")
            agent = self.agent_manager.get_agent("chat_agent")
            if not agent:
                print("[ConversationAgent] Chat agent not found")
                logger.error("Chat agent not found")
                return self._create_error_response(message, "Agent not available")
            print(f"[ConversationAgent] Using agent: {agent.name}")
            
            # Process message with agent
            from langchain_core.messages import HumanMessage
            print(f"[ConversationAgent] Processing message with agent...")
            response = await agent.process([HumanMessage(content=message.text)])
            print(f"[ConversationAgent] Agent response: {response}")
            response_text = response.content
            print(f"[ConversationAgent] Response text: {response_text}")
            
            # Add assistant response to history
            self.conversations[conv_id].append({
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Create response message
            response = PlatformMessage(
                type=MessageType.TEXT,
                text=response_text,
                conversation=message.conversation,
                reply_to=str(message.id)
            )
            
            return response
            
        except Exception as e:
            print(f"[ConversationAgent] Error processing message: {e}")
            import traceback
            traceback.print_exc()
            return PlatformMessage(
                type=MessageType.TEXT,
                text=f"죄송합니다. 메시지 처리 중 오류가 발생했습니다: {str(e)}",
                conversation=message.conversation,
                reply_to=str(message.id)
            )
    
    async def _handle_command(self, message: PlatformMessage) -> PlatformMessage:
        """Handle special commands."""
        command = message.text.lower().strip()
        
        if command == "/help":
            return PlatformMessage(
                type=MessageType.TEXT,
                text="""사용 가능한 명령어:
/help - 도움말 보기
/clear - 대화 기록 초기화
/buttons - 버튼 예제 보기
/card - 카드 예제 보기
/features - MOJI 기능 소개""",
                conversation=message.conversation
            )
        
        elif command == "/clear":
            conv_id = message.conversation.id if message.conversation else "default"
            self.conversations[conv_id] = []
            return PlatformMessage(
                type=MessageType.TEXT,
                text="대화 기록이 초기화되었습니다.",
                conversation=message.conversation
            )
        
        elif command == "/buttons":
            return PlatformMessage(
                type=MessageType.BUTTONS,
                text="어떤 작업을 하시겠습니까?",
                buttons=[
                    Button(text="프로젝트 조회", value="프로젝트 목록을 보여주세요"),
                    Button(text="작업 생성", value="새 작업을 만들고 싶습니다"),
                    Button(text="일정 확인", value="오늘 일정을 알려주세요")
                ],
                conversation=message.conversation
            )
        
        elif command == "/card":
            return PlatformMessage(
                type=MessageType.CARD,
                cards=[
                    Card(
                        title="MOJI AI Assistant",
                        subtitle="지능형 프로젝트 관리 도우미",
                        text="MOJI는 자연어로 프로젝트를 관리할 수 있는 AI 어시스턴트입니다.",
                        image_url="https://via.placeholder.com/300x200?text=MOJI",
                        buttons=[
                            Button(text="자세히 보기", value="/features"),
                            Button(text="시작하기", value="안녕하세요")
                        ]
                    )
                ],
                conversation=message.conversation
            )
        
        elif command == "/features":
            return PlatformMessage(
                type=MessageType.TEXT,
                text="""MOJI의 주요 기능:

🤖 **자연어 대화**: 편하게 대화하듯 프로젝트를 관리하세요
📊 **프로젝트 추적**: 실시간으로 진행 상황을 모니터링
📅 **일정 관리**: 중요한 일정과 마감일을 놓치지 마세요
👥 **팀 협업**: 팀원들과 효율적으로 소통하고 협업
📈 **리포트 생성**: 프로젝트 현황을 한눈에 파악
🔗 **통합 연동**: Slack, Teams, KakaoTalk 등 다양한 플랫폼 지원

무엇을 도와드릴까요?""",
                conversation=message.conversation
            )
        
        else:
            return PlatformMessage(
                type=MessageType.TEXT,
                text=f"알 수 없는 명령어입니다: {command}\n/help를 입력하여 사용 가능한 명령어를 확인하세요.",
                conversation=message.conversation
            )
    
    def _prepare_context(self, conversation_id: str) -> str:
        """Prepare conversation context for LLM."""
        history = self.conversations.get(conversation_id, [])
        
        # Limit history to last 10 messages
        recent_history = history[-10:] if len(history) > 10 else history
        
        context = "You are MOJI, a helpful AI assistant for project management. "
        context += "You help users manage their projects, tasks, and schedules. "
        context += "Be friendly, professional, and concise.\n\n"
        
        if recent_history:
            context += "Recent conversation:\n"
            for msg in recent_history:
                role = msg["role"].capitalize()
                content = msg["content"]
                context += f"{role}: {content}\n"
        
        return context
    
    def _create_error_response(self, message: PlatformMessage, error_text: str) -> PlatformMessage:
        """Create error response message."""
        return PlatformMessage(
            platform=message.platform,
            user=message.user,
            conversation=message.conversation,
            text=error_text,
            type=MessageType.TEXT,
            timestamp=datetime.now()
        )