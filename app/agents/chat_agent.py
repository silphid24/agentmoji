"""Chat agent implementation"""

from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains import LLMChain
from langchain_core.callbacks import AsyncCallbackHandler
from langchain.agents import create_react_agent, AgentExecutor
from langchain.tools import Tool

from app.agents.base import BaseAgent
from app.core.logging import logger
from app.core.config import settings
from app.agents.tools import tool_registry


class ChatAgent(BaseAgent):
    """Basic chat agent for conversations"""
    
    def __init__(
        self,
        agent_id: str = "chat_agent",
        name: str = "MOJI Chat Agent",
        description: str = "General purpose chat agent",
        system_prompt: Optional[str] = None,
        memory_window: int = 5
    ):
        super().__init__(agent_id, name, description, memory_window)
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self.llm = None
        self.chain = None
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt"""
        return """You are MOJI, a helpful AI assistant with access to Monday.com project management tools. You are:
- Friendly and professional
- Concise but thorough in your responses
- Honest about what you know and don't know
- Respectful of user privacy and preferences
- Capable of managing Monday.com projects using natural language

You have access to Monday.com tools for:
- Getting project summaries and status reports
- Creating new project items
- Updating existing tasks
- Searching for specific items
- Getting detailed board information

When users ask about project management, Monday.com data, or want to create/update tasks, use the appropriate Monday.com tools.

Current context:
- Application: {app_name}
- Version: {version}
"""
    
    async def initialize(self) -> None:
        """Initialize the chat agent"""
        # Get LLM from router
        from app.llm.router import llm_router
        
        # Initialize router if needed
        if not llm_router.current_provider:
            await llm_router.initialize()
        
        # Get LangChain model
        self.llm = await llm_router.get_langchain_model()
        
        # Get tools for this agent
        tools = tool_registry.get_tools_for_agent("general")
        logger.info(f"Chat agent loaded {len(tools)} tools: {[tool.name for tool in tools]}")
        
        # Create standard prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt.format(
                app_name=settings.app_name,
                version=settings.app_version
            )),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
        
        # Store tools for later use
        self.tools = tools
        
        # Create simple chain (we'll handle tools manually)
        self.chain = LLMChain(
            llm=self.llm,
            prompt=prompt,
            memory=self.memory
        )
        
        logger.info(f"Chat agent initialized with {len(self.tools)} tools")
        
        logger.info(f"Chat agent initialized with LLM: {llm_router.config.provider}")
    
    async def process(self, messages: List[BaseMessage], **kwargs) -> BaseMessage:
        """Process messages and return response"""
        try:
            # Get the last user message
            last_message = messages[-1] if messages else None
            if not last_message or not isinstance(last_message, HumanMessage):
                return AIMessage(content="I didn't receive a valid message.")
            
            # Add messages to memory
            for msg in messages[:-1]:  # Add all but the last message
                if isinstance(msg, HumanMessage):
                    self.memory.chat_memory.add_user_message(msg.content)
                elif isinstance(msg, AIMessage):
                    self.memory.chat_memory.add_ai_message(msg.content)
            
            # Check if provider/model override is specified
            provider = kwargs.get('provider')
            model = kwargs.get('model')
            
            # Generate response with tool support
            response_content = await self._generate_response_with_tools(
                last_message.content, 
                provider=provider, 
                model=model
            )
            
            # Add the interaction to memory
            self.memory.chat_memory.add_user_message(last_message.content)
            self.memory.chat_memory.add_ai_message(response_content)
            
            return AIMessage(content=response_content)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return AIMessage(content="I'm sorry, I encountered an error processing your message.")
    
    async def _generate_response(self, input_text: str, provider: Optional[str] = None, model: Optional[str] = None) -> str:
        """Generate response using LLM"""
        if not self.chain:
            # Fallback if chain not initialized
            return f"I received your message: '{input_text}'. The LLM is not yet initialized."
        
        try:
            # If provider/model override is specified, use LLM router directly
            if provider or model:
                from app.llm.router import llm_router
                from langchain_core.messages import HumanMessage
                
                # Generate with specific provider/model
                response = await llm_router.generate(
                    [HumanMessage(content=input_text)],
                    provider=provider,
                    model=model
                )
                return response.content
            else:
                # Use the chain to generate response with default settings
                response = await self.chain.arun(input=input_text)
                return response
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return "I apologize, but I encountered an error generating a response."
    
    async def _generate_response_with_tools(self, input_text: str, provider: Optional[str] = None, model: Optional[str] = None) -> str:
        """Generate response with tool support"""
        # Check if input might require tools
        tool_keywords = {
            'monday': ['monday', 'Monday', '프로젝트', '워크스페이스', '보드', '작업', '아이템'],
            'calculator': ['계산', 'calculate', '+', '-', '*', '/', '더하기', '빼기'],
            'datetime': ['날짜', '시간', 'date', 'time', '오늘', '지금']
        }
        
        # Detect if we need to use tools
        should_use_tool = False
        selected_tool = None
        
        for tool_type, keywords in tool_keywords.items():
            if any(keyword in input_text.lower() for keyword in keywords):
                should_use_tool = True
                if tool_type == 'monday':
                    # Determine which Monday tool to use
                    if any(word in input_text for word in ['요약', '현황', '상태', 'summary']):
                        selected_tool = 'monday_project_summary'
                    elif any(word in input_text for word in ['생성', '만들', 'create', '추가']):
                        selected_tool = 'monday_create_item'
                    elif any(word in input_text for word in ['검색', 'search', '찾']):
                        selected_tool = 'monday_search'
                    elif any(word in input_text for word in ['보드', 'board', '상세']):
                        selected_tool = 'monday_board_details'
                    else:
                        selected_tool = 'monday_project_summary'  # Default
                elif tool_type == 'calculator':
                    selected_tool = 'Calculator'
                elif tool_type == 'datetime':
                    selected_tool = 'DateTime'
                break
        
        if should_use_tool and selected_tool and self.tools:
            # Find and execute the tool
            for tool in self.tools:
                if tool.name == selected_tool:
                    try:
                        logger.info(f"Using tool: {selected_tool}")
                        # Execute tool based on type
                        if selected_tool == 'monday_project_summary':
                            # Project summary doesn't need parameters
                            result = tool.run(tool_input={"board_id": None})
                        elif selected_tool == 'monday_create_item':
                            # Create item with basic info
                            result = tool.run(tool_input={
                                "board_id": settings.monday_default_board_id or "2490066826",
                                "item_name": "새로운 작업",
                                "description": input_text
                            })
                        elif selected_tool == 'monday_search':
                            # Search with query
                            result = tool.run(tool_input={"query": input_text})
                        elif selected_tool == 'monday_board_details':
                            # Board details
                            result = tool.run(tool_input={"board_id": settings.monday_default_board_id or "2490066826"})
                        elif selected_tool == 'Calculator':
                            # Calculator tool
                            result = tool.run(tool_input=input_text)
                        elif selected_tool == 'DateTime':
                            # DateTime tool
                            result = tool.run(tool_input=input_text)
                        else:
                            result = tool.run(tool_input=input_text)
                        
                        return result
                    except Exception as e:
                        logger.error(f"Tool execution error: {e}")
                        return f"도구 실행 중 오류가 발생했습니다: {str(e)}"
        
        # Fallback to regular LLM response
        return await self._generate_response(input_text, provider, model)
    
    async def _generate_agent_response(self, input_text: str, provider: Optional[str] = None, model: Optional[str] = None) -> str:
        """Generate response using agent executor with tools"""
        if not self.agent_executor:
            return "Agent executor is not initialized."
        
        try:
            # If provider/model override is specified, we'll need to handle this differently
            if provider or model:
                from app.llm.router import llm_router
                from langchain_core.messages import HumanMessage
                
                # Generate with specific provider/model
                response = await llm_router.generate(
                    [HumanMessage(content=input_text)],
                    provider=provider,
                    model=model
                )
                return response.content
            else:
                # Use agent executor with tools
                try:
                    response = await self.agent_executor.ainvoke({
                        "input": input_text,
                        "history": [],
                        "agent_scratchpad": []
                    })
                    return response.get("output", "No response generated.")
                except Exception as e:
                    logger.error(f"Agent executor error: {e}")
                    # Fallback to direct LLM call
                    from langchain_core.messages import HumanMessage
                    response = await self.llm.ainvoke([HumanMessage(content=input_text)])
                    return response.content
        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"
    
    def add_tool(self, tool: Any) -> None:
        """Add a tool to the agent"""
        # TODO: Implement tool integration
        logger.info(f"Tool integration not yet implemented for {self.name}")
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history as list of dicts"""
        history = []
        messages = self.memory.chat_memory.messages
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                history.append({"role": "system", "content": msg.content})
        
        return history