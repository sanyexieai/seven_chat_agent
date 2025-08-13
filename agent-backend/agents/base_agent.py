from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator
from models.chat_models import AgentMessage, AgentContext, ToolCall, StreamChunk
from tools.base_tool import BaseTool
import asyncio
import uuid
from datetime import datetime

class BaseAgent(ABC):
    """智能体基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.tools: List[BaseTool] = []
        self.contexts: Dict[str, AgentContext] = {}
        
    @abstractmethod
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        pass
    
    @abstractmethod
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        pass
    
    def add_tool(self, tool: BaseTool):
        """添加工具"""
        self.tools.append(tool)
    
    def get_tools(self) -> List[BaseTool]:
        """获取所有工具"""
        return self.tools
    
    def get_context(self, user_id: str) -> Optional[AgentContext]:
        """获取用户上下文"""
        return self.contexts.get(user_id)
    
    def update_context(self, user_id: str, context: AgentContext):
        """更新用户上下文"""
        self.contexts[user_id] = context
    
    def create_message(self, content: str, message_type: str, agent_name: str = None) -> AgentMessage:
        """创建消息"""
        # 将字符串转换为MessageType枚举
        from models.chat_models import MessageType
        try:
            if message_type == "user":
                msg_type = MessageType.USER
            elif message_type == "agent":
                msg_type = MessageType.AGENT
            elif message_type == "system":
                msg_type = MessageType.SYSTEM
            elif message_type == "tool":
                msg_type = MessageType.TOOL
            else:
                msg_type = MessageType.AGENT  # 默认使用AGENT类型
        except Exception:
            msg_type = MessageType.AGENT  # 如果转换失败，使用默认类型
        
        return AgentMessage(
            id=str(uuid.uuid4()),
            type=msg_type,
            content=content,
            agent_name=agent_name or self.name,
            timestamp=datetime.now()
        )
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> ToolCall:
        """执行工具"""
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            raise ValueError(f"工具 {tool_name} 不存在")
        
        try:
            result = await tool.execute(parameters)
            return ToolCall(
                tool_name=tool_name,
                parameters=parameters,
                result=result
            )
        except Exception as e:
            raise Exception(f"工具执行失败: {str(e)}")
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具信息"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema()
            }
            for tool in self.tools
        ]
    
    async def cleanup_context(self, user_id: str):
        """清理用户上下文"""
        if user_id in self.contexts:
            del self.contexts[user_id] 