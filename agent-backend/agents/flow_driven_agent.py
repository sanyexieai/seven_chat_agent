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
		self.bound_tools: List[Any] = []  # 绑定工具（server_tool 字符串）
		
		# 初始化LLM助手
		try:
			self.llm_helper = get_llm_helper()
			logger.info(f"流程图驱动智能体 {name} 初始化成功")
		except Exception as e:
			logger.error(f"LLM初始化失败: {str(e)}")
			raise
		
		# 加载流程图配置
		self._load_flow_config()
		# 知识库绑定占位
		self.bound_knowledge_bases: List[Dict[str, Any]] = []
		logger.info(f"流程图驱动智能体 {name} 初始化完成")

	def set_knowledge_bases(self, knowledge_bases: List[Dict[str, Any]]):
		"""设置绑定的知识库（与通用智能体对齐接口）。"""
		self.bound_knowledge_bases = knowledge_bases or []
		try:
			names = [kb.get('name', 'Unknown') for kb in self.bound_knowledge_bases]
			logger.info(f"流程图智能体 {self.name} 绑定知识库: {names}")
		except Exception:
			pass

	def _merge_json_into_flow_state(self, text: str, flow_state: Dict[str, Any]):
		"""尝试从 LLM 文本中提取 JSON 并合并到 flow_state 中。"""
		if not text:
			return
		try:
			_clean = text
			# 去除<think>段落
			import re as _re
			_clean = _re.sub(r"<think>.*?</think>", "", _clean, flags=_re.IGNORECASE|_re.DOTALL)
			# 提取代码块中的 JSON 或直接解析
			m = _re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", _clean)
			if m:
				_candidate = m.group(1)
			else:
				_candidate = _clean.strip()
			parsed = json.loads(_candidate)
			if isinstance(parsed, dict):
				for k, v in parsed.items():
					flow_state[str(k)] = v
		except Exception:
			# 忽略解析失败
			pass

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
		"""执行 LLM 节点。"""
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
			# 解析 JSON 合并（为后续工具节点提供 selected_* 等变量）
			self._merge_json_into_flow_state(content, flow_state)
			logger.info(f"LLM节点 {node.id} 执行完成，保存为 {save_as}")
		except Exception as e:
			logger.error(f"LLM节点执行失败: {str(e)}")
			content = f"LLM节点执行失败: {str(e)}"
			flow_state[save_as] = content
			flow_state['last_output'] = content
		
		# 返回当前节点结果（路由由外层控制）
		return AgentMessage(
			id=str(uuid.uuid4()),
			type=MessageType.AGENT,
			content=flow_state['last_output'],
			agent_name=self.name,
			metadata={'node_id': node.id, 'node_type': node.type.value}
		)

	async def _select_bound_tool(self, desired_server: Optional[str], desired_tool: Optional[str], mcp_helper) -> Optional[tuple[str, str]]:
		available_services = await mcp_helper.get_available_services()
		if not getattr(self, 'bound_tools', None):
			return None
		# 构建候选（仅保留可用服务）
		candidates: List[tuple[str, str]] = []
		for item in self.bound_tools:
			val = str(item)
			if '_' in val:
				s, t = val.split('_', 1)
				if not available_services or s in available_services:
					candidates.append((s, t))
		# 打分排序
		def score(pair: tuple[str, str]) -> int:
			s, t = pair
			score = 0
			if desired_server and s == desired_server:
				score += 2
			if desired_tool and (t == desired_tool or t.endswith(desired_tool)):
				score += 3
			return score
		candidates.sort(key=score, reverse=True)
		# 验证工具存在
		for s, t in candidates:
			if not desired_tool:
				return (s, t)
			if await self._server_has_tool(mcp_helper, s, t):
				return (s, t)
		return candidates[0] if candidates else None

	async def _find_tool_in_services(self, desired_tool: Optional[str], mcp_helper) -> Optional[tuple[str, str]]:
		if not desired_tool:
			return None
		services = await mcp_helper.get_available_services()
		for s in services:
			try:
				tools = await mcp_helper.get_tools(server_name=s)
				for tk in tools:
					name = tk.get('name') if isinstance(tk, dict) else getattr(tk, 'name', '')
					if name == desired_tool or name.endswith(desired_tool):
						return (s, name)
			except Exception:
				continue
		return None

	async def _execute_tool_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
		"""执行工具节点。支持 server_tool 合并格式与变量模板。"""
		flow_state = self._get_flow_state(context)
		variables = {**flow_state, 'message': message}
		server = self._render_template_value(node.config.get('server'), variables)
		tool = self._render_template_value(node.config.get('tool'), variables)
		params = self._render_template_value(node.config.get('params', {}), variables)
		save_as = node.config.get('save_as', 'last_output')
		
		logger.info(f"工具节点 {node.id} 调用: {server}.{tool} 参数: {params}")
		try:
			from main import agent_manager
			if not agent_manager or not getattr(agent_manager, 'mcp_helper', None):
				raise RuntimeError("MCP助手未初始化")
			mcp_helper = agent_manager.mcp_helper
			
			actual_server = server
			actual_tool = tool
			if tool and '_' in tool and not server:
				parts = tool.split('_', 1)
				actual_server = parts[0]
				actual_tool = parts[1]
			
			# 优先选择绑定工具，若未指定或不可用则回退
			selected = await self._select_bound_tool(actual_server, actual_tool, mcp_helper)
			if selected:
				actual_server, actual_tool = selected
			else:
				# 若未匹配上绑定工具，但指定了 tool，尝试跨服务查找
				found = await self._find_tool_in_services(actual_tool, mcp_helper)
				if found:
					actual_server, actual_tool = found
				else:
					# 最后回退：任选一个可用服务（可能失败，但尽力而为）
					services = await mcp_helper.get_available_services()
					if services and not actual_server:
						actual_server = services[0]
			
			if not actual_server or not actual_tool:
				raise RuntimeError("未能解析可用的 server/tool")
			
			# 调用工具
			result = await mcp_helper.call_tool(
				server_name=actual_server,
				tool_name=actual_tool,
				**(params if isinstance(params, dict) else {"query": str(params)})
			)
			try:
				result_text = json.dumps(result, ensure_ascii=False)
			except Exception:
				result_text = str(result)
			flow_state[save_as] = result
			flow_state['last_output'] = result_text
			return AgentMessage(
				id=str(uuid.uuid4()),
				type=MessageType.AGENT,
				content=result_text,
				agent_name=self.name,
				metadata={'node_id': node.id, 'node_type': node.type.value, 'tool': f"{actual_server}_{actual_tool}"}
			)
		except Exception as e:
			logger.error(f"工具节点执行失败: {str(e)}")
			raise

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
	
	def _select_tool_from_bound(self, desired_server: Optional[str], desired_tool: Optional[str], mcp_helper) -> Optional[tuple[str, str]]:
		"""从绑定工具列表中选择最合适的 (server, tool)。
		优先匹配：server+tool 全匹配 > tool 名匹配 > server 匹配 > 首个绑定。
		并验证该 server/tool 在可用列表中存在。
		"""
		if not getattr(self, 'bound_tools', None):
			return None
		candidates: List[tuple[str, str]] = []
		for item in self.bound_tools:
			val = str(item)
			if '_' in val:
				s, t = val.split('_', 1)
				candidates.append((s, t))
		# 排序打分
		def score(pair: tuple[str, str]) -> int:
			s, t = pair
			score = 0
			if desired_server and s == desired_server:
				score += 2
			if desired_tool and (t == desired_tool or t.endswith(desired_tool)):
				score += 3
			return score
		candidates.sort(key=score, reverse=True)
		# 验证可用性（服务存在且工具存在）
		return self._first_valid_tool(candidates, mcp_helper)

	async def _server_has_tool(self, mcp_helper, server: str, tool: str) -> bool:
		try:
			tools = await mcp_helper.get_tools(server_name=server)
			for tk in tools:
				name = tk.get('name') if isinstance(tk, dict) else getattr(tk, 'name', '')
				if name == tool:
					return True
		except Exception:
			return False
		return False

	def _first_valid_tool(self, pairs: List[tuple[str, str]], mcp_helper) -> Optional[tuple[str, str]]:
		# 仅验证服务存在，工具存在性在调用前再检查以节省请求
		return pairs[0] if pairs else None

	async def _execute_condition_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
		"""执行条件节点，仅返回 true/false 文本，不做路由。"""
		condition = node.config.get('condition', '')
		if not condition:
			raise ValueError(f"条件节点 {node.id} 未配置条件")
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
			response = await self.llm_helper.call(messages=[{"role": "user", "content": prompt}])
			text = (response or '').strip().lower()
			is_true = ('true' in text) and ('false' not in text)
			return AgentMessage(
				id=str(uuid.uuid4()),
				type=MessageType.AGENT,
				content='true' if is_true else 'false',
				agent_name=self.name,
				metadata={'node_id': node.id, 'node_type': node.type.value}
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

			# 开始节点预处理阶段：判断是否可直接回答 / 规划工具 / 添加todolist
			try:
				judge_prompt = (
					"你是一个判断器。给定用户问题，判断是否可以在不查询外部数据、工具或知识库的前提下给出可靠回答。\n"
					"严格输出JSON：{\"can_direct_answer\": true|false, \"answer\": string}。\n"
					f"用户问题：{message}"
				)
				judge_resp = await self.llm_helper.call(messages=[{"role": "user", "content": judge_prompt}])
				parsed = None
				try:
					parsed = json.loads(judge_resp)
				except Exception:
					parsed = None
				if isinstance(parsed, dict) and parsed.get("can_direct_answer") and parsed.get("answer"):
					# 直接回答并结束
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="final",
						content=str(parsed.get("answer", "")),
						agent_name=self.name,
						metadata={"direct": True},
						is_end=True
					)
					return

				# 需要外部数据：规划工具
				from main import agent_manager
				mcp = getattr(agent_manager, 'mcp_helper', None) if agent_manager else None
				bound_tools = list(getattr(self, 'bound_tools', []) or [])
				selected_tool = None  # (server, tool)
				if mcp and bound_tools:
					# 先尝试首选绑定工具（简单启发式）
					for t in bound_tools:
						if isinstance(t, str) and '_' in t:
							server, tool = t.split('_', 1)
							selected_tool = (server, tool)
							break
				
				if mcp and selected_tool:
					try:
						server, tool = selected_tool
						result = await mcp.call_tool(
							server_name=server,
							tool_name=tool,
							query=str(message)
						)
						try:
							result_text = json.dumps(result, ensure_ascii=False)
						except Exception:
							result_text = str(result)
						flow_state['last_output'] = flow_state.get('last_output', '') + ("\n" if flow_state.get('last_output') else "") + result_text
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="tool_result",
							content=result_text,
							metadata={"tool_name": f"{server}_{tool}"},
							agent_name=self.name
						)
					except Exception as e:
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="tool_error",
							content=f"开始阶段工具调用失败: {str(e)}",
							agent_name=self.name
						)
				else:
					# 无可用工具：添加todolist项
					todo_reason = "现有工具无法满足需求，请添加适配该问题的工具或接入数据源。"
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="tool_result",
						content=f"[TODO] {todo_reason}",
						metadata={"tool_name": "todolist"},
						agent_name=self.name
					)
			except Exception as _e:
				# 开始阶段失败不阻断主流程
				logger.warning(f"开始阶段处理失败: {str(_e)}")

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
						# 尝试解析 JSON 并合并到 flow_state
						self._merge_json_into_flow_state(acc, flow_state)
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