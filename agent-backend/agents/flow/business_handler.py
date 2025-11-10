"""
工作流引擎业务逻辑处理器

负责处理与工作流执行相关的业务逻辑，如：
- 保存消息到数据库
- 收集节点信息
- 保存工具执行结果
- 保存实时跟随汇总等

这些逻辑通过钩子机制注入到工作流引擎中，实现业务逻辑与引擎的分离。
"""
from typing import Dict, Any, List, Optional, Callable
from models.chat_models import StreamChunk
from utils.log_helper import get_logger
from sqlalchemy.orm import Session
import json

logger = get_logger("flow_business_handler")


class FlowBusinessHandler:
	"""工作流业务逻辑处理器"""
	
	def __init__(self, db: Optional[Session] = None):
		"""
		初始化业务逻辑处理器
		
		Args:
			db: 数据库会话（可选）
		"""
		self.db = db
		self.collected_nodes: List[Dict[str, Any]] = []
		self.tools_used: List[str] = []
		self.live_follow_segments: List[str] = []
		self.final_content: str = ""
		self.agent_name: Optional[str] = None
		self.session_id: Optional[str] = None
		self.user_id: Optional[str] = None
	
	def reset(self):
		"""重置状态，用于新的执行"""
		self.collected_nodes.clear()
		self.tools_used.clear()
		self.live_follow_segments.clear()
		self.final_content = ""
		self.agent_name = None
		self.session_id = None
		self.user_id = None
	
	def on_chunk(self, chunk: StreamChunk) -> Optional[StreamChunk]:
		"""
		处理流式块的回调
		
		Args:
			chunk: 流式块
			
		Returns:
			处理后的块（如果需要修改），或 None（透传）
		"""
		# 收集节点信息
		if chunk.type == "node_start" and chunk.metadata:
			node_id = chunk.metadata.get('node_id')
			if node_id:
				existing_node = next(
					(node for node in self.collected_nodes if node['node_id'] == node_id),
					None
				)
				if not existing_node:
					self.collected_nodes.append({
						'node_id': node_id,
						'node_type': chunk.metadata.get('node_type'),
						'node_name': chunk.metadata.get('node_name'),
						'node_label': chunk.metadata.get('node_label'),
						'node_metadata': chunk.metadata
					})
		
		# 更新节点输出
		if chunk.type == "node_complete" and chunk.metadata:
			node_id = chunk.metadata.get('node_id')
			if node_id:
				existing_node = next(
					(node for node in self.collected_nodes if node['node_id'] == node_id),
					None
				)
				if existing_node and chunk.metadata.get('output'):
					existing_node['output'] = chunk.metadata.get('output')
		
		# 收集工具使用信息
		if chunk.type == "tool_result" and chunk.metadata:
			tool_name = chunk.metadata.get('tool_name', '')
			if tool_name and tool_name not in self.tools_used:
				self.tools_used.append(tool_name)
			
			# 收集实时跟随片段
			try:
				content_str = chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content, ensure_ascii=False)
				self.live_follow_segments.append(f"[{tool_name}]\n{content_str}")
			except Exception:
				pass
			
			# 保存工具执行结果到数据库
			if self.session_id and self.db:
				try:
					from models.database_models import MessageCreate
					from services.session_service import MessageService
					
					tool_message_data = MessageCreate(
						session_id=self.session_id,
						user_id=self.user_id,
						message_type="tool",
						content=content_str,
						agent_name=self.agent_name or "FlowAgent",
						metadata={"tool_name": tool_name}
					)
					MessageService.create_message(self.db, tool_message_data)
				except Exception as e:
					logger.warning(f"保存工具执行结果失败: {str(e)}")
		
		# 收集最终内容
		if chunk.type == "final":
			self.final_content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
		
		# 透传块
		return chunk
	
	def on_final(self, final_chunk: StreamChunk) -> None:
		"""
		处理最终响应的回调
		负责保存所有消息、节点信息等到数据库
		
		Args:
			final_chunk: 最终响应块
		"""
		if not self.session_id or not self.db:
			return
		
		try:
			from models.database_models import MessageCreate
			from services.session_service import MessageService
			
			# 这里需要从上下文中获取用户消息，暂时跳过用户消息的保存
			# 因为用户消息应该在请求开始时保存
			
			# 保存助手回复
			assistant_message_data = MessageCreate(
				session_id=self.session_id,
				user_id=self.user_id,
				message_type="assistant",
				content=self.final_content or final_chunk.content,
				agent_name=self.agent_name or "FlowAgent",
				metadata={"tools_used": self.tools_used}
			)
			assistant_message = MessageService.create_message(self.db, assistant_message_data)
			
			# 保存节点信息
			if hasattr(assistant_message, 'message_id') and assistant_message.message_id:
				try:
					if self.collected_nodes:
						from models.database_models import MessageNode
						
						for node_info in self.collected_nodes:
							node_record = MessageNode(
								node_id=node_info['node_id'],
								message_id=assistant_message.message_id,
								node_type=node_info.get('node_type'),
								node_name=node_info.get('node_name'),
								node_label=node_info.get('node_label'),
								content=node_info.get('output', ''),
								node_metadata=node_info.get('node_metadata', {})
							)
							self.db.add(node_record)
						
						self.db.commit()
						logger.info(f"成功保存 {len(self.collected_nodes)} 个节点信息，消息ID: {assistant_message.message_id}")
				except Exception as e:
					logger.warning(f"保存节点信息失败: {str(e)}")
					self.db.rollback()
			
			# 保存实时跟随汇总
			try:
				if self.live_follow_segments:
					summary_text = "\n\n".join(self.live_follow_segments)
					MessageService.upsert_workspace_summary(
						db=self.db,
						session_uuid=self.session_id,
						user_id=self.user_id,
						content=summary_text,
						agent_name=self.agent_name or "FlowAgent",
						metadata={"tools_used": self.tools_used, "source": "stream"}
					)
			except Exception as e:
				logger.warning(f"保存实时跟随汇总失败: {str(e)}")
			
			logger.info(f"保存流式聊天消息完成，助手消息ID: {assistant_message.message_id if hasattr(assistant_message, 'message_id') else 'N/A'}")
			
		except Exception as e:
			logger.warning(f"保存流式聊天消息失败: {str(e)}")
	
	def save_user_message(self, message: str) -> None:
		"""
		保存用户消息到数据库
		
		Args:
			message: 用户消息内容
		"""
		if not self.session_id or not self.db:
			return
		
		try:
			from models.database_models import MessageCreate
			from services.session_service import MessageService
			
			user_message_data = MessageCreate(
				session_id=self.session_id,
				user_id=self.user_id,
				message_type="user",
				content=message,
				agent_name=self.agent_name or "FlowAgent"
			)
			MessageService.create_message(self.db, user_message_data)
		except Exception as e:
			logger.warning(f"保存用户消息失败: {str(e)}")
	
	def get_tools_used(self) -> List[str]:
		"""获取使用的工具列表"""
		return self.tools_used.copy()

