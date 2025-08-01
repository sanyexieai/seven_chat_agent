from typing import Dict, Any, AsyncGenerator
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
import asyncio
import json
import uuid

logger = get_logger("prompt_driven_agent")

class PromptDrivenAgent(BaseAgent):
    """纯提示词驱动智能体
    
    通过数据库配置的系统提示词来实现不同的功能。
    这种智能体完全依赖提示词来定义行为，不需要特定的工具。
    """
    
    def __init__(self, name: str, description: str, system_prompt: str = None):
        super().__init__(name, description)
        
        # 默认系统提示词
        self.default_system_prompt = """你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。
请用简洁、准确、友好的方式回应用户的问题。保持对话的自然性和连贯性。"""
        
        # 使用传入的系统提示词或默认提示词
        self.system_prompt = system_prompt or self.default_system_prompt
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"提示词驱动智能体 {name} 初始化成功，LLM已就绪")
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
            
            # 调用LLM生成响应
            logger.info(f"提示词驱动智能体 {self.name} 使用系统提示词: {self.system_prompt}")
            response_content = await self.llm_helper.call(
                messages=[
                    {"role": "system", "content": self.system_prompt}
                ] + conversation_history
            )
            
            # 创建响应消息
            response = self.create_message(
                content=response_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            logger.info(f"提示词驱动智能体 {self.name} 处理消息完成")
            return response
            
        except Exception as e:
            logger.error(f"提示词驱动智能体处理消息失败: {str(e)}")
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
            logger.info(f"提示词驱动智能体 {self.name} 流式调用使用系统提示词: {self.system_prompt}")
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
            
            logger.info(f"提示词驱动智能体 {self.name} 流式处理消息完成")
            
        except Exception as e:
            logger.error(f"提示词驱动智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}"
            ) 