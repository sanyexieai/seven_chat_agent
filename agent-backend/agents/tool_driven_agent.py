from typing import Dict, Any, AsyncGenerator, List
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
from utils.mcp_helper import get_mcp_helper
import asyncio
import json
import uuid

logger = get_logger("tool_driven_agent")

class ToolDrivenAgent(BaseAgent):
    """纯工具驱动智能体
    
    通过绑定MCP工具，根据工具的内容和参数反向生成提示词。
    这种智能体专注于工具的使用，会根据绑定的工具自动生成相应的系统提示词。
    """
    
    def __init__(self, name: str, description: str, bound_tools: List[str] = None):
        super().__init__(name, description)
        
        # 绑定的工具列表（工具名称）
        self.bound_tools = bound_tools or []
        
        # 工具信息缓存
        self.tool_info = {}
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"工具驱动智能体 {name} LLM初始化成功")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
        
        # 初始化MCP助手
        try:
            self.mcp_helper = get_mcp_helper()
            logger.info(f"工具驱动智能体 {name} MCP助手初始化成功")
        except Exception as e:
            logger.warning(f"MCP助手初始化失败: {str(e)}")
            self.mcp_helper = None
    
    def set_bound_tools(self, tools: List[str]):
        """设置绑定的工具列表"""
        self.bound_tools = tools
        logger.info(f"智能体 {self.name} 绑定工具已更新: {tools}")
    
    def get_bound_tools(self) -> List[str]:
        """获取绑定的工具列表"""
        return self.bound_tools
    
    async def load_tool_info(self):
        """加载工具信息"""
        if not self.mcp_helper:
            logger.warning("MCP助手未初始化，无法加载工具信息")
            return
        
        try:
            self.tool_info = {}
            
            # 从所有MCP服务器获取工具信息
            for server_name in self.mcp_helper.get_server_names():
                try:
                    tools = await self.mcp_helper.get_tools(server_name=server_name)
                    for tool in tools:
                        tool_name = getattr(tool, 'name', '') or tool.get('name', '')
                        if tool_name in self.bound_tools:
                            # 提取工具信息
                            tool_info = {
                                'name': tool_name,
                                'display_name': getattr(tool, 'display_name', '') or tool.get('displayName', ''),
                                'description': getattr(tool, 'description', '') or tool.get('description', ''),
                                'input_schema': getattr(tool, 'input_schema', {}) or tool.get('inputSchema', {}),
                                'output_schema': getattr(tool, 'output_schema', {}) or tool.get('outputSchema', {}),
                                'examples': getattr(tool, 'examples', []) or tool.get('examples', [])
                            }
                            self.tool_info[tool_name] = tool_info
                            logger.info(f"加载工具信息: {tool_name}")
                except Exception as e:
                    logger.warning(f"从服务器 {server_name} 加载工具失败: {str(e)}")
            
            logger.info(f"工具驱动智能体 {self.name} 加载了 {len(self.tool_info)} 个工具信息")
            
        except Exception as e:
            logger.error(f"加载工具信息失败: {str(e)}")
    
    def generate_system_prompt(self) -> str:
        """根据绑定的工具生成系统提示词"""
        if not self.tool_info:
            return """你是一个工具驱动的AI助手。请根据用户的需求选择合适的工具来完成任务。"""
        
        prompt_parts = [
            "你是一个工具驱动的AI助手，专门使用以下工具来帮助用户：\n\n"
        ]
        
        for tool_name, tool_info in self.tool_info.items():
            prompt_parts.append(f"工具名称: {tool_name}")
            if tool_info.get('display_name'):
                prompt_parts.append(f"显示名称: {tool_info['display_name']}")
            if tool_info.get('description'):
                prompt_parts.append(f"描述: {tool_info['description']}")
            
            # 添加输入参数信息
            input_schema = tool_info.get('input_schema', {})
            if input_schema:
                prompt_parts.append("输入参数:")
                if isinstance(input_schema, dict):
                    for param_name, param_info in input_schema.items():
                        if isinstance(param_info, dict):
                            param_type = param_info.get('type', 'unknown')
                            param_desc = param_info.get('description', '')
                            prompt_parts.append(f"  - {param_name} ({param_type}): {param_desc}")
                        else:
                            prompt_parts.append(f"  - {param_name}: {param_info}")
            
            # 添加使用示例
            examples = tool_info.get('examples', [])
            if examples:
                prompt_parts.append("使用示例:")
                for example in examples[:2]:  # 只显示前2个示例
                    if isinstance(example, dict):
                        prompt_parts.append(f"  - {example}")
                    else:
                        prompt_parts.append(f"  - {example}")
            
            prompt_parts.append("")  # 空行分隔
        
        prompt_parts.append("""
请根据用户的需求，选择合适的工具来完成任务。在回复中，请：
1. 分析用户的需求
2. 选择合适的工具
3. 说明如何使用工具
4. 提供清晰的解释和建议

如果用户的需求无法通过现有工具完成，请说明原因并建议替代方案。
""")
        
        return "\n".join(prompt_parts)
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        try:
            # 确保工具信息已加载
            if not self.tool_info:
                await self.load_tool_info()
            
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
            
            # 生成系统提示词
            system_prompt = self.generate_system_prompt()
            logger.info(f"工具驱动智能体 {self.name} 生成的系统提示词: {system_prompt}")
            
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
            response_content = await self.llm_helper.call(
                messages=[
                    {"role": "system", "content": system_prompt}
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
            
            logger.info(f"工具驱动智能体 {self.name} 处理消息完成")
            return response
            
        except Exception as e:
            logger.error(f"工具驱动智能体处理消息失败: {str(e)}")
            error_response = self.create_message(
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}",
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            return error_response
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            # 确保工具信息已加载
            if not self.tool_info:
                await self.load_tool_info()
            
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
            
            # 生成系统提示词
            system_prompt = self.generate_system_prompt()
            
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
            full_response = ""
            async for chunk in self.llm_helper.call_stream(
                messages=[
                    {"role": "system", "content": system_prompt}
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
            
            logger.info(f"工具驱动智能体 {self.name} 流式处理消息完成")
            
        except Exception as e:
            logger.error(f"工具驱动智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                type="error",
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}"
            )
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        if not self.mcp_helper:
            raise Exception("MCP助手未初始化")
        
        try:
            result = await self.mcp_helper.execute_tool(tool_name, parameters)
            logger.info(f"工具 {tool_name} 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {str(e)}")
            raise 