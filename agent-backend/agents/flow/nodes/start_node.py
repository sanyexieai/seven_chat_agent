"""开始节点实现"""
from typing import Dict, Any, AsyncGenerator

from models.chat_models import AgentMessage, StreamChunk

from ..base_node import BaseFlowNode


class StartNode(BaseFlowNode):
	"""起始节点：流程入口，通常只是传递消息"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""起始节点执行：保存初始消息"""
		self.save_output(context, message)
		return self._create_agent_message(f"流程开始: {message}", agent_name)
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""起始节点流式执行"""
		self.save_output(context, message)
		start_content = "开始"
		self.append_node_output(context, start_content, node_id=self.id, also_save_as_last_output=False)
		yield self._create_stream_chunk(
			chunk_type="content",
			content=start_content,
			agent_name=agent_name
		)

