from typing import Dict, Any, AsyncGenerator
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("chat_agent")
from utils.llm_helper import get_llm_helper
import asyncio
import json
import uuid

class ChatAgent(BaseAgent):
    """聊天智能体"""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self.system_prompt = """你是一个友好的AI助手，能够帮助用户解答问题、进行对话交流。
请用简洁、准确、友好的方式回应用户的问题。保持对话的自然性和连贯性。"""
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"聊天智能体 {name} 初始化成功，LLM已就绪")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 获取用户上下文
            user_context = self.get_context(user_id)
            
            # 如果上下文为空，创建一个新的
            if user_context is None:
                user_context = AgentContext(
                    user_id=user_id,
                    session_id=f"session_{user_id}",
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, user_context)
            
            # 构建对话历史
            conversation_history = self._build_conversation_history(user_context)
            
            # 生成响应
            response_content = await self._generate_response(message, conversation_history, context)
            
            # 创建响应消息
            response = self.create_message(
                content=response_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            user_context.messages.append(response)
            self.update_context(user_id, user_context)
            
            logger.info(f"用户 {user_id} 消息处理完成")
            return response
            
        except Exception as e:
            logger.error(f"聊天智能体处理消息失败: {str(e)}")
            return self.create_message(
                content=f"抱歉，处理您的消息时出现了问题: {str(e)}",
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 获取用户上下文
            user_context = self.get_context(user_id)
            
            # 如果上下文为空，创建一个新的
            if user_context is None:
                user_context = AgentContext(
                    user_id=user_id,
                    session_id=f"session_{user_id}",
                    messages=[],
                    metadata={}
                )
                self.update_context(user_id, user_context)
            
            # 构建对话历史
            conversation_history = self._build_conversation_history(user_context)
            
            # 流式生成响应
            async for chunk in self._generate_response_stream(message, conversation_history, context):
                yield chunk
                
        except Exception as e:
            logger.error(f"聊天智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"处理您的消息时出现了问题: {str(e)}",
                agent_name=self.name
            )
    
    def _build_conversation_history(self, context) -> list:
        """构建对话历史"""
        if not context.messages:
            return []
        
        messages = []
        # 添加系统消息
        messages.append({"role": "system", "content": self.system_prompt})
        
        # 添加对话历史（只保留最近10条消息）
        for msg in context.messages[-10:]:
            if msg.type == MessageType.USER:
                messages.append({"role": "user", "content": msg.content})
            elif msg.type == MessageType.AGENT:
                messages.append({"role": "assistant", "content": msg.content})
        
        return messages
    
    async def _generate_response(self, message: str, history: list, context: Dict[str, Any] = None) -> str:
        """生成响应"""
        try:
            # 使用LLM生成响应
            return await self._generate_llm_response(message, history, context)
        except Exception as e:
            logger.error(f"生成响应失败: {str(e)}")
            raise
    
    async def _generate_llm_response(self, message: str, history: list, context: Dict[str, Any] = None) -> str:
        """使用LLM生成响应"""
        try:
            # 构建完整的消息列表
            messages = history.copy()
            messages.append({"role": "user", "content": message})
            
            # 调用LLM
            response = await self.llm_helper.call(messages)
            
            # 清理响应
            response = response.strip()
            if not response:
                return "我理解您的问题，让我为您提供一些相关信息..."
            
            logger.debug(f"LLM响应: {response[:100]}...")
            return response
            
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            raise
    
    async def _generate_response_stream(self, message: str, history: list, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式生成响应"""
        try:
            # 使用LLM流式生成
            async for chunk in self._generate_llm_response_stream(message, history, context):
                yield chunk
        except Exception as e:
            logger.error(f"流式生成响应失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"生成响应时出现错误: {str(e)}",
                agent_name=self.name
            )
    
    async def _generate_llm_response_stream(self, message: str, history: list, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """使用LLM流式生成响应"""
        try:
            # 构建完整的消息列表
            messages = history.copy()
            messages.append({"role": "user", "content": message})
            
            # 调用LLM流式API
            async for chunk_content in self.llm_helper.call_stream(messages):
                yield StreamChunk(
                    type="content",
                    content=chunk_content,
                    agent_name=self.name
                )
            
            # 发送完成信号
            yield StreamChunk(
                type="final",
                content="",
                agent_name=self.name
            )
            
        except Exception as e:
            logger.error(f"LLM流式调用失败: {str(e)}")
            raise
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取智能体能力"""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [
                "自然语言对话",
                "问题解答",
                "情感交流",
                "上下文理解",
                "智能响应生成"
            ],
            "tools": self.get_available_tools(),
            "llm_available": self.llm_helper is not None
        } 