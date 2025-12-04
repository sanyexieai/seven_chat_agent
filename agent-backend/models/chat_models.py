from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime

class MessageType(str, Enum):
    """消息类型枚举"""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"

class AgentType(str, Enum):
    """智能体类型枚举"""
    # 原有类型（保留兼容性）
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    CHAT = "chat"
    SEARCH = "search"
    REPORT = "report"
    
    # 新的智能体类型
    PROMPT_DRIVEN = "prompt_driven"    # 纯提示词驱动
    TOOL_DRIVEN = "tool_driven"        # 纯工具驱动
    FLOW_DRIVEN = "flow_driven"        # 流程图驱动

class ChatRequest(BaseModel):
    """聊天请求模型"""
    user_id: str = Field(..., description="用户ID")
    message: str = Field(..., description="用户消息")
    context: Optional[Dict[str, Any]] = Field(default={}, description="上下文信息")
    agent_type: Optional[AgentType] = Field(default=AgentType.CHAT, description="智能体类型")
    agent_name: Optional[str] = Field(default=None, description="指定智能体名称")
    stream: bool = Field(default=False, description="是否流式响应")

class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    agent_name: Optional[str] = Field(default=None, description="智能体名称")
    tools_used: Optional[List[str]] = Field(default=[], description="使用的工具")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    pipeline_context: Optional[Dict[str, Any]] = Field(default=None, description="Pipeline上下文数据")

class AgentMessage(BaseModel):
    """智能体消息模型"""
    id: str = Field(..., description="消息ID")
    type: MessageType = Field(..., description="消息类型")
    content: str = Field(..., description="消息内容")
    agent_name: Optional[str] = Field(default=None, description="智能体名称")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="元数据")

class ToolCall(BaseModel):
    """工具调用模型"""
    tool_name: str = Field(..., description="工具名称")
    parameters: Dict[str, Any] = Field(..., description="工具参数")
    result: Optional[Any] = Field(default=None, description="工具执行结果")

class AgentContext(BaseModel):
    """智能体上下文模型"""
    user_id: str = Field(..., description="用户ID")
    session_id: str = Field(..., description="会话ID")
    messages: List[AgentMessage] = Field(default=[], description="消息历史")
    tools_used: List[ToolCall] = Field(default=[], description="工具调用历史")
    metadata: Dict[str, Any] = Field(default={}, description="元数据")

class StreamChunk(BaseModel):
    """流式响应块模型"""
    chunk_id: Optional[str] = Field(default=None, description="块ID")
    session_id: Optional[str] = Field(default=None, description="会话ID")
    type: str = Field(..., description="块类型")
    content: str = Field(..., description="内容")
    agent_name: Optional[str] = Field(default=None, description="智能体名称")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="元数据")
    is_end: bool = Field(default=False, description="是否为最后一个块")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳") 