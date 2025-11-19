"""路由节点实现"""
from typing import Dict, Any, AsyncGenerator, Optional

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger

from ..base_node import BaseFlowNode


logger = get_logger("flow_router_node")


class RouterNode(BaseFlowNode):
	"""路由节点：根据条件选择分支"""
	
	def _evaluate_condition(self, field_value: Any, routing_config: Dict[str, Any]) -> str:
		"""评估路由条件，返回 'true' 或 'false'"""
		value = routing_config.get('value', None)
		
		if value is not None:
			# 精确值匹配
			return 'true' if field_value == value else 'false'
		
		if isinstance(field_value, bool):
			return 'true' if field_value else 'false'
		
		if isinstance(field_value, (int, float)):
			threshold = routing_config.get('threshold', 0)
			operator = routing_config.get('operator', '>')
			if operator == '>':
				return 'true' if field_value > threshold else 'false'
			if operator == '>=':
				return 'true' if field_value >= threshold else 'false'
			if operator == '<':
				return 'true' if field_value < threshold else 'false'
			if operator == '<=':
				return 'true' if field_value <= threshold else 'false'
			if operator == '==':
				return 'true' if field_value == threshold else 'false'
			return 'false'
		
		if isinstance(field_value, str):
			pattern = routing_config.get('pattern', '')
			if pattern:
				import re
				return 'true' if re.search(pattern, field_value) else 'false'
			return 'true' if field_value else 'false'
		
		return 'false'
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行路由节点（同步）"""
		flow_state = self._get_flow_state(context)
		routing_config = self.config.get('routing_logic', {})
		
		if not routing_config:
			raise ValueError(f"路由节点 {self.id} 未配置路由逻辑")
		
		field = routing_config.get('field', '')
		if not field:
			raise ValueError(f"路由节点 {self.id} 未配置路由字段")
		
		field_value = flow_state.get(field)
		selected_branch = self._evaluate_condition(field_value, routing_config)
		
		logger.info(f"路由节点 {self.id} 字段 {field}={field_value}, 选择分支: {selected_branch}")
		
		flow_state['router_decision'] = {
			'field': field,
			'value': field_value,
			'selected_branch': selected_branch
		}
		
		self.set_node_value(context, 'selected_branch', selected_branch, node_id=self.id)
		self._selected_branch = selected_branch
		
		content = f"路由决策: {field}={field_value} -> {selected_branch}"
		return self._create_agent_message(content, agent_name, metadata={
			'selected_branch': selected_branch,
			'field': field,
			'field_value': field_value
		})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""执行路由节点（流式）"""
		flow_state = self._get_flow_state(context)
		routing_config = self.config.get('routing_logic', {})
		
		if not routing_config:
			error_msg = f"路由节点 {self.id} 未配置路由逻辑"
			yield self._create_stream_chunk(
				chunk_type="error",
				content=error_msg,
				agent_name=agent_name,
				metadata={'error': error_msg}
			)
			return
		
		field = routing_config.get('field', '')
		if not field:
			error_msg = f"路由节点 {self.id} 未配置路由字段"
			yield self._create_stream_chunk(
				chunk_type="error",
				content=error_msg,
				agent_name=agent_name,
				metadata={'error': error_msg}
			)
			return
		
		field_value = flow_state.get(field)
		selected_branch = self._evaluate_condition(field_value, routing_config)
		
		logger.info(f"路由节点 {self.id} 字段 {field}={field_value}, 选择分支: {selected_branch}")
		
		flow_state['router_decision'] = {
			'field': field,
			'value': field_value,
			'selected_branch': selected_branch
		}
		
		self.set_node_value(context, 'selected_branch', selected_branch, node_id=self.id)
		self._selected_branch = selected_branch
		
		content = f"路由决策: {field}={field_value} -> {selected_branch}"
		self.append_node_output(context, content, node_id=self.id, also_save_as_last_output=False)
		
		yield self._create_stream_chunk(
			chunk_type="content",
			content=content,
			agent_name=agent_name,
			metadata={
				'selected_branch': selected_branch,
				'field': field,
				'field_value': field_value
			}
		)
	
	def get_next_node_id(self, branch_index: int = 0) -> Optional[str]:
		"""路由节点重写此方法，根据选中的分支返回下一个节点ID"""
		if hasattr(self, '_selected_branch'):
			selected_branch = self._selected_branch
			if selected_branch == 'true' and len(self.connections) > 0:
				return self.connections[0]
			if selected_branch == 'false' and len(self.connections) > 1:
				return self.connections[1]
			if len(self.connections) > 0:
				return self.connections[0]
		return super().get_next_node_id(branch_index)

