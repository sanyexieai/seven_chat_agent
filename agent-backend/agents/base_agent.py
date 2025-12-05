from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator
from models.chat_models import AgentMessage, AgentContext, ToolCall, StreamChunk, MessageType
from tools.base_tool import BaseTool
from agents.pipeline import Pipeline, get_pipeline
from services.memory_service import MemoryService
from services.memory_refinement_service import MemoryRefinementService
from models.database_models import MemoryRecordCreate
from utils.log_helper import get_logger
from services.session_service import MessageService
import asyncio
import uuid
from datetime import datetime


logger = get_logger("base_agent")


class BaseAgent(ABC):
    """智能体基类
    
    设计目标：
    - 为所有类型智能体提供统一的接口（通用智能体 / 流程图智能体 / 聊天智能体等）
    - 通过 Pipeline 管理**整个智能体生命周期内的上下文和记忆**
    """
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.tools: List[BaseTool] = []
        # 按 user_id 维度的会话上下文，常驻内存，由 agent_manager 持有的 Agent 实例跨请求共享
        self.contexts: Dict[str, AgentContext] = {}
        
    @abstractmethod
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        pass
    
    @abstractmethod
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        pass
    
    # ========= 工具管理 =========
    
    def add_tool(self, tool: BaseTool):
        """添加工具"""
        self.tools.append(tool)
    
    def get_tools(self) -> List[BaseTool]:
        """获取所有工具"""
        return self.tools
    
    # ========= 用户上下文（主存储在 BaseAgent，自同步到 Pipeline） =========
    
    def get_context(self, user_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[AgentContext]:
        """获取用户上下文
        
        - 主存储：self.contexts[user_id]，由常驻的 Agent 实例跨请求共享
        - 为了让 Pipeline 拿得到上下文，这里会把已有的 AgentContext 镜像到 Pipeline.agent_contexts 命名空间
        - 如果 context 中有 session_id，会检查内存中的上下文是否匹配，不匹配则返回 None（让子类从数据库恢复）
        - 如果内存中没有上下文，但 context 中提供了 db_session + session_id，则尝试从 chat_messages 表中重建 AgentContext
        """
        agent_context = self.contexts.get(user_id)
        
        # 如果内存中有上下文，但 context 中提供了 session_id 且不匹配，返回 None（让子类从数据库恢复）
        if agent_context and context is not None:
            session_id = context.get("session_id")
            if session_id and agent_context.session_id != session_id:
                # session_id 不匹配，返回 None，让子类从数据库恢复正确的上下文
                return None
        
        # 如果内存中没有上下文，且提供了 db_session + session_id，则尝试从数据库恢复
        if agent_context is None and context is not None:
            db_session = context.get("db_session")
            session_id = context.get("session_id")
            if db_session and session_id:
                try:
                    history = MessageService.get_session_messages(db_session, session_id, limit=100)
                    messages: List[AgentMessage] = []
                    for m in history:
                        # 将数据库中的 message_type 映射为内部 MessageType
                        mtype = (m.message_type or "").lower()
                        if mtype == "user":
                            msg_type = MessageType.USER
                        elif mtype in ("assistant", "agent"):
                            msg_type = MessageType.AGENT
                        elif mtype == "system":
                            msg_type = MessageType.SYSTEM
                        elif mtype == "tool":
                            msg_type = MessageType.TOOL
                        else:
                            msg_type = MessageType.AGENT
                        messages.append(AgentMessage(
                            id=m.message_id,
                            type=msg_type,
                            content=m.content or "",
                            agent_name=m.agent_name or self.name,
                            timestamp=m.created_at or datetime.now(),
                            metadata=m.metadata or {},
                        ))
                    agent_context = AgentContext(
                        user_id=user_id,
                        session_id=session_id,
                        messages=messages,
                        metadata={},
                    )
                    # 写入内存缓存
                    self.contexts[user_id] = agent_context
                    logger.info(f"BaseAgent 为用户 {user_id} 会话 {session_id} 从数据库重建 AgentContext，历史消息数: {len(messages)}")
                except Exception as e:
                    logger.warning(f"BaseAgent 从数据库重建 AgentContext 失败，将创建空上下文: {e}")
                    agent_context = None
        
        if agent_context and context is not None:
            try:
                pipeline = self.get_pipeline(context)
                key = f"{self.name}:{user_id}"
                pipeline.put(key, agent_context, namespace="agent_contexts")
            except Exception:
                pass
        return agent_context
    
    def update_context(self, user_id: str, agent_context: AgentContext, context: Optional[Dict[str, Any]] = None):
        """更新用户上下文
        
        - 写入 BaseAgent.contexts（主存储）
        - 同步一份到 Pipeline.agent_contexts，方便其他节点/模块统一查看上下文
        """
        self.contexts[user_id] = agent_context
        if context is not None:
            try:
                pipeline = self.get_pipeline(context)
                key = f"{self.name}:{user_id}"
                pipeline.put(key, agent_context, namespace="agent_contexts")
            except Exception:
                pass
    
    # ========= Pipeline 上下文工程（推荐） =========
    
    def get_pipeline(self, context: Optional[Dict[str, Any]]) -> Pipeline:
        """从上下文字典中获取/创建 Pipeline（推荐使用）
        
        说明：
        - context 为单次调用传入的上下文字典（如 chat_request.context）
        - Pipeline 会被挂在 context['pipeline']，可在整个智能体生命周期内复用
        - 兼容 flow_state 结构，适用于流程图智能体
        """
        if context is None:
            context = {}
        return get_pipeline(context)
    
    def pipeline_put(self, context: Optional[Dict[str, Any]], key: str, value: Any, namespace: str = "global") -> None:
        """向 Pipeline 写入数据"""
        pipeline = self.get_pipeline(context)
        pipeline.put(key, value, namespace=namespace)
    
    def pipeline_get(self, context: Optional[Dict[str, Any]], key: str, default: Any = None, namespace: str = "global") -> Any:
        """从 Pipeline 读取数据"""
        pipeline = self.get_pipeline(context)
        return pipeline.get(key, default, namespace=namespace)
    
    def pipeline_write_short_term_memory(self, context: Optional[Dict[str, Any]], content: Any, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        """写入短期记忆（针对当前任务的上下文，容量有限） - 底层封装，一般不直接在子类中调用。
        
        建议子类统一通过 remember_* 系列方法来写入记忆。
        """
        pipeline = self.get_pipeline(context)
        return pipeline.write_to_memory(
            content=content,
            memory_type=Pipeline.MEMORY_TYPE_SHORT_TERM,
            key=key,
            metadata=metadata,
        )
    
    def pipeline_write_long_term_memory(self, context: Optional[Dict[str, Any]], content: Any, key: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, quality_score: Optional[float] = None) -> str:
        """写入长期记忆（高价值、可复用的知识）"""
        pipeline = self.get_pipeline(context)
        return pipeline.write_to_memory(
            content=content,
            memory_type=Pipeline.MEMORY_TYPE_LONG_TERM,
            key=key,
            metadata=metadata,
            quality_score=quality_score,
        )
    
    def pipeline_search_memory(
        self,
        context: Optional[Dict[str, Any]],
        query: str,
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """综合搜索记忆：先查 Pipeline 内存，再查数据库 memories 表（RAG）。
        
        - Pipeline：搜索当前进程内的短期/长期记忆（基于字符串包含）
        - memories：如果 context 中有 db_session，则调用 MemoryService.search_memories 做向量检索
        """
        pipeline = self.get_pipeline(context)

        # 1) 先查 Pipeline 内部记忆
        results: List[Dict[str, Any]] = []
        try:
            in_pipeline = pipeline.search_memory(query=query, limit=limit)
            for item in in_pipeline:
                if "source" not in item:
                    item["source"] = "pipeline"
                results.append(item)
        except Exception:
            pass

        # 2) 再查数据库 memories 表（向量检索）
        ctx = context or {}
        db_session = ctx.get("db_session")
        session_id = ctx.get("session_id")
        if db_session:
            try:
                memory_service = MemoryService()
                db_results = memory_service.search_memories(
                    db=db_session,
                    query=query,
                    user_id=user_id,
                    agent_name=self.name,
                    session_id=session_id,
                    memory_types=None,
                    top_k=limit,
                )
                for r in db_results:
                    item = dict(r)
                    item.setdefault("source", "memories_db")
                    results.append(item)
            except Exception:
                # 记忆检索失败不影响主流程
                pass

        return results

    # ========= 统一的记忆处理接口（推荐子类使用） =========

    def remember_user_message(
        self,
        user_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录用户消息到短期记忆。
        
        - 所有 Agent 统一通过此接口写入“用户输入”类记忆
        - 如果需要覆盖策略，可在子类中重载此方法
        """
        try:
            tags = ["user_message", "short_term"]
            if stream:
                tags.append("stream")
            metadata: Dict[str, Any] = {
                "user_id": user_id,
                "agent_name": self.name,
                "category": "user_input",
                "tags": tags,
            }
            if extra_metadata:
                metadata.update(extra_metadata)

            ctx = context or {}

            # 1) 写入 Pipeline 短期记忆
            self.pipeline_write_short_term_memory(
                context=ctx,
                content=f"用户消息: {message}",
                metadata=metadata,
            )

            # 2) 同步到数据库 memories 表（原始对话存为潜意识）
            db_session = ctx.get("db_session")
            if db_session:
                try:
                    memory_service = MemoryService()
                    # 原始对话数据存为潜意识（subconscious）
                    record = MemoryRecordCreate(
                        user_id=user_id,
                        agent_name=self.name,
                        session_id=ctx.get("session_id"),
                        memory_type=Pipeline.MEMORY_TYPE_SUBCONSCIOUS,  # 改为潜意识
                        category="user_input",
                        source="conversation",
                        content=f"用户消息: {message}",
                        metadata=metadata,
                    )
                    memory_service.create_memory(db_session, record, auto_embed=True)
                except Exception:
                    # DB 记忆失败不影响主流程
                    pass
        except Exception:
            # 记忆失败不影响主流程
            pass

    def remember_agent_response(
        self,
        user_id: str,
        response: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools_used: Optional[List[str]] = None,
        category: str = "agent_response",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录智能体回复到短期记忆。
        
        - 所有 Agent 统一通过此接口写入“助手输出”类记忆
        """
        try:
            tags = ["agent_response", "short_term"]
            if stream:
                tags.append("stream")
            metadata: Dict[str, Any] = {
                "user_id": user_id,
                "agent_name": self.name,
                "category": category,
                "tags": tags,
            }
            if tools_used:
                metadata["tools_used"] = tools_used
            if extra_metadata:
                metadata.update(extra_metadata)

            ctx = context or {}

            # 1) 写入 Pipeline 短期记忆
            self.pipeline_write_short_term_memory(
                context=ctx,
                content=f"智能体回复: {response}",
                metadata=metadata,
            )

            # 2) 同步到数据库 memories 表（原始对话存为潜意识）
            db_session = ctx.get("db_session")
            if db_session:
                try:
                    memory_service = MemoryService()
                    # 原始对话数据存为潜意识（subconscious）
                    record = MemoryRecordCreate(
                        user_id=user_id,
                        agent_name=self.name,
                        session_id=ctx.get("session_id"),
                        memory_type=Pipeline.MEMORY_TYPE_SUBCONSCIOUS,  # 改为潜意识
                        category=category,
                        source="conversation",
                        content=f"智能体回复: {response}",
                        metadata=metadata,
                    )
                    memory_service.create_memory(db_session, record, auto_embed=True)
                except Exception:
                    pass
        except Exception:
            pass

    def remember_dialog_turn(
        self,
        user_id: str,
        user_message: str,
        agent_response: str,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools_used: Optional[List[str]] = None,
        category: str = "dialog_turn",
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一整轮对话（用户 + 助手）到短期记忆。
        
        - 默认用于“轮次摘要”型记忆写入
        """
        try:
            base_prefix = "[流式对话轮次]" if stream else "[对话轮次]"
            summary_content = f"{base_prefix} 用户: {user_message}\n助手: {agent_response}"

            tags = ["dialog", "short_term"]
            if stream:
                tags.append("stream")
            metadata: Dict[str, Any] = {
                "user_id": user_id,
                "agent_name": self.name,
                "category": category,
                "tags": tags,
            }
            if tools_used:
                metadata["tools_used"] = tools_used
            if extra_metadata:
                metadata.update(extra_metadata)

            ctx = context or {}

            # 1) 写入 Pipeline 短期记忆（轮次摘要）
            self.pipeline_write_short_term_memory(
                context=ctx,
                content=summary_content,
                metadata=metadata,
            )

            # 2) 同步到数据库 memories 表（原始对话存为潜意识）
            db_session = ctx.get("db_session")
            if db_session:
                try:
                    memory_service = MemoryService()
                    # 原始对话数据存为潜意识（subconscious）
                    record = MemoryRecordCreate(
                        user_id=user_id,
                        agent_name=self.name,
                        session_id=ctx.get("session_id"),
                        memory_type=Pipeline.MEMORY_TYPE_SUBCONSCIOUS,  # 改为潜意识
                        category=category,
                        source="conversation",
                        content=summary_content,
                        metadata=metadata,
                    )
                    memory_service.create_memory(db_session, record, auto_embed=True)
                except Exception:
                    pass
        except Exception:
            pass
    
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

    # ========= 对话历史构建（可被子类重写的钩子） =========

    def get_history_window_size(self) -> int:
        """返回用于构建对话历史时的窗口大小（条数）。子类可覆盖实现不同策略。"""
        return 10

    def build_conversation_history(
        self,
        agent_context: Optional[AgentContext],
        current_user_message: str,
    ) -> List[Dict[str, str]]:
        """根据 AgentContext 构建 LLM 所需的对话历史格式。

        默认策略：
        - 取最近 get_history_window_size() 条消息
        - USER -> role: user
        - AGENT -> role: assistant
        - 最后追加当前用户消息

        不同类型智能体如需调整历史构造策略，可在子类中重写此方法。
        """
        from models.chat_models import MessageType  # 延迟导入，避免循环依赖

        history: List[Dict[str, str]] = []
        if agent_context and agent_context.messages:
            window_size = self.get_history_window_size()
            for msg in agent_context.messages[-window_size:]:
                if msg.type == MessageType.USER:
                    history.append({"role": "user", "content": msg.content})
                elif msg.type == MessageType.AGENT:
                    history.append({"role": "assistant", "content": msg.content})

        # 追加当前用户消息
        history.append({"role": "user", "content": current_user_message})
        return history
    
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
    
    async def refine_memories_from_subconscious(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """从潜意识记忆中提取重点，并存储为短期/长期记忆
        
        这个方法应该在对话结束后或定期调用，用于提炼记忆。
        
        Args:
            context: 上下文字典（需要包含 db_session 和 session_id）
            user_id: 用户ID（如果未提供，从 context 中获取）
            limit: 每次处理的潜意识记忆数量
            
        Returns:
            提炼结果统计
        """
        ctx = context or {}
        db_session = ctx.get("db_session")
        session_id = ctx.get("session_id")
        
        if not db_session:
            logger.warning("BaseAgent.refine_memories_from_subconscious: 缺少 db_session")
            return {
                "processed": 0,
                "short_term_created": 0,
                "long_term_created": 0,
                "errors": 1,
            }
        
        if not user_id:
            # 尝试从 context 中获取
            user_id = ctx.get("user_id", "default_user")
        
        try:
            refinement_service = MemoryRefinementService()
            result = await refinement_service.refine_memories(
                db=db_session,
                user_id=user_id,
                agent_name=self.name,
                session_id=session_id,
                limit=limit,
            )
            logger.info(
                f"BaseAgent {self.name} 记忆提炼完成: "
                f"处理 {result['processed']} 条，"
                f"创建短期记忆 {result['short_term_created']} 条，"
                f"创建长期记忆 {result['long_term_created']} 条"
            )
            return result
        except Exception as e:
            logger.error(f"BaseAgent {self.name} 记忆提炼失败: {e}")
            return {
                "processed": 0,
                "short_term_created": 0,
                "long_term_created": 0,
                "errors": 1,
            } 