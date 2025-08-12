from typing import Dict, Any, AsyncGenerator
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
import asyncio
import json
import uuid
from typing import List

logger = get_logger("general_agent")

class GeneralAgent(BaseAgent):
    """通用智能体
    
    通过数据库配置的系统提示词来实现不同的功能。
    这种智能体完全依赖提示词来定义行为，不需要特定的工具。
    """
    
    def __init__(self, name: str, description: str, system_prompt: str = None, llm_config: Dict[str, Any] = None):
        super().__init__(name, description)
        
        # 默认系统提示词
        self.default_system_prompt = """你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。
请用简洁、准确、友好的方式回应用户的问题。保持对话的自然性和连贯性。"""
        
        # 使用传入的系统提示词或默认提示词
        self.system_prompt = system_prompt or self.default_system_prompt
        
        # 保存LLM配置
        self.llm_config = llm_config
        
        # 知识库配置
        self.bound_knowledge_bases = []
        
        # 初始化LLM助手
        try:
            if llm_config:
                # 使用智能体特定的LLM配置
                self.llm_helper = get_llm_helper(llm_config)
                logger.info(f"通用智能体 {name} 使用特定LLM配置初始化成功")
            else:
                # 使用默认LLM配置
                self.llm_helper = get_llm_helper()
                logger.info(f"通用智能体 {name} 使用默认LLM配置初始化成功")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
    
    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self.system_prompt = prompt
        logger.info(f"智能体 {self.name} 系统提示词已更新")
    
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.system_prompt
    
    def set_knowledge_bases(self, knowledge_bases: List[Dict[str, Any]]):
        """设置绑定的知识库"""
        self.bound_knowledge_bases = knowledge_bases
        logger.info(f"智能体 {self.name} 绑定知识库: {[kb.get('name', 'Unknown') for kb in knowledge_bases]}")
    
    async def query_knowledge_base(self, query: str, db_session=None) -> str:
        """查询知识库"""
        if not self.bound_knowledge_bases:
            return ""
        
        try:
            from services.knowledge_base_service import KnowledgeBaseService
            kb_service = KnowledgeBaseService()
            
            all_results = []
            for kb_info in self.bound_knowledge_bases:
                kb_id = kb_info.get('id') or kb_info.get('knowledge_base_id')
                if not kb_id:
                    continue
                
                try:
                    # 查询知识库
                    results = kb_service.query_knowledge_base(db_session, kb_id, query, limit=3)
                    if results and results.get('chunks'):
                        kb_name = kb_info.get('name', f'知识库{kb_id}')
                        kb_results = f"\n\n来自知识库 '{kb_name}' 的相关信息：\n"
                        for chunk in results['chunks']:
                            kb_results += f"- {chunk.get('content', '')}\n"
                        all_results.append(kb_results)
                except Exception as e:
                    logger.warning(f"查询知识库 {kb_id} 失败: {str(e)}")
                    continue
            
            return "\n".join(all_results) if all_results else ""
            
        except Exception as e:
            logger.error(f"知识库查询失败: {str(e)}")
            return ""
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 获取用户上下文
            agent_context = self.get_context(user_id)
            if not agent_context:
                agent_context = AgentContext(
                    user_id=user_id,
                    session_id=str(uuid.uuid4()),
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, agent_context)
            
            # 构建对话历史
            conversation_history = []
            for msg in agent_context.messages[-10:]:  # 保留最近10条消息
                if msg.type == MessageType.USER:
                    conversation_history.append({"role": "user", "content": msg.content})
                elif msg.type == MessageType.AGENT:
                    conversation_history.append({"role": "assistant", "content": msg.content})
            
            # 添加当前用户消息
            conversation_history.append({"role": "user", "content": message})
            
            # 查询知识库（如果有绑定的话）
            knowledge_context = ""
            if self.bound_knowledge_bases:
                try:
                    # 从context中获取数据库会话
                    db_session = context.get('db_session') if context else None
                    knowledge_context = await self.query_knowledge_base(message, db_session)
                    if knowledge_context:
                        logger.info(f"智能体 {self.name} 查询知识库获得相关上下文")
                except Exception as e:
                    logger.warning(f"知识库查询失败: {str(e)}")
            
            # 构建增强的系统提示词
            enhanced_system_prompt = self.system_prompt
            if knowledge_context:
                enhanced_system_prompt += f"\n\n以下是相关的知识库信息，请基于这些信息回答用户问题：\n{knowledge_context}"
                enhanced_system_prompt += "\n\n请结合知识库信息，提供准确、详细的回答。如果知识库信息不足以回答问题，请说明并提供一般性建议。"
            
            # 调用LLM生成响应
            logger.info(f"通用智能体 {self.name} 使用增强系统提示词处理消息")
            
            # 临时禁用LLM调用，返回模拟响应（用于测试）
            try:
                response_content = await self.llm_helper.call(
                    messages=[
                        {"role": "system", "content": enhanced_system_prompt}
                    ] + conversation_history
                )
            except Exception as e:
                logger.warning(f"LLM调用失败，使用模拟响应: {str(e)}")
                # 生成模拟响应
                if knowledge_context:
                    response_content = f"您好！我是{self.name}智能体。我查询了知识库，找到了相关信息：\n{knowledge_context}\n\n基于这些信息，我会尽力帮助您。如果您需要真实的AI响应，请确保LLM服务正在运行。"
                else:
                    response_content = f"您好！我是{self.name}智能体。我收到了您的消息：'{message}'。根据我的系统提示词，我会尽力帮助您。如果您需要真实的AI响应，请确保LLM服务正在运行。"
            
            # 创建响应消息
            response = self.create_message(
                content=response_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            logger.info(f"通用智能体 {self.name} 处理消息完成")
            return response
            
        except Exception as e:
            logger.error(f"通用智能体处理消息失败: {str(e)}")
            error_response = self.create_message(
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}",
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            return error_response
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 获取用户上下文
            agent_context = self.get_context(user_id)
            if not agent_context:
                agent_context = AgentContext(
                    user_id=user_id,
                    session_id=str(uuid.uuid4()),
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, agent_context)
            
            # 构建对话历史
            conversation_history = []
            for msg in agent_context.messages[-10:]:  # 保留最近10条消息
                if msg.type == MessageType.USER:
                    conversation_history.append({"role": "user", "content": msg.content})
                elif msg.type == MessageType.AGENT:
                    conversation_history.append({"role": "assistant", "content": msg.content})
            
            # 添加当前用户消息
            conversation_history.append({"role": "user", "content": message})
            
            # 流式调用LLM
            logger.info(f"通用智能体 {self.name} 流式调用使用系统提示词: {self.system_prompt}")
            full_response = ""
            async for chunk in self.llm_helper.call_stream(
                messages=[
                    {"role": "system", "content": self.system_prompt}
                ] + conversation_history
            ):
                full_response += chunk
                yield StreamChunk(
                    type="content",
                    content=chunk
                )
            
            # 发送最终响应
            yield StreamChunk(
                type="final",
                content=full_response
            )
            
            # 创建并保存响应消息
            response = self.create_message(
                content=full_response,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            logger.info(f"通用智能体 {self.name} 流式处理消息完成")
            
        except Exception as e:
            logger.error(f"通用智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}"
            ) 