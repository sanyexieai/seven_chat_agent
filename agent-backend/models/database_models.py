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
    agent_type = Column(String(50), nullable=False)  # prompt_driven, tool_driven, flow_driven等
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)  # 智能体配置
    
    # 新增字段用于新智能体类型
    system_prompt = Column(Text, nullable=True)  # 系统提示词（用于prompt_driven）
    bound_tools = Column(JSON, nullable=True)    # 绑定的工具列表（用于tool_driven）
    flow_config = Column(JSON, nullable=True)    # 流程图配置（用于flow_driven）
    
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
    system_prompt: Optional[str] = Field(None, description="系统提示词（用于prompt_driven）")
    bound_tools: Optional[List[str]] = Field(None, description="绑定的工具列表（用于tool_driven）")
    flow_config: Optional[Dict[str, Any]] = Field(None, description="流程图配置（用于flow_driven）")

class AgentUpdate(BaseModel):
    """更新智能体请求模型"""
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    is_active: Optional[bool] = Field(None, description="是否激活")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")
    system_prompt: Optional[str] = Field(None, description="系统提示词（用于prompt_driven）")
    bound_tools: Optional[List[str]] = Field(None, description="绑定的工具列表（用于tool_driven）")
    flow_config: Optional[Dict[str, Any]] = Field(None, description="流程图配置（用于flow_driven）")

class AgentResponse(BaseModel):
    """智能体响应模型"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    agent_type: str
    is_active: bool
    config: Optional[Dict[str, Any]]
    system_prompt: Optional[str]
    bound_tools: Optional[List[str]]
    flow_config: Optional[Dict[str, Any]]
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

# 知识库相关模型
class KnowledgeBase(Base):
    """知识库表"""
    __tablename__ = "knowledge_bases"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(String(100), index=True, nullable=False)  # 知识库所有者
    is_public = Column(Boolean, default=False)  # 是否公开
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)  # 知识库配置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    documents = relationship("Document", back_populates="knowledge_base", cascade="all, delete-orphan")
    chunks = relationship("DocumentChunk", back_populates="knowledge_base", cascade="all, delete-orphan")

class Document(Base):
    """文档表"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    name = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=True)  # 文件路径
    file_type = Column(String(50), nullable=False)  # txt, pdf, docx, md等
    file_size = Column(Integer, nullable=True)  # 文件大小（字节）
    content = Column(Text, nullable=True)  # 文档内容
    doc_metadata = Column(JSON, nullable=True)  # 文档元数据
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

class DocumentChunk(Base):
    """文档分块表"""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)  # 分块索引
    content = Column(Text, nullable=False)  # 分块内容
    embedding = Column(Text, nullable=True)  # 向量嵌入（JSON格式）
    chunk_metadata = Column(JSON, nullable=True)  # 分块元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")
    document = relationship("Document", back_populates="chunks")

class KnowledgeBaseQuery(Base):
    """知识库查询记录表"""
    __tablename__ = "knowledge_base_queries"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    user_id = Column(String(100), index=True, nullable=False)
    query = Column(Text, nullable=False)  # 查询内容
    response = Column(Text, nullable=True)  # 响应内容
    sources = Column(JSON, nullable=True)  # 来源文档
    query_metadata = Column(JSON, nullable=True)  # 查询元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase")

# 知识库相关的Pydantic模型
class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求模型"""
    name: str = Field(..., description="知识库名称")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    owner_id: str = Field(..., description="所有者ID")
    is_public: bool = Field(False, description="是否公开")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")

class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求模型"""
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="描述")
    is_public: Optional[bool] = Field(None, description="是否公开")
    is_active: Optional[bool] = Field(None, description="是否激活")
    config: Optional[Dict[str, Any]] = Field(None, description="配置")

class KnowledgeBaseResponse(BaseModel):
    """知识库响应模型"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    owner_id: str
    is_public: bool
    is_active: bool
    config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DocumentCreate(BaseModel):
    """创建文档请求模型"""
    knowledge_base_id: int = Field(..., description="知识库ID")
    name: str = Field(..., description="文档名称")
    file_type: str = Field(..., description="文件类型")
    content: Optional[str] = Field(None, description="文档内容")
    doc_metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

class DocumentUpdate(BaseModel):
    """更新文档请求模型"""
    name: Optional[str] = Field(None, description="文档名称")
    content: Optional[str] = Field(None, description="文档内容")
    doc_metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")
    is_active: Optional[bool] = Field(None, description="是否激活")

class DocumentResponse(BaseModel):
    """文档响应模型"""
    id: int
    knowledge_base_id: int
    name: str
    file_path: Optional[str]
    file_type: str
    file_size: Optional[int]
    content: Optional[str]
    doc_metadata: Optional[Dict[str, Any]]
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DocumentChunkResponse(BaseModel):
    """文档分块响应模型"""
    id: int
    knowledge_base_id: int
    document_id: int
    chunk_index: int
    content: str
    chunk_metadata: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True

class QueryRequest(BaseModel):
    """查询请求模型"""
    knowledge_base_id: int = Field(..., description="知识库ID")
    query: str = Field(..., description="查询内容")
    user_id: str = Field(..., description="用户ID")
    max_results: Optional[int] = Field(5, description="最大结果数")

class QueryResponse(BaseModel):
    """查询响应模型"""
    query: str
    response: str
    sources: List[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True 