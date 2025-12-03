from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint, Float
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
    content = Column(Text, nullable=True)  # 消息内容（用户消息直接存储，智能体消息可选）
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
    chunk_count = Column(Integer, default=0)  # token
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
    raw_data = Column(JSON, nullable=True)  # 原始工具数据（完整信息）
    tool_metadata = Column(JSON, nullable=True)  # LLM整理后的元数据（args、使用场景、注意事项等）
    score = Column(Float, default=3.0)  # 工具评分：范围[1,5]，默认取中间值3.0
    is_available = Column(Boolean, default=True)  # 是否可用（由评分阈值计算并持久化）
    container_type = Column(String(50), nullable=True, default="none")  # 容器类型：browser, file, none
    container_config = Column(JSON, nullable=True)  # 容器配置
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    server = relationship("MCPServer", back_populates="tools")

class PromptTemplate(Base):
    """提示词模板表"""
    __tablename__ = "prompt_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)  # 模板名称，如 "auto_infer"
    display_name = Column(String(200), nullable=False)  # 显示名称
    description = Column(Text, nullable=True)  # 描述
    template_type = Column(String(50), nullable=False)  # 模板类型：system, user
    content = Column(Text, nullable=False)  # 模板内容
    variables = Column(JSON, nullable=True)  # 支持的变量列表
    is_builtin = Column(Boolean, default=False)  # 是否为内置模板（从代码中提取的）
    version = Column(String(50), nullable=True)  # 版本号，如 "1.0.0"
    usage_count = Column(Integer, default=0)  # 引用次数
    is_active = Column(Boolean, default=True)  # 是否激活
    source_file = Column(String(500), nullable=True)  # 来源文件路径
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TemporaryTool(Base):
    """临时工具表（通过代码编辑器生成）"""
    __tablename__ = "temporary_tools"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    code = Column(Text, nullable=False)  # 工具代码
    input_schema = Column(JSON, nullable=True)  # 输入schema
    output_schema = Column(JSON, nullable=True)  # 输出schema
    examples = Column(JSON, nullable=True)  # 示例
    container_type = Column(String(50), nullable=True, default="none")  # 容器类型：browser, file, none
    container_config = Column(JSON, nullable=True)  # 容器配置
    is_active = Column(Boolean, default=True)
    is_temporary = Column(Boolean, default=True)  # 是否为临时工具
    score = Column(Float, default=3.0)  # 工具评分：范围[1,5]，默认取中间值3.0
    is_available = Column(Boolean, default=True)  # 是否可用（由评分阈值计算并持久化）
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ToolConfig(Base):
    """工具配置表（用于存储所有工具的容器配置，包括内置工具）"""
    __tablename__ = "tool_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    tool_name = Column(String(100), unique=True, nullable=False, index=True)  # 工具名称（唯一标识）
    tool_type = Column(String(50), nullable=False)  # 工具类型：builtin, mcp, temporary
    container_type = Column(String(50), nullable=True, default="none")  # 容器类型：browser, file, none
    container_config = Column(JSON, nullable=True)  # 容器配置
    score = Column(Float, default=3.0)  # 工具评分（用于内置工具，范围[1,5]，默认3.0）
    is_available = Column(Boolean, default=True)  # 是否可用（由评分阈值计算并持久化）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineState(Base):
    """Pipeline 状态持久化表
    
    作用：
    - 按 user_id + agent_name + session_id 维度持久化 Pipeline.export() 的完整状态
    - 便于在服务重启或跨请求时恢复智能体的上下文与记忆
    """
    __tablename__ = "pipeline_states"
    
    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(String(100), nullable=True, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    state = Column(JSON, nullable=False)  # Pipeline.export() 的结果
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('user_id', 'agent_name', 'session_id', name='uq_pipeline_state_user_agent_session'),
    )


class ToolPromptLink(Base):
    """工具与提示词模板关联表
    
    作用：
    - 支持为每个工具绑定一个或多个提示词模板
    - 通过 scene 字段区分不同使用场景（如 auto_param, system, summary 等）
    - 方便在工具管理页面直接修改某个工具在特定场景下使用的提示词
    """
    __tablename__ = "tool_prompt_links"
    
    id = Column(Integer, primary_key=True, index=True)
    tool_name = Column(String(100), nullable=False, index=True)  # 对应 ToolManager 中的工具名称
    tool_type = Column(String(50), nullable=True)  # builtin, mcp, temporary
    scene = Column(String(50), nullable=True, default="auto_param")  # 使用场景
    prompt_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    prompt_template = relationship("PromptTemplate")


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
    raw_data: Optional[Dict[str, Any]] = None  # 原始工具数据（完整信息）
    tool_metadata: Optional[Dict[str, Any]] = None  # LLM整理后的元数据
    container_type: Optional[str] = "none"
    container_config: Optional[Dict[str, Any]] = None
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
    container_type: Optional[str] = None
    container_config: Optional[Dict[str, Any]] = None

class TemporaryToolResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    code: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    container_type: Optional[str] = "none"
    container_config: Optional[Dict[str, Any]] = None
    is_active: bool
    is_temporary: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ToolPromptLinkResponse(BaseModel):
    """工具与提示词关联响应模型"""
    id: int
    tool_name: str
    tool_type: Optional[str] = None
    scene: Optional[str] = None
    prompt_id: int
    is_active: bool
    prompt_template: Optional["PromptTemplateResponse"] = None  # 方便前端直接渲染
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ToolPromptLinkCreate(BaseModel):
    """创建 / 更新 工具与提示词关联"""
    tool_name: str
    tool_type: Optional[str] = None
    scene: Optional[str] = "auto_param"
    prompt_id: int
    is_active: Optional[bool] = True


class ToolPromptLinkUpdate(BaseModel):
    """更新工具与提示词关联"""
    scene: Optional[str] = None
    prompt_id: Optional[int] = None
    is_active: Optional[bool] = None

class TemporaryToolCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    code: str
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    container_type: Optional[str] = "none"
    container_config: Optional[Dict[str, Any]] = None

class TemporaryToolUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None
    container_type: Optional[str] = None
    container_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

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
    chunk_count: Optional[int] = 0  # tokens
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatMessageResponse(BaseModel):
    id: int
    message_id: str
    session_id: str
    user_id: str
    message_type: str
    content: str  # 添加消息内容字段！
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
    nodes: Optional[List[MessageNodeResponse]] = None  # 节点列表
    
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
    name = Column(String(100), index=True, nullable=False)
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
    # 新增：领域与分割策略标注/摘要关联
    domain = Column(String(100), nullable=True)  # 内容领域（如：技术、小说、财经、法律等）
    domain_confidence = Column(Float, default=0.0)  # 领域识别置信度
    chunk_strategy = Column(String(50), nullable=True)  # 分割策略：hierarchical/semantic/sentence/fixed/llm
    strategy_variant = Column(String(50), nullable=True)  # 策略变体/配置（可选，如chunk_size_500_overlap_50）
    is_summary = Column(Boolean, default=False)  # 是否为摘要分片
    summary_parent_chunk_id = Column(Integer, ForeignKey("document_chunks.id"), nullable=True)  # 摘要所对应的原始分片（或章节代表分片）
    section_title = Column(String(500), nullable=True)  # 如果能识别章节/标题，存储标题
    chunk_type = Column(String(50), default="原文")  # 分片类型：原文/LLM整理/摘要/其他
    source_query = Column(String(1000), nullable=True)  # 如果是LLM整理结果，记录原始查询
    parent_chunk_ids = Column(JSON, nullable=True)  # 如果是LLM整理结果，记录来源分片ID列表
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
    domain: Optional[str] = None
    domain_confidence: Optional[float] = None
    chunk_strategy: Optional[str] = None
    strategy_variant: Optional[str] = None
    is_summary: Optional[bool] = None
    summary_parent_chunk_id: Optional[int] = None
    section_title: Optional[str] = None
    chunk_type: Optional[str] = "原文"
    source_query: Optional[str] = None
    parent_chunk_ids: Optional[List[int]] = None
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

# 知识图谱相关模型
class KnowledgeTriple(Base):
    """知识三元组表"""
    __tablename__ = "knowledge_triples"
    
    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_id = Column(Integer, ForeignKey("document_chunks.id"), nullable=True)  # 关联到具体分块
    subject = Column(String(500), nullable=False)  # 主语（实体）
    predicate = Column(String(500), nullable=False)  # 关系
    object = Column(String(500), nullable=False)  # 宾语（实体）
    confidence = Column(Float, default=1.0)  # 置信度
    source_text = Column(Text, nullable=True)  # 来源文本片段
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联关系
    knowledge_base = relationship("KnowledgeBase")
    document = relationship("Document")
    chunk = relationship("DocumentChunk")

class KnowledgeTripleCreate(BaseModel):
    knowledge_base_id: int
    document_id: int
    chunk_id: Optional[int] = None
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_text: Optional[str] = None

class KnowledgeTripleResponse(BaseModel):
    id: int
    knowledge_base_id: int
    document_id: int
    chunk_id: Optional[int] = None
    subject: str
    predicate: str
    object: str
    confidence: float
    source_text: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# 工具配置Pydantic模型
class ToolConfigResponse(BaseModel):
    id: int
    tool_name: str
    tool_type: str
    container_type: Optional[str] = "none"
    container_config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ToolConfigCreate(BaseModel):
    tool_name: str
    tool_type: str
    container_type: Optional[str] = "none"
    container_config: Optional[Dict[str, Any]] = None

class ToolConfigUpdate(BaseModel):
    container_type: Optional[str] = None
    container_config: Optional[Dict[str, Any]] = None 