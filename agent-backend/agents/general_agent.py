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
    这种智能体完全依赖提示词来定义行为，支持工具调用和知识库查询。
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
        
        # 绑定工具配置
        self.bound_tools = []
        
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
    
    def set_bound_tools(self, tools: List[Any]):
        """设置绑定的工具"""
        self.bound_tools = tools
        logger.info(f"智能体 {self.name} 绑定工具: {len(tools)} 个")
    
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
    
    def _build_enhanced_system_prompt(self, knowledge_context: str = "") -> str:
        """构建增强的系统提示词"""
        enhanced_prompt = self.system_prompt
        
        # 添加知识库信息
        if knowledge_context:
            enhanced_prompt += f"\n\n以下是相关的知识库信息，请基于这些信息回答用户问题：\n{knowledge_context}"
            enhanced_prompt += "\n\n请结合知识库信息，提供准确、详细的回答。如果知识库信息不足以回答问题，请说明并提供一般性建议。"
        
        # 添加工具信息
        if self.bound_tools:
            tools_description = "\n\n你可以使用以下工具：\n"
            for t in self.bound_tools:
                if isinstance(t, str):
                    tools_description += f"- {t}\n"
                elif isinstance(t, dict):
                    server = t.get('server_name') or t.get('server')
                    name = t.get('name') or t.get('tool_name')
                    if server and name:
                        tools_description += f"- {server}_{name}\n"
            
            tools_description += "\n\n当需要使用工具时，请使用以下格式：\n"
            tools_description += "TOOL_CALL: <工具名称> <参数>\n"
            tools_description += "例如：TOOL_CALL: ddg_search query=商汤科技\n"
            tools_description += "我会自动执行工具调用并返回结果。"
            
            enhanced_prompt += tools_description
            logger.info(f"智能体 {self.name} 的系统提示词已增强，包含 {len(self.bound_tools)} 个工具")
        
        return enhanced_prompt
    
    def _parse_tool_calls(self, response: str) -> List[str]:
        """解析响应中的工具调用指令"""
        tool_calls = []
        lines = response.split('\n')
        
        for line in lines:
            if line.strip().startswith('TOOL_CALL:'):
                tool_call = line.strip().replace('TOOL_CALL:', '').strip()
                tool_calls.append(tool_call)
                logger.info(f"✅ 找到工具调用: '{tool_call}'")
        
        return tool_calls
    
    def _build_tool_mapping(self) -> tuple[set, Dict[str, str]]:
        """构建工具映射关系"""
        bound_tool_keys = set()
        tool_to_server: Dict[str, str] = {}
        
        for t in self.bound_tools:
            if isinstance(t, str):
                if '_' in t:
                    s, n = t.split('_', 1)
                    bound_tool_keys.add(t)
                    tool_to_server[n] = s
            elif isinstance(t, dict):
                s = t.get('server_name') or t.get('server')
                n = t.get('name') or t.get('tool_name')
                if s and n:
                    bound_tool_keys.add(f"{s}_{n}")
                    tool_to_server[n] = s
        
        return bound_tool_keys, tool_to_server
    
    def _infer_default_tool_calls(self, user_message: str) -> List[str]:
        """在LLM未显式发出 TOOL_CALL 时，根据已绑定工具推断一个或多个默认调用。
        策略：优先选择名称中包含 'search' 的工具；否则选择第一个绑定工具。
        返回形如 ['server_tool query=xxx'] 的调用列表。
        """
        if not self.bound_tools:
            return []
        candidate_calls: List[str] = []
        fallback_call: str = ""
        lower_msg = (user_message or "").strip()
        for t in self.bound_tools:
            if isinstance(t, str):
                server_tool = t
                if not fallback_call:
                    fallback_call = f"{server_tool} {lower_msg}" if lower_msg else server_tool
                if 'search' in server_tool.lower():
                    candidate_calls.append(f"{server_tool} query={lower_msg}" if lower_msg else server_tool)
            elif isinstance(t, dict):
                server = t.get('server_name') or t.get('server')
                name = t.get('name') or t.get('tool_name')
                if server and name:
                    server_tool = f"{server}_{name}"
                    if not fallback_call:
                        fallback_call = f"{server_tool} {lower_msg}" if lower_msg else server_tool
                    if 'search' in name.lower() or 'search' in server.lower():
                        candidate_calls.append(f"{server_tool} query={lower_msg}" if lower_msg else server_tool)
        # 去重，保持顺序
        seen = set()
        ordered = [c for c in candidate_calls if not (c in seen or seen.add(c))]
        if ordered:
            return [ordered[0]]
        return [fallback_call] if fallback_call else []

    async def _satisfaction_check_and_refine(self, user_message: str, initial_answer: str, tool_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """让LLM评估是否已满足需求，必要时给出改进的查询。返回 { satisfied: bool, refined_query: Optional[str] }"""
        try:
            instruction = (
                "你是一个审核助手。给定用户问题、初步回答以及工具检索结果，判断是否已足够回答用户。"
                "仅返回JSON，格式为 {\"satisfied\": true|false, \"refined_query\": string|null}。"
            )
            payload = {
                "role": "system",
                "content": instruction
            }
            context_blob = {
                "user_message": user_message,
                "initial_answer": initial_answer,
                "tool_results": tool_results,
            }
            resp = await self.llm_helper.call(messages=[payload, {"role": "user", "content": json.dumps(context_blob, ensure_ascii=False)}])
            try:
                parsed = json.loads(resp)
                return {
                    "satisfied": bool(parsed.get("satisfied", False)),
                    "refined_query": parsed.get("refined_query")
                }
            except Exception:
                lower = (resp or "").lower()
                return {
                    "satisfied": ("true" in lower and "false" not in lower),
                    "refined_query": None
                }
        except Exception as e:
            logger.warning(f"满意度评估失败: {str(e)}")
            return {"satisfied": False, "refined_query": None}
    
    async def _execute_tool_call(self, tool_call: str, bound_tool_keys: set, tool_to_server: Dict[str, str], mcp_helper) -> tuple[str, str]:
        """执行单个工具调用"""
        try:
            # 解析工具名称和参数
            parts = tool_call.split(' ', 1)
            if len(parts) < 2:
                return f"工具调用格式不正确: {tool_call}", ""
            
            tool_name = parts[0].strip()
            tool_params = parts[1].strip()
            
            # 检查工具是否在绑定列表中
            if not (tool_name in bound_tool_keys or tool_name in tool_to_server):
                return f"工具 {tool_name} 未绑定，无法执行", ""
            
            # 解析参数
            params = {}
            if '=' in tool_params:
                for param in tool_params.split():
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key.strip()] = value.strip()
            else:
                # 如果没有=，假设是查询参数
                params['query'] = tool_params
            
            # 从工具名中提取服务器名和工具名
            if '_' in tool_name:
                server_name, actual_tool_name = tool_name.split('_', 1)
            else:
                actual_tool_name = tool_name
                server_name = tool_to_server.get(actual_tool_name)
                if not server_name:
                    available_services = await mcp_helper.get_available_services()
                    if available_services:
                        server_name = available_services[0]
                    else:
                        raise RuntimeError("没有可用的MCP服务器")
            
            # 调用MCP工具
            tool_result = await mcp_helper.call_tool(
                server_name=server_name,
                tool_name=actual_tool_name,
                **params
            )
            
            return tool_result, tool_name
            
        except Exception as e:
            logger.error(f"执行工具调用失败: {str(e)}")
            return f"工具执行失败: {str(e)}", ""
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息（非流式）"""
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
                    db_session = context.get('db_session') if context else None
                    knowledge_context = await self.query_knowledge_base(message, db_session)
                except Exception as e:
                    logger.warning(f"知识库查询失败: {str(e)}")
            
            # 构建增强的系统提示词
            enhanced_system_prompt = self._build_enhanced_system_prompt(knowledge_context)
            
            # 调用LLM生成响应
            try:
                response_content = await self.llm_helper.call(
                    messages=[
                        {"role": "system", "content": enhanced_system_prompt}
                    ] + conversation_history
                )
            except Exception as e:
                logger.warning(f"LLM调用失败，使用模拟响应: {str(e)}")
                response_content = f"您好！我是{self.name}智能体。我收到了您的消息：'{message}'。如果您需要真实的AI响应，请确保LLM服务正在运行。"
            
            # 工具阶段：先解析显式调用，否则走默认推断
            tools_used = []
            tool_results_pack = []
            tool_calls = []
            if self.bound_tools:
                if "TOOL_CALL:" in response_content:
                    tool_calls = self._parse_tool_calls(response_content)
                if not tool_calls:
                    tool_calls = self._infer_default_tool_calls(message)
                    if tool_calls:
                        logger.info(f"未发现显式工具调用，已自动推断调用: {tool_calls}")
                try:
                    if tool_calls:
                        bound_tool_keys, tool_to_server = self._build_tool_mapping()
                        from main import agent_manager
                        if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                            mcp_helper = agent_manager.mcp_helper
                            for tc in tool_calls:
                                tool_result, tool_name = await self._execute_tool_call(tc, bound_tool_keys, tool_to_server, mcp_helper)
                                if tool_name:
                                    response_content += f"\n\n🔍 工具 {tool_name} 执行结果:\n{tool_result}"
                                    tools_used.append(tool_name)
                                    tool_results_pack.append({"tool": tool_name, "query": tc, "result": tool_result})
                        else:
                            logger.warning("MCP助手未初始化，无法执行工具调用")
                except Exception as e:
                    logger.error(f"工具调用处理失败: {str(e)}")
                    response_content += f"\n\n工具调用失败: {str(e)}"

            # 满意度检查与一次性优化重试
            if tool_results_pack:
                check = await self._satisfaction_check_and_refine(message, response_content, tool_results_pack)
                if not check.get("satisfied") and check.get("refined_query"):
                    refined = check["refined_query"]
                    secondary_calls = self._infer_default_tool_calls(refined)
                    try:
                        if secondary_calls:
                            bound_tool_keys, tool_to_server = self._build_tool_mapping()
                            from main import agent_manager
                            if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                                mcp_helper = agent_manager.mcp_helper
                                for tc in secondary_calls:
                                    tool_result, tool_name = await self._execute_tool_call(tc, bound_tool_keys, tool_to_server, mcp_helper)
                                    if tool_name:
                                        response_content += f"\n\n🔁 二次检索 {tool_name}（优化查询）执行结果:\n{tool_result}"
                                        tools_used.append(tool_name)
                                        tool_results_pack.append({"tool": tool_name, "query": tc, "result": tool_result, "refined": True})
                            else:
                                logger.warning("MCP助手未初始化，无法执行工具调用（优化轮次）")
                    except Exception as e:
                        logger.error(f"优化轮次工具调用失败: {str(e)}")
                        response_content += f"\n\n优化轮次工具调用失败: {str(e)}"

            # 创建响应消息
            response = self.create_message(
                content=response_content,
                message_type=MessageType.AGENT,
                agent_name=self.name
            )
            
            # 更新上下文
            agent_context.messages.append(response)
            self.update_context(user_id, agent_context)
            
            # 保存工具使用信息到元数据
            if tools_used:
                response.metadata = {"tools_used": tools_used}
            
            logger.info(f"通用智能体 {self.name} 处理消息完成，使用工具: {tools_used}")
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
            
            # 查询知识库（如果有绑定的话）
            knowledge_context = ""
            if self.bound_knowledge_bases:
                try:
                    db_session = context.get('db_session') if context else None
                    knowledge_context = await self.query_knowledge_base(message, db_session)
                except Exception as e:
                    logger.warning(f"知识库查询失败: {str(e)}")
            
            # 构建增强的系统提示词
            enhanced_system_prompt = self._build_enhanced_system_prompt(knowledge_context)
            
            # 流式调用LLM
            full_response = ""
            chunk_count = 0
            async for chunk in self.llm_helper.call_stream(
                messages=[
                    {"role": "system", "content": enhanced_system_prompt}
                ] + conversation_history
            ):
                full_response += chunk
                chunk_count += 1
                yield StreamChunk(
                    chunk_id=f"{user_id}_{chunk_count}",
                    session_id=agent_context.session_id,
                    type="content",
                    content=chunk,
                    agent_name=self.name
                )
            
            # 工具阶段：先解析显式调用，否则走默认推断
            tools_used = []
            tool_results_pack = []
            tool_calls = []
            if self.bound_tools:
                if "TOOL_CALL:" in full_response:
                    tool_calls = self._parse_tool_calls(full_response)
                if not tool_calls:
                    tool_calls = self._infer_default_tool_calls(message)
                    if tool_calls:
                        logger.info(f"未发现显式工具调用，已自动推断调用: {tool_calls}")
                try:
                    if tool_calls:
                        bound_tool_keys, tool_to_server = self._build_tool_mapping()
                        from main import agent_manager
                        if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                            mcp_helper = agent_manager.mcp_helper
                            for tc in tool_calls:
                                tool_result, tool_name = await self._execute_tool_call(tc, bound_tool_keys, tool_to_server, mcp_helper)
                                if tool_name:
                                    formatted_result = f"\n\n🔍 工具 {tool_name} 执行结果:\n{tool_result}\n"
                                    # 将工具结果也累积到最终全文中，确保前端即便只展示最终块也能看到
                                    full_response += formatted_result
                                    yield StreamChunk(
                                        chunk_id=f"{user_id}_tool_{tool_name}",
                                        session_id=agent_context.session_id,
                                        type="tool_result",
                                        content=formatted_result,
                                        metadata={"tool_name": tool_name},
                                        agent_name=self.name
                                    )
                                    # 兼容前端仅展示 content 类型的情况，再追加一条内容块
                                    yield StreamChunk(
                                        chunk_id=f"{user_id}_tool_{tool_name}_content",
                                        session_id=agent_context.session_id,
                                        type="content",
                                        content=formatted_result,
                                        agent_name=self.name
                                    )
                                    tools_used.append(tool_name)
                                    tool_results_pack.append({"tool": tool_name, "query": tc, "result": tool_result})
                        else:
                            logger.warning("MCP助手未初始化，无法执行工具调用")
                except Exception as e:
                    logger.error(f"工具调用处理失败: {str(e)}")
                    yield StreamChunk(
                        chunk_id=f"{user_id}_tool_error",
                        session_id=agent_context.session_id,
                        type="tool_error",
                        content=f"\n\n工具调用失败: {str(e)}",
                        agent_name=self.name
                    )

            # 满意度检查与一次优化轮
            if tool_results_pack:
                check = await self._satisfaction_check_and_refine(message, full_response, tool_results_pack)
                if not check.get("satisfied") and check.get("refined_query"):
                    refined = check["refined_query"]
                    secondary_calls = self._infer_default_tool_calls(refined)
                    try:
                        if secondary_calls:
                            bound_tool_keys, tool_to_server = self._build_tool_mapping()
                            from main import agent_manager
                            if agent_manager and hasattr(agent_manager, 'mcp_helper'):
                                mcp_helper = agent_manager.mcp_helper
                                for tc in secondary_calls:
                                    tool_result, tool_name = await self._execute_tool_call(tc, bound_tool_keys, tool_to_server, mcp_helper)
                                    if tool_name:
                                        formatted_result = f"\n\n🔁 二次检索 {tool_name}（优化查询）执行结果:\n{tool_result}\n"
                                        full_response += formatted_result
                                        yield StreamChunk(
                                            chunk_id=f"{user_id}_tool2_{tool_name}",
                                            session_id=agent_context.session_id,
                                            type="tool_result",
                                            content=formatted_result,
                                            metadata={"tool_name": tool_name, "refined": True},
                                            agent_name=self.name
                                        )
                                        # 兼容前端仅展示 content 类型的情况，再追加一条内容块
                                        yield StreamChunk(
                                            chunk_id=f"{user_id}_tool2_{tool_name}_content",
                                            session_id=agent_context.session_id,
                                            type="content",
                                            content=formatted_result,
                                            agent_name=self.name
                                        )
                                        tools_used.append(tool_name)
                                        tool_results_pack.append({"tool": tool_name, "query": tc, "result": tool_result, "refined": True})
                            else:
                                logger.warning("MCP助手未初始化，无法执行工具调用（优化轮次）")
                    except Exception as e:
                        logger.error(f"优化轮次工具调用失败: {str(e)}")
                        yield StreamChunk(
                            chunk_id=f"{user_id}_tool2_error",
                            session_id=agent_context.session_id,
                            type="tool_error",
                            content=f"\n\n优化轮次工具调用失败: {str(e)}",
                            agent_name=self.name
                        )

            # 发送最终响应块，包含完整的响应内容
            yield StreamChunk(
                chunk_id=f"{user_id}_final",
                session_id=agent_context.session_id,
                type="final",
                content=full_response,
                metadata={"tools_used": tools_used},
                agent_name=self.name
            )
            
            # 更新对话历史
            agent_context.messages.append(AgentMessage(
                message_id=str(uuid.uuid4()),
                user_id=user_id,
                type=MessageType.USER,
                content=message,
                timestamp=asyncio.get_event_loop().time()
            ))
            
            agent_context.messages.append(AgentMessage(
                message_id=str(uuid.uuid4()),
                user_id=user_id,
                type=MessageType.AGENT,
                content=full_response,
                timestamp=asyncio.get_event_loop().time(),
                metadata={"tools_used": tools_used}
            ))
            
            self.update_context(user_id, agent_context)
            logger.info(f"智能体 {self.name} 流式处理消息完成，响应长度: {len(full_response)}, 使用工具: {tools_used}")
            
        except Exception as e:
            logger.error(f"通用智能体流式处理消息失败: {str(e)}")
            yield StreamChunk(
                chunk_id=f"{user_id}_error",
                session_id=agent_context.session_id,
                type="error",
                content=f"抱歉，处理您的消息时出现了错误: {str(e)}",
                agent_name=self.name
            ) 