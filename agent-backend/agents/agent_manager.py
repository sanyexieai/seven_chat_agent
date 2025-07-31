from typing import Dict, Optional, AsyncGenerator, Any
from agents.base_agent import BaseAgent
from agents.chat_agent import ChatAgent
from agents.search_agent import SearchAgent
from agents.report_agent import ReportAgent
from models.chat_models import AgentMessage, StreamChunk, AgentContext
from utils.log_helper import get_logger
from database.database import SessionLocal
from models.database_models import Agent as DBAgent

# 获取logger实例
logger = get_logger("agent_manager")
import asyncio
import uuid

class AgentManager:
    """智能体管理器"""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.user_sessions: Dict[str, str] = {}  # user_id -> session_id
        self.session_contexts: Dict[str, AgentContext] = {}  # session_id -> context
        
    async def initialize(self):
        """初始化智能体管理器"""
        logger.info("初始化智能体管理器...")
        
        # 创建默认智能体
        await self._create_default_agents()
        
        logger.info(f"智能体管理器初始化完成，共 {len(self.agents)} 个智能体")
    
    async def _create_default_agents(self):
        """从数据库加载智能体"""
        db = SessionLocal()
        try:
            # 从数据库获取所有激活的智能体
            db_agents = db.query(DBAgent).filter(DBAgent.is_active == True).all()
            
            for db_agent in db_agents:
                # 根据智能体类型创建相应的智能体实例
                if db_agent.agent_type == "chat":
                    agent = ChatAgent(db_agent.name, db_agent.display_name)
                elif db_agent.agent_type == "search":
                    agent = SearchAgent(db_agent.name, db_agent.display_name)
                elif db_agent.agent_type == "report":
                    agent = ReportAgent(db_agent.name, db_agent.display_name)
                else:
                    # 默认使用聊天智能体
                    agent = ChatAgent(db_agent.name, db_agent.display_name)
                
                # 设置智能体配置
                if db_agent.config:
                    agent.config = db_agent.config
                
                self.agents[db_agent.name] = agent
                logger.info(f"加载智能体: {db_agent.name} ({db_agent.display_name})")
            
            logger.info(f"从数据库加载了 {len(self.agents)} 个智能体")
            
        except Exception as e:
            logger.error(f"从数据库加载智能体失败: {str(e)}")
            # 如果数据库加载失败，创建默认智能体
            await self._create_fallback_agents()
        finally:
            db.close()
    
    async def _create_fallback_agents(self):
        """创建默认智能体（备用方案）"""
        # 聊天智能体
        chat_agent = ChatAgent("chat_agent", "通用聊天智能体")
        self.agents["chat_agent"] = chat_agent
        
        # 搜索智能体
        search_agent = SearchAgent("search_agent", "搜索和信息检索智能体")
        self.agents["search_agent"] = search_agent
        
        # 报告智能体
        report_agent = ReportAgent("report_agent", "报告生成智能体")
        self.agents["report_agent"] = report_agent
        
        logger.info("创建默认智能体完成")
    
    def get_session_id(self, user_id: str) -> str:
        """获取或创建会话ID"""
        if user_id not in self.user_sessions:
            session_id = str(uuid.uuid4())
            self.user_sessions[user_id] = session_id
            self.session_contexts[session_id] = AgentContext(
                user_id=user_id,
                session_id=session_id
            )
        return self.user_sessions[user_id]
    
    def get_context(self, user_id: str) -> AgentContext:
        """获取用户上下文"""
        session_id = self.get_session_id(user_id)
        return self.session_contexts[session_id]
    
    def update_context(self, user_id: str, context: AgentContext):
        """更新用户上下文"""
        session_id = self.get_session_id(user_id)
        self.session_contexts[session_id] = context
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 获取或创建会话
            session_id = self.get_session_id(user_id)
            agent_context = self.get_context(user_id)
            
            # 如果上下文为空，创建一个新的
            if agent_context is None:
                agent_context = AgentContext(
                    user_id=user_id,
                    session_id=session_id,
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, agent_context)
            
            # 选择智能体（这里简化处理，实际可以根据消息内容智能选择）
            agent = self._select_agent(message)
            
            # 处理消息
            response = await agent.process_message(user_id, message, context)
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            return response
            
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
            raise
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 获取或创建会话
            session_id = self.get_session_id(user_id)
            agent_context = self.get_context(user_id)
            
            # 选择智能体
            agent = self._select_agent(message)
            
            # 流式处理消息
            async for chunk in agent.process_message_stream(user_id, message, context):
                yield chunk
                
                # 如果是最终响应，更新上下文
                if chunk.type == "final":
                    # 这里可以添加消息到上下文
                    pass
                    
        except Exception as e:
            logger.error(f"流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"处理消息时出错: {str(e)}"
            )
    
    def _select_agent(self, message: str) -> BaseAgent:
        """选择智能体（简化版本）"""
        # 这里可以实现更智能的智能体选择逻辑
        if any(keyword in message.lower() for keyword in ["搜索", "查找", "查询", "search", "find"]):
            return self.agents.get("search_agent", self.agents["chat_agent"])
        elif any(keyword in message.lower() for keyword in ["报告", "总结", "分析", "report", "summary"]):
            return self.agents.get("report_agent", self.agents["chat_agent"])
        else:
            return self.agents["chat_agent"]
    
 