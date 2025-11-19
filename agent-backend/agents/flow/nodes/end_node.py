"""结束节点实现"""
from typing import Dict, Any, AsyncGenerator

from models.chat_models import AgentMessage, StreamChunk

from ..base_node import BaseFlowNode


class EndNode(BaseFlowNode):
	"""结束节点：流程出口，输出最终结果"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""结束节点执行：返回最终结果"""
		flow_state = self._get_flow_state(context)
		final_content = flow_state.get('last_output', '')
		return self._create_agent_message(final_content, agent_name, metadata={'is_final': True})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""结束节点流式执行"""
		end_content = "结束"
		
		self.append_node_output(context, end_content, node_id=self.id, also_save_as_last_output=False)
		
		yield self._create_stream_chunk(
			chunk_type="content",
			content=end_content,
			agent_name=agent_name,
			metadata={'is_final': True}
		)
		
		flow_state = self._get_flow_state(context)
		final_content = flow_state.get('last_output', '')
		
		if not final_content or final_content == end_content:
			nodes = flow_state.get('nodes', {})
			has_real_output = False
			for node_id, node_data in nodes.items():
				if node_id == self.id or node_id == 'start_node':
					continue
				outputs = node_data.get('outputs', [])
				if outputs:
					last_output = outputs[-1] if isinstance(outputs, list) else outputs
					if last_output and isinstance(last_output, str) and last_output.strip() and last_output not in ["开始", "结束"]:
						has_real_output = True
						break
			
			if has_real_output:
				final_content = "✅ 流程执行完成"
			else:
				final_content = end_content
		
		yield self._create_stream_chunk(
			chunk_type="final",
			content=final_content,
			agent_name=agent_name,
			is_end=True,
			metadata={'is_final': True}
		)

