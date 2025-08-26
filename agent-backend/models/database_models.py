from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

Base = declarative_base()

class Agent(Base):
    """智能体配置表"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=False)  # general, flow_driven
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)  # 智能体配置
    
    # 新增字段用于新智能体类型
    system_prompt = Column(Text, nullable=True)  # 系统提示词（用于general）
    bound_tools = Column(JSON, nullable=True)    # 绑定的工具列表（用于general）
    bound_knowledge_bases = Column(JSON, nullable=True)  # 绑定的知识库列表（用于general）
    flow_config = Column(JSON, nullable=True)    # 流程图配置（用于flow_driven）
    llm_config_id = Column(Integer, ForeignKey("llm_configs.id"), nullable=True)  # 关联的LLM配置
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    sessions = relationship("UserSession", back_populates="agent")
    llm_config = relationship("LLMConfig")  # 关联LLM配置

class Flow(Base):
    """流程图配置表"""
    __tablename__ = "flows"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    flow_config = Column(JSON, nullable=True)  # 流程图配置
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserSession(Base):
    """用户会话表"""
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(String(100), nullable=False)
    session_name = Column(String(200), nullable=False, default="新对话")
    # 移除强制绑定智能体，改为可选
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系 - 智能体关系改为可选
    agent = relationship("Agent", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session")

class ChatMessage(Base):
    """聊天消息表"""
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(100), unique=True, index=True, nullable=False)
    session_id = Column(String(100), ForeignKey("user_sessions.session_id"), nullable=False)
    user_id = Column(String(100), nullable=False)
    message_type = Column(String(50), nullable=False)  # user, agent, system, tool
    agent_name = Column(String(100), nullable=True)
    message_metadata = Column(JSON, nullable=True)  # 重命名为message_metadata避免冲突
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    session = relationship("UserSession", back_populates="messages")
    nodes = relationship("MessageNode", back_populates="message")

class MessageNode(Base):
    """消息节点表"""
    __tablename__ = "message_nodes"
    
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(100), nullable=False)  # 节点唯一标识
    message_id = Column(String(100), ForeignKey("chat_messages.message_id"), nullable=False)
    node_type = Column(String(50), nullable=False)  # llm, tool, judge, router等
    node_name = Column(String(200), nullable=False)  # 节点显示名称
    node_label = Column(String(200), nullable=True)  # 节点标签
    content = Column(Text, nullable=True)  # 节点输出内容
    node_metadata = Column(JSON, nullable=True)  # 节点元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    message = relationship("ChatMessage", back_populates="nodes")

# Pydantic响应模型
class AgentResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    agent_type: str
    is_active: bool
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None
    llm_config: Optional['LLMConfigResponse'] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AgentCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    agent_type: str
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None

class AgentUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None

class FlowResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class FlowCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None

class FlowUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None

class MCPServer(Base):
    """MCP服务器配置表"""
    __tablename__ = "mcp_servers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    transport = Column(String(50), nullable=False)  # stdio, sse, websocket, streamable_http
    command = Column(String(500), nullable=True)  # 命令（用于stdio）
    args = Column(JSON, nullable=True)  # 命令参数
    env = Column(JSON, nullable=True)  # 环境变量
    url = Column(String(500), nullable=True)  # URL（用于http/websocket）
    is_active = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)  # 其他配置
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    tools = relationship("MCPTool", back_populates="server")

class MCPTool(Base):
    """MCP工具表"""
    __tablename__ = "mcp_tools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    server_id = Column(Integer, ForeignKey("mcp_servers.id"), nullable=False)
    tool_type = Column(String(50), nullable=True)  # 工具类型
    input_schema = Column(JSON, nullable=True)  # 输入schema
    output_schema = Column(JSON, nullable=True)  # 输出schema
    examples = Column(JSON, nullable=True)  # 示例
    tool_schema = Column(JSON, nullable=True)  # 工具schema（兼容性）
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    server = relationship("MCPServer", back_populates="tools")

# Pydantic响应模型
class AgentResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    agent_type: str
    is_active: bool
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None
    llm_config: Optional['LLMConfigResponse'] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class AgentCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    agent_type: str
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None

class AgentUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    system_prompt: Optional[str] = None
    bound_tools: Optional[List[Any]] = None
    bound_knowledge_bases: Optional[List[Any]] = None
    flow_config: Optional[Dict[str, Any]] = None
    llm_config_id: Optional[int] = None

class FlowResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class FlowCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None

class FlowUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    flow_config: Optional[Dict[str, Any]] = None

class MCPServerResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    transport: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    is_active: bool
    config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    tools: Optional[List['MCPToolResponse']] = []
    
    class Config:
        from_attributes = True

class MCPServerCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    transport: str
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class MCPServerUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    transport: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class MCPToolResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    server_id: int
    tool_type: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    tool_schema: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MCPToolCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    server_id: int
    tool_type: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    tool_schema: Optional[Dict[str, Any]] = None

class MCPToolUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    tool_type: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    tool_schema: Optional[Dict[str, Any]] = None

class UserSessionResponse(BaseModel):
    id: int
    session_id: str
    user_id: str
    agent_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MessageNodeResponse(BaseModel):
    """消息节点响应模型"""
    id: int
    node_id: str
    node_type: str
    node_name: str
    node_label: Optional[str] = None
    content: Optional[str] = None  # 节点输出内容
    node_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatMessageResponse(BaseModel):
    id: int
    message_id: str
    session_id: str
    user_id: str
    message_type: str
    agent_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    nodes: Optional[List[MessageNodeResponse]] = None  # 节点列表
    
    class Config:
        from_attributes = True

class SessionCreate(BaseModel):
    user_id: str
    session_name: str = "新对话"
    agent_id: Optional[int] = None  # 现在可选

class SessionResponse(BaseModel):
    id: int
    session_id: str
    user_id: str
    session_name: str
    agent_id: Optional[int] = None  # 现在可选
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    session_id: str
    user_id: str
    message_type: str
    content: str
    agent_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class MessageResponse(BaseModel):
    id: int
    message_id: str
    session_id: str
    user_id: str
    message_type: str
    content: str
    agent_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# LLM配置相关模型
class LLMConfig(Base):
    """LLM配置表"""
    __tablename__ = "llm_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    provider = Column(String(50), nullable=False)  # openai, anthropic, local等
    model_name = Column(String(100), nullable=False)  # gpt-4, claude-3等
    api_key = Column(String(500), nullable=True)  # API密钥
    api_base = Column(String(500), nullable=True)  # API基础URL
    config = Column(JSON, nullable=True)  # 其他配置参数
    is_default = Column(Boolean, default=False)  # 是否为默认配置
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# LLM配置Pydantic模型
class LLMConfigCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    provider: str
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_default: bool = False

class LLMConfigUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

class LLMConfigResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    provider: str
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_default: bool
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
    owner_id = Column(String(100), nullable=True)  # 所有者ID
    is_public = Column(Boolean, default=False)  # 是否公开
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    documents = relationship("Document", back_populates="knowledge_base")

class Document(Base):
    """文档表"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf, txt, docx等
    content = Column(Text, nullable=True)  # 文档内容
    document_metadata = Column(JSON, nullable=True)  # 元数据
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    status = Column(String(50), default="pending")  # 文档状态：pending, processing, completed, failed
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")

class DocumentChunk(Base):
    """文档分块表"""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)  # 添加知识库ID
    content = Column(Text, nullable=False)  # 分块内容
    chunk_index = Column(Integer, nullable=False)  # 分块索引
    embedding = Column(JSON, nullable=True)  # 向量嵌入
    chunk_metadata = Column(JSON, nullable=True)  # 元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    document = relationship("Document", back_populates="chunks")
    knowledge_base = relationship("KnowledgeBase")

# 知识库Pydantic模型
class KnowledgeBaseCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    is_public: bool = False

class KnowledgeBaseUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    is_active: Optional[bool] = None

class KnowledgeBaseResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    is_public: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DocumentCreate(BaseModel):
    name: str
    file_type: str
    content: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    knowledge_base_id: int

class DocumentUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None

class DocumentResponse(BaseModel):
    id: int
    name: str
    file_type: str
    content: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    knowledge_base_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    knowledge_base_id: int
    content: str
    chunk_index: int
    embedding: Optional[List[float]] = None
    chunk_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class QueryRequest(BaseModel):
    query: str
    user_id: str
    top_k: int = 5
    max_results: int = 5
    similarity_threshold: float = 0.7

class QueryResponse(BaseModel):
    query: str
    results: List[DocumentChunkResponse]
    total_results: int

# 知识库查询历史模型
class KnowledgeBaseQuery(Base):
    """知识库查询历史表"""
    __tablename__ = "knowledge_base_queries"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    user_id = Column(String(100), nullable=False)
    query = Column(Text, nullable=False)  # 查询内容
    response = Column(Text, nullable=True)  # 响应内容
    sources = Column(JSON, nullable=True)  # 来源信息
    query_metadata = Column(JSON, nullable=True)  # 查询元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase")

# 知识库查询历史Pydantic模型
class KnowledgeBaseQueryCreate(BaseModel):
    knowledge_base_id: int
    user_id: str
    query: str
    response: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    query_metadata: Optional[Dict[str, Any]] = None

class KnowledgeBaseQueryResponse(BaseModel):
    id: int
    knowledge_base_id: int
    user_id: str
    query: str
    response: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    query_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True 