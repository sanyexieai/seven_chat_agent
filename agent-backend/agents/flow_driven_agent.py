from typing import Dict, Any, AsyncGenerator, List, Optional
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
import asyncio
import json
import uuid
from enum import Enum

logger = get_logger("flow_driven_agent")

class NodeType(str, Enum):
    """节点类型枚举"""
    AGENT = "agent"           # 智能体节点
    CONDITION = "condition"    # 条件节点
    ACTION = "action"         # 动作节点
    LLM = "llm"               # LLM 调用节点
    TOOL = "tool"             # 工具调用节点

class FlowNode:
    """流程图节点"""
    def __init__(self, node_id: str, node_type: NodeType, name: str, config: Dict[str, Any] = None):
        self.id = node_id
        self.type = node_type
        self.name = name
        self.config = config or {}
        self.position = self.config.get('position', {'x': 0, 'y': 0})
        self.connections = self.config.get('connections', [])  # 连接到的其他节点ID列表

class FlowDrivenAgent(BaseAgent):
    """流程图驱动智能体
    
    通过在线编辑流程图的形式，将其他基础智能体作为节点创建复杂的多智能体组合。
    支持条件分支、循环、并行执行等复杂的流程控制。
    """
    
    def __init__(self, name: str, description: str, flow_config: Dict[str, Any] = None):
        super().__init__(name, description)
        
        # 流程图配置
        self.flow_config = flow_config or {}
        self.nodes = {}  # 节点字典 {node_id: FlowNode}
        self.start_node_id = None  # 起始节点ID
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"流程图驱动智能体 {name} 初始化成功")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
        
        # 加载流程图配置
        self._load_flow_config()
        logger.info(f"流程图驱动智能体 {name} 初始化完成")
    
    def _load_flow_config(self):
        """加载流程图配置"""
        self.nodes = {}
        self.start_node_id = None
        
        try:
            if not self.flow_config:
                logger.warning("流程图配置为空")
                return
            
            # 解析节点配置
            nodes_config = self.flow_config.get('nodes', [])
            logger.info(f"开始解析 {len(nodes_config)} 个节点")
            
            for node_config in nodes_config:
                node_id = node_config.get('id')
                node_type = NodeType(node_config.get('type', 'agent'))
                node_data = node_config.get('data', {})
                node_name = node_data.get('label', '')
                
                # 从data中提取config
                node_config_dict = node_data.get('config', {})
                
                logger.info(f"解析节点 {node_id}: type={node_type}, name={node_name}, config={node_config_dict}")
                
                node = FlowNode(node_id, node_type, node_name, node_config_dict)
                self.nodes[node_id] = node
                
                # 检查是否为起始节点
                if node_data.get('isStartNode', False):
                    self.start_node_id = node_id
                    logger.info(f"设置起始节点: {node_id}")
            
            # 如果没有找到起始节点，使用第一个节点作为起始节点
            if not self.start_node_id and nodes_config:
                self.start_node_id = nodes_config[0]['id']
                logger.info(f"未找到起始节点，使用第一个节点作为起始节点: {self.start_node_id}")
            
            logger.info(f"加载了 {len(self.nodes)} 个流程图节点")
            logger.info(f"起始节点: {self.start_node_id}")
            
            # 打印所有节点的配置
            for node_id, node in self.nodes.items():
                logger.info(f"节点 {node_id} 配置: {node.config}")
            
        except Exception as e:
            logger.error(f"加载流程图配置失败: {str(e)}")
    
    def set_flow_config(self, config: Dict[str, Any]):
        """设置流程图配置"""
        self.flow_config = config
        self._load_flow_config()
        logger.info(f"智能体 {self.name} 流程图配置已更新")
    
    def get_flow_config(self) -> Dict[str, Any]:
        """获取流程图配置"""
        return self.flow_config
    
    def add_node(self, node_id: str, node_type: NodeType, name: str, config: Dict[str, Any] = None):
        """添加节点"""
        node = FlowNode(node_id, node_type, name, config)
        self.nodes[node_id] = node
        logger.info(f"添加节点: {node_id} ({node_type.value})")
    
    def remove_node(self, node_id: str):
        """删除节点"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"删除节点: {node_id}")
    
    def connect_nodes(self, from_node_id: str, to_node_id: str):
        """连接节点"""
        if from_node_id in self.nodes and to_node_id in self.nodes:
            if to_node_id not in self.nodes[from_node_id].connections:
                self.nodes[from_node_id].connections.append(to_node_id)
                logger.info(f"连接节点: {from_node_id} -> {to_node_id}")
    
    async def execute_flow(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """执行流程图"""
        if not self.start_node_id:
            return AgentMessage(
                id=str(uuid.uuid4()),
                type=MessageType.AGENT,
                content="流程图未配置起始节点，无法执行。",
                agent_name=self.name,
                metadata={'flow_executed': False, 'error': 'no_start_node'}
            )
        
        try:
            logger.info(f"开始执行流程图，起始节点: {self.start_node_id}")
            logger.info(f"用户消息: {message}")
            
            # 直接执行起始节点，传入用户消息
            response = await self._execute_node(self.start_node_id, user_id, message, context)
            
            logger.info(f"流程图执行完成")
            return response
            
        except Exception as e:
            logger.error(f"执行流程图失败: {str(e)}")
            return AgentMessage(
                id=str(uuid.uuid4()),
                type=MessageType.AGENT,
                content=f"流程图执行失败: {str(e)}",
                agent_name=self.name,
                metadata={'flow_executed': False, 'error': str(e)}
            )
    
    async def _execute_node(self, node_id: str, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行节点"""
        node = self.nodes.get(node_id)
        if not node:
            raise ValueError(f"节点 {node_id} 不存在")
        
        logger.info(f"执行节点: {node_id} ({node.type})")
        
        try:
            if node.type == NodeType.AGENT:
                return await self._execute_agent_node(node, user_id, message, context)
            elif node.type == NodeType.CONDITION:
                return await self._execute_condition_node(node, user_id, message, context)
            elif node.type == NodeType.ACTION:
                return await self._execute_action_node(node, user_id, message, context)
            elif node.type == NodeType.LLM:
                return await self._execute_llm_node(node, user_id, message, context)
            elif node.type == NodeType.TOOL:
                return await self._execute_tool_node(node, user_id, message, context)
            else:
                raise ValueError(f"不支持的节点类型: {node.type}")
        except Exception as e:
            logger.error(f"执行节点 {node_id} 失败: {str(e)}")
            raise

    def _get_flow_state(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """从上下文获取/初始化流程状态容器。"""
        if context is None:
            context = {}
        state = context.get('flow_state')
        if state is None:
            state = {}
            context['flow_state'] = state
        return state

    def _render_template_value(self, value: Any, variables: Dict[str, Any]) -> Any:
        """渲染字符串中的 {{var}} 模板；对 dict/list 递归处理。"""
        if isinstance(value, str):
            result = value
            for k, v in variables.items():
                placeholder = f"{{{{{k}}}}}"
                try:
                    result = result.replace(placeholder, str(v))
                except Exception:
                    pass
            return result
        if isinstance(value, dict):
            return {k: self._render_template_value(v, variables) for k, v in value.items()}
        if isinstance(value, list):
            return [self._render_template_value(v, variables) for v in value]
        return value

    async def _execute_llm_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行 LLM 节点。
        配置：
        - system_prompt: 可选，系统提示词模板
        - user_prompt: 可选，用户提示词模板；若缺省则使用传入 message
        - save_as: 可选，将输出保存到 flow_state 的变量名，默认 'last_output'
        """
        flow_state = self._get_flow_state(context)
        variables = {**flow_state, 'message': message}
        system_prompt = self._render_template_value(node.config.get('system_prompt', ''), variables)
        user_prompt = self._render_template_value(node.config.get('user_prompt', message), variables)
        save_as = node.config.get('save_as', 'last_output')
        
        logger.info(f"LLM节点 {node.id} 开始执行")
        try:
            if system_prompt:
                content = await self.llm_helper.call(messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ])
            else:
                content = await self.llm_helper.call(messages=[
                    {"role": "user", "content": user_prompt}
                ])
            flow_state[save_as] = content
            flow_state['last_output'] = content
            logger.info(f"LLM节点 {node.id} 执行完成，保存为 {save_as}")
        except Exception as e:
            logger.error(f"LLM节点执行失败: {str(e)}")
            content = f"LLM节点执行失败: {str(e)}"
            flow_state[save_as] = content
            flow_state['last_output'] = content
        
        # 跳转到下一个节点或返回
        if node.connections:
            next_node_id = node.connections[0]
            return await self._execute_node(next_node_id, user_id, message, context)
        return AgentMessage(
            id=str(uuid.uuid4()),
            type=MessageType.AGENT,
            content=flow_state['last_output'],
            agent_name=self.name,
            metadata={'node_id': node.id, 'node_type': node.type.value}
        )

    async def _execute_tool_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行 工具 节点。
        配置：
        - server: 服务名（可选，如果工具名包含 server_ 前缀可缺省）
        - tool: 工具名（必填）
        - params: dict/str 参数模板，支持 {{message}} / {{last_output}} / 其它 flow_state 变量
        - save_as: 可选，保存结果变量名，默认 'last_output'
        - append_to_output: bool，可选，是否将结果附加到 last_output（默认 True）
        """
        flow_state = self._get_flow_state(context)
        variables = {**flow_state, 'message': message}
        server = self._render_template_value(node.config.get('server'), variables)
        tool = self._render_template_value(node.config.get('tool'), variables)
        raw_params = node.config.get('params', {})
        params = self._render_template_value(raw_params, variables)
        save_as = node.config.get('save_as', 'last_output')
        append_to_output = node.config.get('append_to_output', True)
        
        if not tool:
            raise ValueError(f"工具节点 {node.id} 未配置 tool 名称")
        
        try:
            from main import agent_manager
            if not agent_manager or not getattr(agent_manager, 'mcp_helper', None):
                raise RuntimeError("MCP助手未初始化")
            mcp_helper = agent_manager.mcp_helper
            actual_server = server
            actual_tool = tool
            # 如果 tool 类似 server_tool 合并在一起，则拆分
            if '_' in tool and not server:
                parts = tool.split('_', 1)
                actual_server = parts[0]
                actual_tool = parts[1]
            if not actual_server:
                # 若仍无服务名，选第一个可用服务
                services = await mcp_helper.get_available_services()
                if not services:
                    raise RuntimeError("没有可用的MCP服务")
                actual_server = services[0]
            logger.info(f"工具节点 {node.id} 调用: {actual_server}.{actual_tool} 参数: {params}")
            result = await mcp_helper.call_tool(server_name=actual_server, tool_name=actual_tool, **(params if isinstance(params, dict) else {"query": str(params)}))
            try:
                serializable = json.dumps(result, ensure_ascii=False)
                result_text = serializable
            except Exception:
                result_text = str(result)
            
            # 保存结果
            flow_state[save_as] = result
            if append_to_output:
                prev = str(flow_state.get('last_output', ''))
                flow_state['last_output'] = f"{prev}\n\n🔧 工具 {actual_server}_{actual_tool} 结果:\n{result_text}" if prev else result_text
            else:
                flow_state['last_output'] = result_text
            logger.info(f"工具节点 {node.id} 执行完成，结果已保存为 {save_as}")
        except Exception as e:
            logger.error(f"工具节点执行失败: {str(e)}")
            flow_state['last_output'] = f"工具节点执行失败: {str(e)}"
            flow_state[save_as] = None
        
        # 跳转到下一个节点或返回
        if node.connections:
            next_node_id = node.connections[0]
            return await self._execute_node(next_node_id, user_id, message, context)
        return AgentMessage(
            id=str(uuid.uuid4()),
            type=MessageType.AGENT,
            content=str(flow_state.get('last_output', '')),
            agent_name=self.name,
            metadata={'node_id': node.id, 'node_type': node.type.value}
        )
    
    async def _execute_agent_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行智能体节点"""
        agent_name = node.config.get('agent_name')
        if not agent_name:
            raise ValueError(f"智能体节点 {node.id} 未配置智能体名称")
        
        try:
            # 尝试从AgentManager获取对应的智能体
            from main import agent_manager
            if agent_manager and agent_name in agent_manager.agents:
                # 使用实际的智能体
                target_agent = agent_manager.agents[agent_name]
                response = await target_agent.process_message(user_id, message, context)
                return response
            else:
                # 如果找不到智能体，使用LLM模拟
                prompt = f"作为智能体 '{agent_name}'，请处理以下用户消息：\n{message}"
                response = await self.llm_helper.call(
                    messages=[{"role": "user", "content": prompt}]
                )
                
                return AgentMessage(
                    id=str(uuid.uuid4()),
                    type=MessageType.AGENT,
                    content=response,
                    agent_name=f"{self.name}->{agent_name}",
                    metadata={'node_id': node.id, 'node_type': node.type.value, 'agent_name': agent_name}
                )
        except Exception as e:
            logger.error(f"执行智能体节点失败: {str(e)}")
            raise
    
    async def _execute_condition_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行条件节点"""
        condition = node.config.get('condition', '')
        if not condition:
            raise ValueError(f"条件节点 {node.id} 未配置条件")
        
        # 使用LLM判断条件，支持引用 flow_state
        flow_state = self._get_flow_state(context)
        variables = {**flow_state, 'message': message}
        rendered_condition = self._render_template_value(condition, variables)
        prompt = (
            "请基于以下信息判断条件是否成立，严格只回答 true 或 false。\n"
            f"条件：{rendered_condition}\n"
            f"用户消息：{message}\n"
            f"流程状态（JSON）：{json.dumps(flow_state, ensure_ascii=False)}\n"
        )
        
        try:
            response = await self.llm_helper.call(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # 解析结果
            is_true = 'true' in response.lower()
            
            # 根据条件选择下一个节点
            next_node_id = None
            if is_true and node.connections:
                next_node_id = node.connections[0]  # 第一个连接为true分支
            elif len(node.connections) > 1:
                next_node_id = node.connections[1]  # 第二个连接为false分支
            
            if next_node_id:
                return await self._execute_node(next_node_id, user_id, message, context)
            else:
                return AgentMessage(
                    id=str(uuid.uuid4()),
                    type=MessageType.AGENT,
                    content=f"条件判断结果：{is_true}，但未找到后续节点",
                    agent_name=self.name,
                    metadata={'node_id': node.id, 'node_type': node.type.value, 'condition_result': is_true}
                )
        except Exception as e:
            logger.error(f"执行条件节点失败: {str(e)}")
            raise
    
    async def _execute_action_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行动作节点"""
        action = node.config.get('action', '')
        if not action:
            raise ValueError(f"动作节点 {node.id} 未配置动作")
        
        # 执行动作（这里可以扩展为调用具体的工具或API）
        result = f"执行动作：{action}"
        
        # 如果有后续节点，继续执行
        if node.connections:
            next_node_id = node.connections[0]
            return await self._execute_node(next_node_id, user_id, message, context)
        else:
            return AgentMessage(
                id=str(uuid.uuid4()),
                type=MessageType.AGENT,
                content=result,
                agent_name=self.name,
                metadata={'node_id': node.id, 'node_type': node.type.value, 'action': action}
            )
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        return await self.execute_flow(user_id, message, context)
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息：按节点执行并逐步输出。
        - LLM 节点：使用 call_stream 按块输出 type="content"
        - TOOL 节点：工具执行完成后输出 type="tool_result"
        - 其他节点：整体内容作为一段 type="content"
        - 最终：输出 type="final"
        """
        try:
            flow_state = self._get_flow_state(context)
            base_vars = {"message": message}

            if not self.start_node_id:
                yield StreamChunk(
                    chunk_id=str(uuid.uuid4()),
                    session_id=(context or {}).get('session_id', ''),
                    type="error",
                    content="流程图未配置起始节点，无法执行。",
                    agent_name=self.name,
                    metadata={'flow_executed': False, 'error': 'no_start_node'},
                    is_end=True
                )
                return

            current_id = self.start_node_id
            step_guard = 0

            while current_id and step_guard < 1000:
                step_guard += 1
                node = self.nodes.get(current_id)
                if not node:
                    break

                vars_all = {**flow_state, **base_vars}

                if node.type == NodeType.LLM:
                    # 渲染提示
                    system_prompt = self._render_template_value(node.config.get('system_prompt', ''), vars_all)
                    user_prompt = self._render_template_value(node.config.get('user_prompt', message), vars_all)
                    save_as = node.config.get('save_as', 'last_output')

                    try:
                        msgs = []
                        if system_prompt:
                            msgs.append({"role": "system", "content": system_prompt})
                        msgs.append({"role": "user", "content": user_prompt})

                        acc = ""
                        async for piece in self.llm_helper.call_stream(messages=msgs):
                            if not piece:
                                continue
                            acc += piece
                            flow_state['last_output'] = flow_state.get('last_output', '') + piece
                            # 流式输出
                            yield StreamChunk(
                                chunk_id=str(uuid.uuid4()),
                                session_id=(context or {}).get('session_id', ''),
                                type="content",
                                content=piece,
                                agent_name=self.name
                            )
                        flow_state[save_as] = acc
                    except Exception as e:
                        yield StreamChunk(
                            chunk_id=str(uuid.uuid4()),
                            session_id=(context or {}).get('session_id', ''),
                            type="error",
                            content=f"LLM节点执行失败: {str(e)}",
                            agent_name=self.name
                        )
                    # 下一个
                    nexts = node.connections or []
                    current_id = nexts[0] if nexts else None
                    continue

                if node.type == NodeType.TOOL:
                    server = self._render_template_value(node.config.get('server'), vars_all)
                    tool = self._render_template_value(node.config.get('tool'), vars_all)
                    params_raw = node.config.get('params', {})
                    params = self._render_template_value(params_raw, vars_all)
                    save_as = node.config.get('save_as', 'last_output')
                    append_to_output = node.config.get('append_to_output', True)

                    try:
                        from main import agent_manager
                        if not agent_manager or not getattr(agent_manager, 'mcp_helper', None):
                            raise RuntimeError("MCP助手未初始化")
                        mcp = agent_manager.mcp_helper

                        actual_server = server
                        actual_tool = tool
                        if tool and '_' in tool and not server:
                            parts = tool.split('_', 1)
                            actual_server = parts[0]
                            actual_tool = parts[1]
                        if not actual_server:
                            services = await mcp.get_available_services()
                            if not services:
                                raise RuntimeError("没有可用的MCP服务")
                            actual_server = services[0]

                        result = await mcp.call_tool(
                            server_name=actual_server,
                            tool_name=actual_tool,
                            **(params if isinstance(params, dict) else {"query": str(params)})
                        )
                        try:
                            import json as _json
                            result_text = _json.dumps(result, ensure_ascii=False)
                        except Exception:
                            result_text = str(result)

                        flow_state[save_as] = result
                        formatted = result_text
                        if append_to_output:
                            flow_state['last_output'] = flow_state.get('last_output', '') + "\n" + result_text

                        # 输出工具结果
                        yield StreamChunk(
                            chunk_id=str(uuid.uuid4()),
                            session_id=(context or {}).get('session_id', ''),
                            type="tool_result",
                            content=formatted,
                            metadata={"tool_name": f"{actual_server}_{actual_tool}"},
                            agent_name=self.name
                        )
                    except Exception as e:
                        yield StreamChunk(
                            chunk_id=str(uuid.uuid4()),
                            session_id=(context or {}).get('session_id', ''),
                            type="tool_error",
                            content=f"工具节点执行失败: {str(e)}",
                            agent_name=self.name
                        )
                    nexts = node.connections or []
                    current_id = nexts[0] if nexts else None
                    continue

                if node.type == NodeType.CONDITION:
                    # 复用现有实现，不输出内容，仅决定路线
                    cond_msg = await self._execute_condition_node(node, user_id, message, context)
                    # 简单解析 true/false
                    text = (cond_msg.content or '').strip().lower()
                    is_true = ('true' in text) and ('false' not in text)
                    nexts = node.connections or []
                    if is_true and nexts:
                        current_id = nexts[0]
                    elif len(nexts) > 1:
                        current_id = nexts[1]
                    else:
                        current_id = None
                    continue

                if node.type == NodeType.AGENT:
                    # 调用目标智能体（非流式），整体作为一段内容输出
                    agent_resp = await self._execute_agent_node(node, user_id, message, context)
                    flow_state['last_output'] = flow_state.get('last_output', '') + (agent_resp.content or '')
                    yield StreamChunk(
                        chunk_id=str(uuid.uuid4()),
                        session_id=(context or {}).get('session_id', ''),
                        type="content",
                        content=agent_resp.content or '',
                        agent_name=self.name
                    )
                    nexts = node.connections or []
                    current_id = nexts[0] if nexts else None
                    continue

                # 未知节点，结束
                break

            # 最终输出
            yield StreamChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=(context or {}).get('session_id', ''),
                type="final",
                content=flow_state.get('last_output', ''),
                agent_name=self.name,
                metadata={},
                is_end=True
            )
        except Exception as e:
            logger.error(f"流式处理消息失败: {str(e)}")
            yield StreamChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=(context or {}).get('session_id', ''),
                type="error",
                content=f"处理消息时发生错误: {str(e)}",
                agent_name=self.name,
                metadata={'error': str(e)},
                is_end=True
            ) 