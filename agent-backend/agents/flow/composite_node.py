"""
复合节点：将多个节点和流程组合成复合节点

复合节点可以将一个完整的子流程封装成一个节点，实现流程的模块化和复用。
"""
from typing import Dict, Any, AsyncGenerator, Optional
from .base_node import BaseFlowNode, NodeCategory
from .engine import FlowEngine
from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger

logger = get_logger("flow_composite_node")


class CompositeNode(BaseFlowNode):
	"""复合节点：封装一个子流程
	
	配置格式：
	{
		"subflow": {
			"nodes": [...],
			"edges": [...]
		},
		"input_mapping": {
			"subflow_input": "parent_flow_state_key"
		},
		"output_mapping": {
			"subflow_output": "parent_flow_state_key"
		}
	}
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
		super().__init__(node_id, category, implementation, name, config, position)
		self._subflow_engine: Optional[FlowEngine] = None
		self._initialize_subflow()
	
	def _initialize_subflow(self):
		"""初始化子流程引擎"""
		subflow_config = self.config.get('subflow')
		if not subflow_config:
			logger.warning(f"复合节点 {self.id} 未配置子流程")
			return
		
		try:
			# 创建子流程引擎
			self._subflow_engine = FlowEngine()
			self._subflow_engine.build_from_config(subflow_config)
			logger.info(f"复合节点 {self.id} 子流程初始化成功，包含 {len(self._subflow_engine._node_map)} 个节点")
		except Exception as e:
			logger.error(f"复合节点 {self.id} 子流程初始化失败: {str(e)}")
			self._subflow_engine = None
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行复合节点（同步）"""
		if not self._subflow_engine:
			error_msg = f"复合节点 {self.id} 子流程未初始化"
			logger.error(error_msg)
			return self._create_agent_message(error_msg, agent_name, metadata={'error': error_msg})
		
		try:
			# 准备子流程的输入
			subflow_context = self._prepare_subflow_context(context)
			
			# 执行子流程
			result = await self._subflow_engine.run(
				user_id=user_id,
				message=message,
				context=subflow_context,
				start_node_id=None  # 使用默认起始节点
			)
			
			# 提取子流程的输出
			output = self._extract_subflow_output(subflow_context, result)
			
			# 将输出映射回父流程状态
			self._map_output_to_parent(context, output)
			
			return self._create_agent_message(output, agent_name, metadata={
				'composite_node_id': self.id,
				'subflow_result': result
			})
		except Exception as e:
			logger.error(f"复合节点 {self.id} 执行失败: {str(e)}")
			error_msg = f"复合节点执行失败: {str(e)}"
			return self._create_agent_message(error_msg, agent_name, metadata={'error': str(e)})
	
	async def execute_stream(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		agent_name: str = None
	) -> AsyncGenerator[StreamChunk, None]:
		"""执行复合节点（流式）"""
		if not self._subflow_engine:
			error_msg = f"复合节点 {self.id} 子流程未初始化"
			logger.error(error_msg)
			yield self._create_stream_chunk(
				chunk_type="error",
				content=error_msg,
				agent_name=agent_name,
				metadata={'error': error_msg}
			)
			return
		
		try:
			# 准备子流程的输入
			subflow_context = self._prepare_subflow_context(context)
			
			# 执行子流程（流式）
			accumulated_output = ""
			async for chunk in self._subflow_engine.run_stream(
				user_id=user_id,
				message=message,
				context=subflow_context,
				start_node_id=None
			):
				# 透传子流程的块，但添加复合节点标识
				if chunk.type == "content":
					accumulated_output += chunk.content
				
				# 修改metadata，添加复合节点信息
				chunk_metadata = chunk.metadata or {}
				chunk_metadata['composite_node_id'] = self.id
				chunk_metadata['parent_node_id'] = self.id
				
				yield self._create_stream_chunk(
					chunk_type=chunk.type,
					content=chunk.content,
					agent_name=chunk.agent_name or agent_name,
					metadata=chunk_metadata,
					is_end=chunk.is_end
				)
			
			# 提取最终输出并映射回父流程
			final_output = accumulated_output or subflow_context.get('flow_state', {}).get('last_output', '')
			self._map_output_to_parent(context, final_output)
			
		except Exception as e:
			logger.error(f"复合节点 {self.id} 流式执行失败: {str(e)}")
			yield self._create_stream_chunk(
				chunk_type="error",
				content=f"复合节点执行失败: {str(e)}",
				agent_name=agent_name,
				metadata={'error': str(e)}
			)
	
	def _prepare_subflow_context(self, parent_context: Dict[str, Any]) -> Dict[str, Any]:
		"""准备子流程的上下文"""
		# 复制父流程的上下文
		subflow_context = parent_context.copy()
		
		# 创建子流程的flow_state
		parent_flow_state = parent_context.get('flow_state', {})
		subflow_flow_state = {}
		
		# 应用输入映射
		input_mapping = self.config.get('input_mapping', {})
		for subflow_key, parent_key in input_mapping.items():
			value = parent_flow_state.get(parent_key)
			if value is not None:
				subflow_flow_state[subflow_key] = value
		
		# 如果没有映射，直接复制last_output
		if not input_mapping and 'last_output' in parent_flow_state:
			subflow_flow_state['last_output'] = parent_flow_state['last_output']
		
		subflow_context['flow_state'] = subflow_flow_state
		
		return subflow_context
	
	def _extract_subflow_output(self, subflow_context: Dict[str, Any], result: AgentMessage) -> str:
		"""提取子流程的输出"""
		subflow_flow_state = subflow_context.get('flow_state', {})
		
		# 优先使用output_mapping指定的输出
		output_mapping = self.config.get('output_mapping', {})
		if output_mapping:
			for parent_key, subflow_key in output_mapping.items():
				value = subflow_flow_state.get(subflow_key)
				if value is not None:
					return str(value)
		
		# 否则使用last_output或result.content
		return subflow_flow_state.get('last_output') or result.content or ""
	
	def _map_output_to_parent(self, parent_context: Dict[str, Any], output: str):
		"""将子流程的输出映射回父流程状态"""
		parent_flow_state = self._get_flow_state(parent_context)
		
		# 应用输出映射
		output_mapping = self.config.get('output_mapping', {})
		if output_mapping:
			# 如果配置了映射，将输出保存到指定的键
			for parent_key, subflow_key in output_mapping.items():
				parent_flow_state[parent_key] = output
		else:
			# 否则保存为last_output
			parent_flow_state['last_output'] = output
		
		# 同时保存到节点的save_as配置
		save_as = self.config.get('save_as', 'last_output')
		parent_flow_state[save_as] = output
	
	def to_dict(self) -> Dict[str, Any]:
		"""将复合节点转换为字典"""
		base_dict = super().to_dict()
		# 添加子流程信息
		if self._subflow_engine:
			base_dict['subflow'] = {
				'nodes': [node.to_dict() for node in self._subflow_engine._node_map.values()],
				'edges': []  # 可以从_adj重建edges
			}
		return base_dict

