from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator, Type, Callable
from enum import Enum
from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
import uuid

logger = get_logger("flow_node")


class NodeCategory(str, Enum):
	"""节点类别枚举 - 按执行模式分类，而非具体实现
	
	这种设计使得节点类型更通用，具体实现通过 implementation 配置指定。
	例如：PROCESSOR 节点可以通过 implementation: "llm" 或 "tool" 来指定具体实现。
	"""
	# 核心执行节点
	PROCESSOR = "processor"      # 处理器节点：处理数据（可以是 LLM、工具、函数等）
	ROUTER = "router"           # 路由节点：条件分支，根据条件选择下一个节点
	LOOP = "loop"               # 循环节点：迭代执行子流程
	AGGREGATOR = "aggregator"   # 聚合节点：合并多个输入分支的结果
	
	# 数据操作节点
	TRANSFORM = "transform"     # 转换节点：数据格式转换、提取等
	VALIDATOR = "validator"     # 验证节点：数据验证和校验
	STORAGE = "storage"         # 存储节点：保存/读取数据
	
	# 流程控制节点
	START = "start"             # 起始节点：流程入口
	END = "end"                 # 结束节点：流程出口
	PARALLEL = "parallel"       # 并行节点：并行执行多个分支
	MERGE = "merge"             # 合并节点：合并并行分支的结果


class NodeImplementation(str, Enum):
	"""节点实现类型枚举 - 具体的执行方式
	
	这些是 PROCESSOR 节点可以使用的具体实现。
	通过注册机制，可以动态添加新的实现。
	"""
	# LLM 相关
	LLM = "llm"                 # LLM 调用
	LLM_STREAM = "llm_stream"   # 流式 LLM 调用
	LLM_TOOL_CHOICE = "llm_tool_choice"  # LLM 工具选择（ReAct模式）
	
	# 工具相关
	TOOL = "tool"               # 工具调用（MCP工具）
	TOOL_BATCH = "tool_batch"    # 批量工具调用
	
	# 智能体相关
	AGENT = "agent"             # 调用其他智能体
	AGENT_STREAM = "agent_stream"  # 流式调用其他智能体
	
	# 知识库相关
	KNOWLEDGE_BASE = "knowledge_base"  # 知识库查询
	KNOWLEDGE_BASE_RAG = "knowledge_base_rag"  # RAG查询
	
	# 路由相关
	ROUTER_CONDITION = "router_condition"  # 条件路由（基于flow_state字段）
	ROUTER_LLM = "router_llm"    # LLM判断路由
	ROUTER_RULE = "router_rule"  # 规则路由
	
	# 数据操作
	TRANSFORM_JSON = "transform_json"  # JSON转换
	TRANSFORM_TEMPLATE = "transform_template"  # 模板转换
	VALIDATOR_SCHEMA = "validator_schema"  # Schema验证
	
	# 自定义
	CUSTOM = "custom"           # 自定义实现（通过函数或类指定）


class NodeRegistry:
	"""节点实现注册表 - 管理所有可用的节点实现
	
	支持动态注册新的节点实现，实现插件化扩展。
	"""
	_registry: Dict[str, Type['BaseFlowNode']] = {}
	_factory_registry: Dict[str, Callable] = {}
	
	@classmethod
	def register(cls, implementation: str, node_class: Type['BaseFlowNode']):
		"""注册节点实现类
		
		Args:
			implementation: 实现类型（如 "llm", "tool"）
			node_class: 节点类
		"""
		cls._registry[implementation] = node_class
		logger.info(f"注册节点实现: {implementation} -> {node_class.__name__}")
	
	@classmethod
	def register_factory(cls, implementation: str, factory: Callable):
		"""注册节点工厂函数
		
		Args:
			implementation: 实现类型
			factory: 工厂函数，接收 (node_id, config) 返回节点实例
		"""
		cls._factory_registry[implementation] = factory
		logger.info(f"注册节点工厂: {implementation}")
	
	@classmethod
	def get_node_class(cls, implementation: str) -> Optional[Type['BaseFlowNode']]:
		"""获取节点实现类"""
		return cls._registry.get(implementation)
	
	@classmethod
	def get_factory(cls, implementation: str) -> Optional[Callable]:
		"""获取节点工厂函数"""
		return cls._factory_registry.get(implementation)
	
	@classmethod
	def create_node(
		cls,
		node_id: str,
		category: NodeCategory,
		implementation: str,
		name: str,
		config: Dict[str, Any] = None,
		position: Optional[Dict[str, float]] = None
	) -> 'BaseFlowNode':
		"""通过注册表创建节点实例
		
		Args:
			node_id: 节点ID
			category: 节点类别
			implementation: 实现类型
			name: 节点名称
			config: 配置
			position: 位置
			
		Returns:
			节点实例
			
		Raises:
			ValueError: 如果实现未注册
		"""
		# 优先使用工厂函数
		factory = cls.get_factory(implementation)
		if factory:
			return factory(node_id, category, name, config, position)
		
		# 其次使用注册的类
		node_class = cls.get_node_class(implementation)
		if node_class:
			return node_class(node_id, category, implementation, name, config, position)
		
		# 如果未找到，抛出错误
		available_impls = cls.list_implementations()
		error_msg = f"未找到节点实现 '{implementation}'。已注册的实现: {available_impls if available_impls else '无'}"
		logger.error(error_msg)
		raise ValueError(error_msg)
	
	@classmethod
	def list_implementations(cls) -> List[str]:
		"""列出所有已注册的实现"""
		all_impls = set(cls._registry.keys()) | set(cls._factory_registry.keys())
		return sorted(list(all_impls))


class BaseFlowNode(ABC):
	"""流程图节点基类
	
	设计理念：
	1. 节点类别（category）定义节点的执行模式（如 PROCESSOR, ROUTER）
	2. 节点实现（implementation）定义具体的执行方式（如 "llm", "tool"）
	3. 通过注册机制支持动态扩展新的实现
	
	所有流程图节点都应该继承此类，实现具体的执行逻辑。
	基类提供了：
	- 节点基本属性管理（id, category, implementation, name, config等）
	- 模板渲染功能（支持 {{variable}} 语法）
	- 流程状态管理（flow_state）
	- 配置验证
	- 统一的执行接口
	"""
	
	def __init__(
		self,
		node_id: str,
		category: NodeCategory,
		implementation: str,
		name: str,
		config: Dict[str, Any] = None,
		position: Optional[Dict[str, float]] = None
	):
		"""
		初始化节点
		
		Args:
			node_id: 节点唯一标识
			category: 节点类别（执行模式）
			implementation: 节点实现类型（具体执行方式）
			name: 节点名称/标签
			config: 节点配置字典
			position: 节点位置信息（用于可视化）
		"""
		self.id = node_id
		self.category = category
		self.implementation = implementation
		self.name = name
		self.config = config or {}
		self.position = position or self.config.get('position', {'x': 0, 'y': 0})
		self.connections: List[Optional[str]] = []  # 连接到的其他节点ID列表
		self.label = self.config.get('label', name)  # 显示标签
		
		# 验证配置
		self._validate_config()
	
	def _validate_config(self):
		"""验证节点配置的有效性（子类可重写）"""
		# 基类默认不做验证，子类可以重写此方法
		pass
	
	def set_connections(self, connections: List[Optional[str]]):
		"""设置节点的连接关系"""
		self.connections = connections or []
	
	def add_connection(self, target_node_id: str, index: Optional[int] = None):
		"""添加一个连接"""
		if index is not None and 0 <= index < len(self.connections):
			self.connections[index] = target_node_id
		else:
			self.connections.append(target_node_id)
	
	def get_next_node_id(self, branch_index: int = 0) -> Optional[str]:
		"""获取下一个节点ID（根据分支索引）"""
		if 0 <= branch_index < len(self.connections):
			return self.connections[branch_index]
		return None
	
	def _render_template_value(self, value: Any, variables: Dict[str, Any]) -> Any:
		"""渲染字符串中的 {{var}} 模板；对 dict/list 递归处理。
		
		Args:
			value: 要渲染的值（可以是字符串、字典、列表）
			variables: 变量字典
			
		Returns:
			渲染后的值
		"""
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
	
	def _get_flow_state(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
		"""从上下文获取/初始化流程状态容器。
		
		Args:
			context: 上下文字典
			
		Returns:
			流程状态字典
		"""
		if context is None:
			context = {}
		state = context.get('flow_state')
		if state is None:
			state = {}
			context['flow_state'] = state
		return state
	
	def _save_to_flow_state(
		self,
		context: Dict[str, Any],
		key: str,
		value: Any,
		also_save_as_last_output: bool = False
	):
		"""保存值到流程状态
		
		Args:
			context: 上下文字典
			key: 保存的键名
			value: 要保存的值
			also_save_as_last_output: 是否同时保存为 last_output
		"""
		flow_state = self._get_flow_state(context)
		flow_state[key] = value
		if also_save_as_last_output:
			flow_state['last_output'] = value if isinstance(value, str) else str(value)
	
	def _get_from_flow_state(self, context: Dict[str, Any], key: str, default: Any = None) -> Any:
		"""从流程状态获取值
		
		Args:
			context: 上下文字典
			key: 键名
			default: 默认值
			
		Returns:
			流程状态中的值或默认值
		"""
		flow_state = self._get_flow_state(context)
		return flow_state.get(key, default)
	
	# ===== 上下文/历史数据：以节点ID为命名空间的读写工具（中间件式能力） =====
	def _get_nodes_bucket(self, context: Dict[str, Any]) -> Dict[str, Any]:
		"""获取 flow_state 中的 nodes 容器，用于存放各节点的历史数据"""
		flow_state = self._get_flow_state(context)
		nodes = flow_state.get('nodes')
		if nodes is None:
			nodes = {}
			flow_state['nodes'] = nodes
		return nodes
	
	def _ensure_node_entry(self, context: Dict[str, Any], node_id: Optional[str] = None) -> Dict[str, Any]:
		"""确保某个节点ID在 nodes 容器中存在条目"""
		nid = node_id or self.id
		nodes = self._get_nodes_bucket(context)
		entry = nodes.get(nid)
		if entry is None:
			entry = {'data': {}, 'outputs': []}
			nodes[nid] = entry
		if 'data' not in entry:
			entry['data'] = {}
		if 'outputs' not in entry:
			entry['outputs'] = []
		return entry
	
	def set_node_value(self, context: Dict[str, Any], key: str, value: Any, node_id: Optional[str] = None):
		"""将值保存到指定节点（默认当前节点）的 data 命名空间"""
		entry = self._ensure_node_entry(context, node_id)
		entry['data'][key] = value
	
	def get_node_value(self, context: Dict[str, Any], key: str, default: Any = None, node_id: Optional[str] = None) -> Any:
		"""从指定节点（默认当前节点）的 data 命名空间读取值"""
		entry = self._ensure_node_entry(context, node_id)
		return entry['data'].get(key, default)
	
	def append_node_output(self, context: Dict[str, Any], output: Any, node_id: Optional[str] = None, also_save_as_last_output: bool = True):
		"""为指定节点（默认当前节点）追加一条输出，并可同步更新全局 last_output"""
		entry = self._ensure_node_entry(context, node_id)
		entry['outputs'].append(output)
		if also_save_as_last_output:
			self._save_to_flow_state(context, 'last_output', output, also_save_as_last_output=False)
	
	def get_node_outputs(self, context: Dict[str, Any], node_id: Optional[str] = None) -> List[Any]:
		"""获取指定节点（默认当前节点）的所有历史输出"""
		entry = self._ensure_node_entry(context, node_id)
		return entry['outputs']
	
	def get_last_output_of_node(self, context: Dict[str, Any], node_id: Optional[str] = None, default: Any = None) -> Any:
		"""获取指定节点（默认当前节点）的最后一次输出"""
		outputs = self.get_node_outputs(context, node_id)
		return outputs[-1] if outputs else default
	
	# ===== 标准输入/输出辅助 =====
	def prepare_inputs(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
		"""标准化节点输入，支持模板渲染
		
		优先读取 config.input（dict）作为输入字段来源；可使用 {{var}} 模板引用 flow_state 中的数据。
		基础输入包含：
		- message: 当前消息
		- last_output: 全局最后输出
		- flow_state: 全部流程状态（供高级模板引用）
		"""
		flow_state = self._get_flow_state(context)
		base_inputs = {
			'message': message,
			'last_output': flow_state.get('last_output'),
			'flow_state': flow_state
		}
		config_inputs = self.config.get('input') or {}
		# 模板渲染：允许在 input 中引用 base_inputs + flow_state 扁平变量
		variables = {**base_inputs, **flow_state}
		rendered_inputs = self._render_template_value(config_inputs, variables) if config_inputs else {}
		return {**base_inputs, **rendered_inputs}
	
	def save_output(self, context: Dict[str, Any], output: Any):
		"""标准化保存节点输出
		
		- 追加到当前节点的 outputs 列表
		- 更新全局 last_output
		- 若 config.save_as 存在，同时保存到 flow_state[save_as]
		"""
		self.append_node_output(context, output, node_id=self.id, also_save_as_last_output=True)
		save_as = self.config.get('save_as')
		if save_as:
			self._save_to_flow_state(context, save_as, output, also_save_as_last_output=False)
	
	# ===== 挂载容器（可选） =====
	def get_mount_spec(self) -> Optional[Dict[str, Any]]:
		"""返回挂载容器规范，例如:
		{
			'type': 'docker',
			'image': 'my/browser:latest',
			'options': {'shm_size': '2g'}
		}
		"""
		mount = self.config.get('mount')
		return mount if isinstance(mount, dict) else None
	
	def requires_mount(self) -> bool:
		"""是否需要挂载容器（例如浏览器类节点）"""
		return self.get_mount_spec() is not None
	
	@abstractmethod
	async def execute(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		agent_name: str = None
	) -> AgentMessage:
		"""执行节点（同步方式）
		
		Args:
			user_id: 用户ID
			message: 用户消息
			context: 上下文字典（包含 flow_state）
			agent_name: 智能体名称
			
		Returns:
			AgentMessage: 执行结果消息
		"""
		pass
	
	@abstractmethod
	async def execute_stream(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		agent_name: str = None
	) -> AsyncGenerator[StreamChunk, None]:
		"""执行节点（流式方式）
		
		Args:
			user_id: 用户ID
			message: 用户消息
			context: 上下文字典（包含 flow_state）
			agent_name: 智能体名称
			
		Yields:
			StreamChunk: 流式响应块
		"""
		pass
	
	def _create_agent_message(
		self,
		content: str,
		agent_name: str = None,
		metadata: Optional[Dict[str, Any]] = None
	) -> AgentMessage:
		"""创建 AgentMessage 的辅助方法
		
		Args:
			content: 消息内容
			agent_name: 智能体名称
			metadata: 元数据
			
		Returns:
			AgentMessage 实例
		"""
		from models.chat_models import MessageType
		# 优先使用 config 中的 nodeType（如果存在），否则使用 implementation
		node_type = self.config.get('nodeType') or self.implementation
		base_metadata = {
			'node_id': self.id,
			'node_category': self.category.value,
			'node_implementation': self.implementation,
			'node_type': node_type,  # 添加 node_type，优先使用 config 中的 nodeType
			'node_name': self.name,
			'node_label': self.label
		}
		if metadata:
			base_metadata.update(metadata)
		
		return AgentMessage(
			id=str(uuid.uuid4()),
			type=MessageType.AGENT,
			content=content,
			agent_name=agent_name or "FlowAgent",
			metadata=base_metadata
		)
	
	def _create_stream_chunk(
		self,
		chunk_type: str,
		content: str,
		session_id: Optional[str] = None,
		agent_name: str = None,
		metadata: Optional[Dict[str, Any]] = None,
		is_end: bool = False
	) -> StreamChunk:
		"""创建 StreamChunk 的辅助方法
		
		Args:
			chunk_type: 块类型（content, node_start, node_complete, tool_result等）
			content: 内容
			session_id: 会话ID
			agent_name: 智能体名称
			metadata: 元数据
			is_end: 是否为最后一个块
			
		Returns:
			StreamChunk 实例
		"""
		# 优先使用 config 中的 nodeType（如果存在），否则使用 implementation
		# 这样可以确保前端保存的 nodeType 被正确传递到 metadata
		node_type = self.config.get('nodeType') or self.implementation
		base_metadata = {
			'node_id': self.id,
			'node_category': self.category.value,
			'node_implementation': self.implementation,
			'node_type': node_type,  # 添加 node_type，优先使用 config 中的 nodeType
			'node_name': self.name,
			'node_label': self.label
		}
		if metadata:
			base_metadata.update(metadata)
		
		return StreamChunk(
			chunk_id=str(uuid.uuid4()),
			session_id=session_id,
			type=chunk_type,
			content=content,
			agent_name=agent_name or "FlowAgent",
			metadata=base_metadata,
			is_end=is_end
		)
	
	def to_dict(self) -> Dict[str, Any]:
		"""将节点转换为字典（用于序列化）
		
		Returns:
			节点字典
		"""
		return {
			'id': self.id,
			'category': self.category.value,
			'implementation': self.implementation,
			'name': self.name,
			'label': self.label,
			'config': self.config,
			'position': self.position,
			'connections': self.connections
		}
	
	@classmethod
	def from_config(cls, node_config: Dict[str, Any]) -> 'BaseFlowNode':
		"""从配置字典创建节点实例（工厂方法）
		
		Args:
			node_config: 节点配置字典，格式：
				{
					'id': str,
					'type': str (旧格式，兼容) 或 'category': str,
					'implementation': str (可选，默认为 type),
					'data': {
						'label': str,
						'config': dict,
						'isStartNode': bool (可选)
					}
				}
				
		Returns:
			BaseFlowNode 实例
			
		Raises:
			ValueError: 配置无效时抛出
		"""
		node_id = node_config.get('id')
		if not node_id:
			raise ValueError("节点配置缺少 'id' 字段")
		
		node_data = node_config.get('data', {})
		node_name = node_data.get('label', node_id)
		node_config_dict = node_data.get('config', {})
		position = node_config.get('position', {'x': 0, 'y': 0})
		
		# 优先使用 data.nodeType（前端保存的原始类型），这是最准确的节点类型
		# 需要将前端的 nodeType 映射到后端的 implementation
		node_type_mapping = {
			'llm': 'llm',
			'tool': 'tool',
			'router': 'router',
			'start': 'start',
			'end': 'end',
			'knowledgeBase': 'knowledge_base',
			'knowledge_base': 'knowledge_base',
			'agent': 'agent',
			'action': 'tool',  # action 映射为 tool
			'auto_infer': 'auto_param'
		}
		
		# 优先使用 data.nodeType
		data_node_type = node_data.get('nodeType')
		if data_node_type:
			# 将前端的 nodeType 映射到后端的 implementation
			implementation = node_type_mapping.get(data_node_type, data_node_type)
			# 根据 implementation 推断 category
			category = cls._infer_category_from_type(implementation)
		else:
			# 如果没有 data.nodeType，使用新格式（category 和 implementation）
			# 如果配置中有 category，优先使用它
			category_str = node_config.get('category')
			if category_str:
				try:
					category = NodeCategory(category_str)
				except ValueError:
					raise ValueError(f"未知的节点类别: {category_str}")
				# implementation 从配置中获取，如果没有则使用 category
				implementation = node_config.get('implementation', category_str)
			else:
				# 兼容旧格式：如果只有 type，则作为 category 和 implementation
				node_type_str = node_config.get('type')
				if node_type_str:
					# 旧格式：type 直接作为 implementation
					implementation = node_config.get('implementation', node_type_str)
					# 根据 type 推断 category
					category = cls._infer_category_from_type(node_type_str)
				else:
					# 如果都没有，默认使用 PROCESSOR
					category = NodeCategory.PROCESSOR
					implementation = node_config.get('implementation', 'llm')
		
		# 确保 label 被保存到 config 中
		if node_name:
			node_config_dict['label'] = node_name
		
		# 确保 nodeType 被保存到 config 中（如果存在），用于后续识别节点类型
		if data_node_type:
			node_config_dict['nodeType'] = data_node_type
		
		# 使用注册表创建节点
		return NodeRegistry.create_node(
			node_id=node_id,
			category=category,
			implementation=implementation,
			name=node_name,
			config=node_config_dict,
			position=position
		)
	
	@staticmethod
	def _infer_category_from_type(node_type: str) -> NodeCategory:
		"""从旧格式的 type 推断新的 category（兼容性方法）"""
		type_mapping = {
			'llm': NodeCategory.PROCESSOR,
			'tool': NodeCategory.PROCESSOR,
			'agent': NodeCategory.PROCESSOR,
			'router': NodeCategory.ROUTER,
			'judge': NodeCategory.ROUTER,
			'knowledge_base': NodeCategory.PROCESSOR,
			'start': NodeCategory.START,
			'end': NodeCategory.END,
		}
		return type_mapping.get(node_type, NodeCategory.PROCESSOR)
	
	def __repr__(self) -> str:
		"""节点的字符串表示"""
		return f"<{self.__class__.__name__}(id={self.id}, category={self.category.value}, implementation={self.implementation}, name={self.name})>"
