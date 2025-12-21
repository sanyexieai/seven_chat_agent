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
	START = "start"           # 开始节点
	AGENT = "agent"           # 智能体节点
	ACTION = "action"         # 动作节点
	LLM = "llm"               # LLM 调用节点
	TOOL = "tool"             # 工具调用节点
	ROUTER = "router"         # 路由节点（统一的路由逻辑处理）
	KNOWLEDGE_BASE = "knowledge_base"  # 知识库查询节点
	END = "end"               # 结束节点

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
				node_type_value = node_config.get('type', NodeType.AGENT.value)
				try:
					node_type = NodeType(node_type_value)
				except ValueError:
					# 回退：如果是旧格式，尝试根据类别或实现推断
					implementation = node_config.get('implementation', node_type_value)
					node_type = NodeType(implementation) if implementation in NodeType._value2member_map_ else NodeType.AGENT
				node_data = node_config.get('data', {})
				node_name = node_data.get('label', '')
				
				# 从data中提取config，并确保label被包含
				node_config_dict = node_data.get('config', {})
				# 确保label被保存到config中，供后续使用
				if node_name:
					node_config_dict['label'] = node_name
				
				logger.info(f"解析节点 {node_id}: type={node_type}, name={node_name}, config={node_config_dict}")
				
				node = FlowNode(node_id, node_type, node_name, node_config_dict)
				self.nodes[node_id] = node
				
				# 检查是否为起始节点
				if node_data.get('isStartNode', False) or node_type == NodeType.START:
					self.start_node_id = node_id
					logger.info(f"设置起始节点: {node_id}")
			
			# 如果没有找到起始节点，使用第一个节点作为起始节点
			if not self.start_node_id and nodes_config:
				self.start_node_id = nodes_config[0]['id']
				logger.info(f"未找到起始节点，使用第一个节点作为起始节点: {self.start_node_id}")
			
			# 解析边配置，建立节点连接关系
			edges_config = self.flow_config.get('edges', [])
			logger.info(f"开始解析 {len(edges_config)} 条边")
			
			# 修复后的连线处理逻辑
			for edge_config in edges_config:
				source_id = edge_config.get('source')
				target_id = edge_config.get('target')
				source_handle = edge_config.get('sourceHandle', '')
				
				if source_id and target_id and source_id in self.nodes:
					source_node = self.nodes[source_id]
					if not hasattr(source_node, 'connections'):
						source_node.connections = []
					
					# 根据sourceHandle决定连接类型
					if source_handle == 'source-true':
						# 真值分支，放在第一个位置
						if len(source_node.connections) == 0:
							source_node.connections = [target_id, None]
						else:
							source_node.connections[0] = target_id
					elif source_handle == 'source-false':
						# 假值分支，放在第二个位置
						if len(source_node.connections) == 0:
							source_node.connections = [None, target_id]
						elif len(source_node.connections) == 1:
							source_node.connections.append(target_id)
						else:
							source_node.connections[1] = target_id
					else:
						# 默认连接，放在第一个位置
						if len(source_node.connections) == 0:
							source_node.connections = [target_id]
						else:
							source_node.connections[0] = target_id
					
					logger.info(f"建立连接: {source_id} -> {target_id} (handle: {source_handle})")
			
			logger.info(f"加载了 {len(self.nodes)} 个流程图节点")
			logger.info(f"起始节点: {self.start_node_id}")
			
			# 打印所有节点的配置和连接
			for node_id, node in self.nodes.items():
				logger.info(f"节点 {node_id} 配置: {node.config}")
				logger.info(f"节点 {node_id} 连接: {getattr(node, 'connections', [])}")
		
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

	async def _execute_router_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
		"""执行路由节点 - 统一的路由逻辑处理"""
		flow_state = self._get_flow_state(context)
		routing_config = node.config.get('routing_logic', {})
		
		if not routing_config:
			raise ValueError(f"路由节点 {node.id} 未配置路由逻辑")
		
		# 获取路由字段和值
		field = routing_config.get('field', '')
		value = routing_config.get('value', None)
		true_branch = routing_config.get('true_branch', '')
		false_branch = routing_config.get('false_branch', '')
		
		if not field:
			raise ValueError(f"路由节点 {node.id} 未配置路由字段")
		
		# 从流程状态获取字段值
		field_value = flow_state.get(field)
		
		# 根据路由逻辑选择分支
		selected_branch = None
		if value is not None:
			# 精确值匹配
			if field_value == value:
				selected_branch = 'true'
			else:
				selected_branch = 'false'
		else:
			# 布尔值判断
			if isinstance(field_value, bool):
				selected_branch = 'true' if field_value else 'false'
			elif isinstance(field_value, (int, float)):
				# 数值判断
				threshold = routing_config.get('threshold', 0)
				operator = routing_config.get('operator', '>')
				
				if operator == '>':
					selected_branch = 'true' if field_value > threshold else 'false'
				elif operator == '>=':
					selected_branch = 'true' if field_value >= threshold else 'false'
				elif operator == '<':
					selected_branch = 'true' if field_value < threshold else 'false'
				elif operator == '<=':
					selected_branch = 'true' if field_value <= threshold else 'false'
				elif operator == '==':
					selected_branch = 'true' if field_value == threshold else 'false'
				else:
					selected_branch = 'false'
			elif isinstance(field_value, str):
				# 字符串判断
				pattern = routing_config.get('pattern', '')
				if pattern:
					import re
					if re.search(pattern, field_value):
						selected_branch = 'true'
					else:
						selected_branch = 'false'
				else:
					# 非空字符串判断
					selected_branch = 'true' if field_value else 'false'
			else:
				# 其他类型，默认为false
				selected_branch = 'false'
		
		# 记录路由决策
		logger.info(f"路由节点 {node.id} 字段 {field}={field_value}, 选择分支: {selected_branch}")
		logger.info(f"路由节点 {node.id} 可用分支: {true_branch} (真值), {false_branch} (假值)")
		
		# 将路由决策保存到流程状态，供后续节点使用
		flow_state['router_decision'] = {
			'field': field,
			'value': field_value,
			'selected_branch': selected_branch,
			'timestamp': str(uuid.uuid4())
		}
		
		return AgentMessage(
			id=str(uuid.uuid4()),
			type=MessageType.AGENT,
			content=f"路由决策: {field}={field_value} -> {selected_branch}",
			agent_name=self.name,
			metadata={'node_id': node.id, 'node_type': node.type.value, 'selected_branch': selected_branch}
		)

	async def _execute_knowledge_base_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
		"""执行知识库查询节点"""
		flow_state = self._get_flow_state(context)
		
		# 获取知识库配置
		kb_config = node.config.get('knowledge_base_config', {})
		kb_id = kb_config.get('knowledge_base_id')
		query_type = kb_config.get('query_type', 'semantic')  # semantic, keyword, hybrid
		max_results = kb_config.get('max_results', 5)
		query_template = kb_config.get('query_template', '{{message}}')
		save_as = kb_config.get('save_as', 'knowledge_result')
		
		if not kb_id:
			raise ValueError(f"知识库节点 {node.id} 未配置知识库ID")
		
		try:
			# 导入知识库服务
			from services.knowledge_base_service import KnowledgeBaseService
			kb_service = KnowledgeBaseService()
			
			# 构建查询内容
			query = query_template.replace('{{message}}', message)
			if '{{last_output}}' in query_template:
				last_output = flow_state.get('last_output', '')
				query = query.replace('{{last_output}}', last_output)
			
			# 查询知识库
			results = kb_service.query_knowledge_base(
				db_session=context.get('db_session'),
				kb_id=kb_id,
				query=query,
				user_id=user_id,
				max_results=max_results
			)
			
			# 格式化结果
			if results and results.get('sources'):
				formatted_result = f"知识库查询结果:\n\n"
				formatted_result += f"查询: {query}\n\n"
				formatted_result += f"回答: {results.get('response', '未找到相关答案')}\n\n"
				formatted_result += "相关文档:\n"
				
				for i, source in enumerate(results['sources'][:max_results], 1):
					similarity = source.get('similarity', 0)
					content = source.get('content', '')
					formatted_result += f"{i}. 相似度: {similarity:.2%}\n"
					formatted_result += f"   内容: {content[:200]}{'...' if len(content) > 200 else ''}\n\n"
				
				# 保存结果到流程状态
				flow_state[save_as] = {
					'query': query,
					'response': results.get('response', ''),
					'sources': results.get('sources', []),
					'knowledge_base_id': kb_id,
					'query_type': query_type,
					'timestamp': str(uuid.uuid4())
				}
				
				return AgentMessage(
					id=str(uuid.uuid4()),
					type=MessageType.AGENT,
					content=formatted_result,
					agent_name=self.name,
					metadata={
						'node_id': node.id, 
						'node_type': node.type.value, 
						'knowledge_base_id': kb_id,
						'query_type': query_type,
						'result_count': len(results.get('sources', []))
					}
				)
			else:
				# 没有找到结果
				flow_state[save_as] = {
					'query': query,
					'response': '未找到相关答案',
					'sources': [],
					'knowledge_base_id': kb_id,
					'query_type': query_type,
					'timestamp': str(uuid.uuid4())
				}
				
				return AgentMessage(
					id=str(uuid.uuid4()),
					type=MessageType.AGENT,
					content=f"知识库查询结果:\n\n查询: {query}\n\n未找到相关答案",
					agent_name=self.name,
					metadata={
						'node_id': node.id, 
						'node_type': node.type.value, 
						'knowledge_base_id': kb_id,
						'query_type': query_type,
						'result_count': 0
					}
				)
				
		except Exception as e:
			logger.error(f"知识库节点 {node.id} 执行失败: {str(e)}")
			flow_state[save_as] = {
				'query': query if 'query' in locals() else '未知',
				'response': f'查询失败: {str(e)}',
				'sources': [],
				'knowledge_base_id': kb_id,
				'query_type': query_type,
				'timestamp': str(uuid.uuid4()),
				'error': str(e)
			}
			
			return AgentMessage(
				id=str(uuid.uuid4()),
				type=MessageType.AGENT,
				content=f"知识库查询失败: {str(e)}",
				agent_name=self.name,
				metadata={
					'node_id': node.id, 
					'node_type': node.type.value, 
					'knowledge_base_id': kb_id,
					'query_type': query_type,
					'error': str(e)
				}
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
			
			# 添加调试日志
			logger.info(f"🚀 开始执行流程图，起始节点: {self.start_node_id}")
			logger.info(f"🚀 流程图节点数量: {len(self.nodes)}")
			logger.info(f"🚀 流程图节点类型: {[node.type.value for node in self.nodes.values()]}")
			logger.info(f"🚀 流程图节点详情: {[(node.id, node.type.value, node.name) for node in self.nodes.values()]}")
			logger.info(f"🚀 用户消息: {message}")
			logger.info(f"🚀 流程状态: {flow_state}")
			
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
					logger.error(f"🚨 找不到节点: {current_id}")
					break

				logger.info(f"🚀 执行节点 {step_guard}: {current_id} ({node.type.value}) - {node.name}")
				vars_all = {**flow_state, **base_vars}

				if node.type == NodeType.START:
					start_message_raw = (
						node.config.get('message')
						or node.config.get('start_message')
						or node.config.get('label', node.name)
						or "开始"
					)
					start_message = str(start_message_raw)
					
					# 节点开始事件
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="node_start",
						content=f"🚀 开始执行 {node.name or '开始节点'}",
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name)
						}
					)
					
					# 节点内容输出
					if start_message:
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="content",
							content=start_message,
							agent_name=self.name,
							metadata={
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name,
								'node_label': node.config.get('label', node.name)
							}
						)
					
					# 节点完成事件
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="node_complete",
						content=f"✅ {node.name or '开始节点'} 执行完成",
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name),
							'output': start_message
						}
					)
					
					nexts = node.connections or []
					current_id = nexts[0] if nexts else None
					continue

				if node.type == NodeType.LLM:
					logger.info(f"🚀 进入LLM节点处理分支: {current_id}")
					# 发送节点开始标识
					logger.info(f"🚀 准备发送节点开始事件: {node.id} ({node.name})")
					logger.info(f"🚀 节点metadata: node_id={node.id}, node_type={node.type.value}, node_name={node.name}, node_label={node.config.get('label', node.name)}")
					
					# 添加调试日志，确认即将发送node_start事件
					logger.info(f"🚀 即将发送StreamChunk: type=node_start, content=🚀 开始执行 {node.name} 节点")
					
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="node_start",
						content=f"🚀 开始执行 {node.name} 节点",
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name)
						}
					)
					
					logger.info(f"🚀 节点开始事件已发送: {node.id}")
					logger.info(f"🚀 节点开始事件发送完成，继续执行LLM逻辑")
					
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
							# 流式输出，添加节点标识
							yield StreamChunk(
								chunk_id=str(uuid.uuid4()),
								session_id=(context or {}).get('session_id', ''),
								type="content",
								content=piece,
								agent_name=self.name,
								metadata={
									'node_id': node.id,
									'node_type': node.type.value,
									'node_name': node.name,
									'node_label': node.config.get('label', node.name)
								}
							)
						flow_state[save_as] = acc
						# 尝试解析 JSON 并合并到 flow_state
						self._merge_json_into_flow_state(acc, flow_state)
						
						# 输出节点执行完成标识
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="node_complete",
							content=f"✅ {node.name} 节点执行完成",
							agent_name=self.name,
							metadata={
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name,
								'node_label': node.config.get('label', node.name),
								'output': acc
							}
						)
					except Exception as e:
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="error",
							content=f"LLM节点执行失败: {str(e)}",
							agent_name=self.name,
							metadata={
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name
							}
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
							metadata={
								"tool_name": f"{actual_server}_{actual_tool}",
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name,
								'node_label': node.config.get('label', node.name)
							},
							agent_name=self.name
						)
					except Exception as e:
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="tool_error",
							content=f"工具节点执行失败: {str(e)}",
							agent_name=self.name,
							metadata={
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name,
								'node_label': node.config.get('label', node.name)
							}
						)
					nexts = node.connections or []
					current_id = nexts[0] if nexts else None
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
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name),
							'agent_name': agent_name
						}
					)
					nexts = node.connections or []
					current_id = nexts[0] if nexts else None
					continue

				if node.type == NodeType.ROUTER:
					# 执行路由节点
					logger.info(f"🚀 进入ROUTER节点处理分支: {current_id}")
					logger.info(f"🚀 即将执行路由节点: {node.id} ({node.name})")
					
					router_msg = await self._execute_router_node(node, user_id, message, context)
					flow_state['last_output'] = flow_state.get('last_output', '') + (router_msg.content or '')
					
					# 输出路由决策
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="content",
						content=router_msg.content or '',
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name),
							'selected_branch': router_msg.metadata.get('selected_branch')
						}
					)
					
					# 根据路由决策决定下一步
					selected_branch = router_msg.metadata.get('selected_branch')
					nexts = node.connections or []
					
					if selected_branch and nexts:
						# 根据路由决策选择分支
						if selected_branch == 'true' and len(nexts) > 0:
							current_id = nexts[0]  # 第一个分支：真值分支
							logger.info(f"路由节点 {node.id} 选择真值分支: {current_id}")
						elif selected_branch == 'false' and len(nexts) > 1:
							current_id = nexts[1]  # 第二个分支：假值分支
							logger.info(f"路由节点 {node.id} 选择假值分支: {current_id}")
						elif len(nexts) > 0:
							# 只有一个分支，继续执行
							current_id = nexts[0]
							logger.info(f"路由节点 {node.id} 只有一个分支，继续执行: {current_id}")
						else:
							current_id = None
							logger.info(f"路由节点 {node.id} 没有后续节点，结束流程")
					else:
						# 没有路由决策或后续节点，结束流程
						current_id = None
						logger.info(f"路由节点 {node.id} 未找到分支，结束流程")
					
					continue

				if node.type == NodeType.KNOWLEDGE_BASE:
					# 执行知识库查询节点
					logger.info(f"🚀 进入知识库节点处理: {current_id}")
					logger.info(f"🚀 即将执行知识库节点: {node.id} ({node.name})")
					
					kb_msg = await self._execute_knowledge_base_node(node, user_id, message, context)
					flow_state['last_output'] = flow_state.get('last_output', '') + (kb_msg.content or '')
					
					# 输出知识库查询结果
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="content",
						content=kb_msg.content or '',
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name),
							'knowledge_base_id': kb_msg.metadata.get('knowledge_base_id'),
							'query_type': kb_msg.metadata.get('query_type'),
							'result_count': kb_msg.metadata.get('result_count', 0)
						}
					)
					
					nexts = node.connections or []
					current_id = nexts[0] if nexts else None
					continue

				if node.type == NodeType.END:
					end_message_raw = (
						node.config.get('message')
						or node.config.get('end_message')
						or flow_state.get('last_output', '')
						or "结束"
					)
					end_message = str(end_message_raw)
					
					# 节点开始事件
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="node_start",
						content=f"🚀 开始执行 {node.name or '结束节点'}",
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name)
						}
					)
					
					# 节点内容输出
					if end_message:
						yield StreamChunk(
							chunk_id=str(uuid.uuid4()),
							session_id=(context or {}).get('session_id', ''),
							type="content",
							content=end_message,
							agent_name=self.name,
							metadata={
								'node_id': node.id,
								'node_type': node.type.value,
								'node_name': node.name,
								'node_label': node.config.get('label', node.name)
							}
						)
					
					# 节点完成事件
					yield StreamChunk(
						chunk_id=str(uuid.uuid4()),
						session_id=(context or {}).get('session_id', ''),
						type="node_complete",
						content=f"✅ {node.name or '结束节点'} 执行完成",
						agent_name=self.name,
						metadata={
							'node_id': node.id,
							'node_type': node.type.value,
							'node_name': node.name,
							'node_label': node.config.get('label', node.name),
							'output': end_message
						}
					)
					
					# 更新最终输出并结束流程
					flow_state['last_output'] = end_message
					current_id = None
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