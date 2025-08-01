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
        logger.info(f"工具驱动智能体 {name} 初始化，绑定工具: {self.bound_tools}")
        
        # 工具信息缓存
        self.tool_info = {}
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"工具驱动智能体 {name} LLM初始化成功")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
        
        # 初始化MCP助手（暂时不初始化，等待外部设置）
        self.mcp_helper = None
        logger.info(f"工具驱动智能体 {name} 初始化完成，等待MCP助手设置")
    
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
            logger.info(f"开始加载绑定工具信息，绑定工具列表: {self.bound_tools}")
            
            # 从所有MCP服务器获取工具信息
            available_services = await self.mcp_helper.get_available_services()
            logger.info(f"实际可用的MCP服务: {available_services}")
            
            for server_name in available_services:
                try:
                    logger.info(f"尝试从服务器 {server_name} 获取工具...")
                    tools = await self.mcp_helper.get_tools(server_name=server_name)
                    logger.info(f"从服务器 {server_name} 获取到 {len(tools)} 个工具")
                    
                    for tool in tools:
                        # 更详细地获取工具名称
                        tool_name = None
                        if hasattr(tool, 'name'):
                            tool_name = getattr(tool, 'name', '')
                        elif isinstance(tool, dict):
                            tool_name = tool.get('name', '')
                        else:
                            tool_name = str(tool)
                        
                        logger.info(f"检查工具: {tool_name} (类型: {type(tool)})")
                        logger.info(f"工具对象: {tool}")
                        
                        if tool_name in self.bound_tools:
                            # 提取工具信息
                            tool_info = {
                                'name': tool_name,
                                'display_name': getattr(tool, 'display_name', ''),
                                'description': getattr(tool, 'description', ''),
                                'input_schema': getattr(tool, 'input_schema', {}),
                                'output_schema': getattr(tool, 'output_schema', {}),
                                'examples': getattr(tool, 'examples', [])
                            }
                            self.tool_info[tool_name] = tool_info
                            logger.info(f"成功加载绑定工具信息: {tool_name}")
                        else:
                            logger.info(f"工具 {tool_name} 不在绑定列表中，跳过")
                except Exception as e:
                    logger.error(f"从服务器 {server_name} 加载工具失败: {str(e)}")
                    logger.error(f"错误详情: {type(e).__name__}: {e}")
            
            logger.info(f"工具驱动智能体 {self.name} 最终加载了 {len(self.tool_info)} 个绑定工具信息")
            logger.info(f"加载的工具: {list(self.tool_info.keys())}")
            
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
请根据用户的需求，选择合适的工具来完成任务。

**重要：当需要使用工具时，请使用以下JSON格式调用工具：**

```json
{
  "tool": "工具名称",
  "参数名1": "参数值1",
  "参数名2": "参数值2"
}
```

**使用步骤：**
1. 分析用户的需求
2. 选择合适的工具
3. 使用JSON格式调用工具
4. 等待工具执行结果
5. 根据结果生成最终回复

**示例：**
如果用户要求打开百度搜索"商汤科技"，你应该这样调用工具：

```json
{
  "tool": "browser_navigate",
  "url": "https://www.baidu.com"
}
```

```json
{
  "tool": "browser_form_input_fill",
  "selector": "input#kw",
  "value": "商汤科技"
}
```

```json
{
  "tool": "browser_press_key",
  "key": "Enter"
}
```

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
            
            # 解析响应中的工具调用
            tools_used = []
            final_response = response_content
            
            # 检查是否包含工具调用
            if "```json" in response_content:
                # 提取JSON格式的工具调用
                import re
                json_blocks = re.findall(r'```json\s*(\{.*?\})\s*```', response_content, re.DOTALL)
                
                for json_block in json_blocks:
                    try:
                        import json
                        tool_call = json.loads(json_block)
                        
                        if "tool" in tool_call:
                            tool_name = tool_call["tool"]
                            parameters = {k: v for k, v in tool_call.items() if k != "tool"}
                            
                            logger.info(f"执行工具调用: {tool_name} 参数: {parameters}")
                            
                            # 执行工具
                            if self.mcp_helper:
                                # 检查工具是否在绑定列表中
                                if tool_name in self.bound_tools:
                                    # 尝试从所有可用服务器中调用工具
                                    result = None
                                    for server_name in await self.mcp_helper.get_available_services():
                                        try:
                                            result = await self.mcp_helper.call_tool(server_name, tool_name, **parameters)
                                            logger.info(f"工具 {tool_name} 在服务器 {server_name} 执行成功")
                                            break
                                        except Exception as e:
                                            logger.debug(f"工具 {tool_name} 在服务器 {server_name} 执行失败: {str(e)}")
                                            continue
                                    
                                    if result is not None:
                                        tools_used.append({
                                            "tool": tool_name,
                                            "parameters": parameters,
                                            "result": result
                                        })
                                        logger.info(f"工具 {tool_name} 执行结果: {result}")
                                    else:
                                        logger.error(f"工具 {tool_name} 在所有服务器上执行失败")
                                else:
                                    logger.error(f"工具 {tool_name} 不在绑定列表中")
                            else:
                                logger.error("MCP助手未初始化")
                            
                    except Exception as e:
                        logger.error(f"解析工具调用失败: {str(e)}")
                        logger.error(f"JSON块: {json_block}")
            
            # 如果有工具调用，生成最终响应
            if tools_used:
                # 重新调用LLM生成包含工具执行结果的响应
                tool_results = "\n".join([
                    f"工具 {tool['tool']} 执行结果: {tool['result']}"
                    for tool in tools_used
                ])
                
                final_response = await self.llm_helper.call(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                        {"role": "assistant", "content": response_content},
                        {"role": "user", "content": f"工具执行结果:\n{tool_results}\n\n请根据工具执行结果生成最终回复。"}
                    ]
                )
            
            # 创建响应消息
            response = self.create_message(
                content=final_response,
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
        logger.info(f"尝试执行工具: {tool_name}")
        logger.info(f"当前绑定工具列表: {self.bound_tools}")
        
        if not self.mcp_helper:
            raise Exception("MCP助手未初始化")
        
        # 检查工具是否在绑定列表中
        if tool_name not in self.bound_tools:
            logger.error(f"工具 {tool_name} 不在绑定列表中，无法执行")
            logger.error(f"绑定工具列表: {self.bound_tools}")
            raise Exception(f"工具 {tool_name} 不在绑定列表中，无法执行")
        
        try:
            result = await self.mcp_helper.execute_tool(tool_name, parameters)
            logger.info(f"工具 {tool_name} 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {str(e)}")
            raise 