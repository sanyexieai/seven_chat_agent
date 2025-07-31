from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional, List, Dict, Any

Base = declarative_base()

class Agent(Base):
    """智能体配置表"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=False)  # chat, search, report等
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)  # 智能体配置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    sessions = relationship("UserSession", back_populates="agent")

class UserSession(Base):
    """用户会话表"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(String(100), index=True, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    title = Column(String(200), nullable=True)  # 会话标题
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    agent = relationship("Agent", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")

class Message(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("user_sessions.id"), nullable=False)
    message_id = Column(String(100), unique=True, index=True, nullable=False)
    type = Column(String(20), nullable=False)  # user, agent, system, tool
    content = Column(Text, nullable=False)
    agent_name = Column(String(100), nullable=True)
    message_metadata = Column(JSON, nullable=True)  # 重命名为message_metadata避免冲突
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    session = relationship("UserSession", back_populates="messages")



class MCPServer(Base):
    """MCP服务器表"""
    __tablename__ = "mcp_servers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    transport = Column(String(50), nullable=False)  # stdio, sse, websocket, streamable_http
    command = Column(String(500), nullable=True)  # 命令
    args = Column(JSON, nullable=True)  # 参数列表
    env = Column(JSON, nullable=True)  # 环境变量
    url = Column(String(500), nullable=True)  # URL（用于HTTP/WebSocket传输）
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    tools = relationship("MCPTool", back_populates="server", cascade="all, delete-orphan")

class MCPTool(Base):
    """MCP工具表"""
    __tablename__ = "mcp_tools"
    
    id = Column(Integer, primary_key=True, index=True)
    server_id = Column(Integer, ForeignKey("mcp_servers.id"), nullable=False)
    name = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    tool_type = Column(String(50), nullable=False)  # tool, resource, prompt
    input_schema = Column(JSON, nullable=True)  # 输入参数模式
    output_schema = Column(JSON, nullable=True)  # 输出参数模式
    examples = Column(JSON, nullable=True)  # 使用示例
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    server = relationship("MCPServer", back_populates="tools")
    
    # 复合唯一索引
    __table_args__ = (
        UniqueConstraint('server_id', 'name', name='uq_server_tool'),
    )

# Pydantic模型用于API
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class AgentCreate(BaseModel):
    """创建智能体请求模型"""
    name: str = Field(..., description="智能体名称")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    agent_type: str = Field(..., description="智能体类型")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")

class AgentUpdate(BaseModel):
    """更新智能体请求模型"""
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: Optional[bool] = Field(None, description="是否激活")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")

class AgentResponse(BaseModel):
    """智能体响应模型"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    agent_type: str
    is_active: bool
    config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SessionCreate(BaseModel):
    """创建会话请求模型"""
    user_id: str = Field(..., description="用户ID")
    agent_id: int = Field(..., description="智能体ID")
    title: Optional[str] = Field(None, description="会话标题")

class SessionResponse(BaseModel):
    """会话响应模型"""
    id: int
    session_id: str
    user_id: str
    agent_id: int
    title: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    agent: AgentResponse
    
    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    """创建消息请求模型"""
    session_id: int = Field(..., description="会话ID")
    type: str = Field(..., description="消息类型")
    content: str = Field(..., description="消息内容")
    agent_name: Optional[str] = Field(None, description="智能体名称")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class MessageResponse(BaseModel):
    """消息响应模型"""
    id: int
    message_id: str
    session_id: int
    type: str
    content: str
    agent_name: Optional[str]
    metadata: Optional[Dict[str, Any]] = None  # 保持API兼容性
    created_at: datetime
    
    class Config:
        from_attributes = True
    
    @classmethod
    def model_validate(cls, obj):
        """重写model_validate方法以处理字段映射"""
        if hasattr(obj, 'message_metadata'):
            # 将message_metadata映射到metadata
            obj.metadata = obj.message_metadata
        return super().model_validate(obj)



class MCPServerCreate(BaseModel):
    """创建MCP服务器请求模型"""
    name: str = Field(..., description="服务器名称")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    transport: str = Field(..., description="传输协议")
    command: Optional[str] = Field(None, description="命令")
    args: Optional[List[str]] = Field(None, description="参数列表")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量")
    url: Optional[str] = Field(None, description="URL")

class MCPServerUpdate(BaseModel):
    """更新MCP服务器请求模型"""
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    transport: Optional[str] = Field(None, description="传输协议")
    command: Optional[str] = Field(None, description="命令")
    args: Optional[List[str]] = Field(None, description="参数列表")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量")
    url: Optional[str] = Field(None, description="URL")
    is_active: Optional[bool] = Field(None, description="是否激活")

class MCPServerResponse(BaseModel):
    """MCP服务器响应模型"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    transport: str
    command: Optional[str]
    args: Optional[List[str]]
    env: Optional[Dict[str, str]]
    url: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MCPToolCreate(BaseModel):
    """创建MCP工具请求模型"""
    server_id: int = Field(..., description="服务器ID")
    name: str = Field(..., description="工具名称")
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    tool_type: str = Field(..., description="工具类型")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="输入参数模式")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="输出参数模式")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="使用示例")

class MCPToolUpdate(BaseModel):
    """更新MCP工具请求模型"""
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    tool_type: Optional[str] = Field(None, description="工具类型")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="输入参数模式")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="输出参数模式")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="使用示例")
    is_active: Optional[bool] = Field(None, description="是否激活")

class MCPToolResponse(BaseModel):
    """MCP工具响应模型"""
    id: int
    server_id: int
    name: str
    display_name: Optional[str]
    description: Optional[str]
    tool_type: str
    input_schema: Optional[Dict[str, Any]]
    output_schema: Optional[Dict[str, Any]]
    examples: Optional[List[Dict[str, Any]]]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True 