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
		self.assistant_message_id: Optional[str] = None  # 助手消息ID，用于延迟保存节点信息
	
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
					# 从metadata中获取node_type，优先使用node_implementation，如果没有则使用node_category
					node_type = chunk.metadata.get('node_type') or chunk.metadata.get('node_implementation') or chunk.metadata.get('node_category')
					if not node_type:
						# 如果都没有，记录警告并使用默认值
						logger.warning(f"节点 {node_id} 的metadata中缺少node_type/node_implementation/node_category，使用默认值'unknown'")
						node_type = 'unknown'
					
					node_info = {
						'node_id': node_id,
						'node_type': node_type,
						'node_name': chunk.metadata.get('node_name'),
						'node_label': chunk.metadata.get('node_label'),
						'node_metadata': chunk.metadata,
						'output': '',  # 初始化输出为空字符串，后续通过 node_complete 事件更新
						'chunk_count': 0  # 初始化 chunk 计数为 0
					}
					self.collected_nodes.append(node_info)
					logger.info(f"📝 收集节点信息：node_id={node_id}, node_type={node_type}, node_name={chunk.metadata.get('node_name')}, 当前已收集 {len(self.collected_nodes)} 个节点")
		
		# 统计 content chunk 数量（属于当前节点的 content chunk）
		if chunk.type == "content" and chunk.metadata:
			node_id = chunk.metadata.get('node_id')
			if node_id:
				existing_node = next(
					(node for node in self.collected_nodes if node['node_id'] == node_id),
					None
				)
				if existing_node:
					# 增加该节点的 chunk 计数
					existing_node['chunk_count'] = existing_node.get('chunk_count', 0) + 1
		
		# 更新节点输出
		if chunk.type == "node_complete" and chunk.metadata:
			node_id = chunk.metadata.get('node_id')
			if node_id:
				existing_node = next(
					(node for node in self.collected_nodes if node['node_id'] == node_id),
					None
				)
				if existing_node:
					# 从 metadata 中获取节点输出
					node_output = chunk.metadata.get('output', '')
					if node_output:
						existing_node['output'] = node_output
						logger.info(f"✅ 更新节点 {node_id} 的输出，length={len(node_output)}, preview={repr(node_output[:100])}, chunk_count={existing_node.get('chunk_count', 0)}")
						
						# 如果助手消息已经保存，立即更新数据库中的节点信息
						if self.assistant_message_id and self.db:
							self._update_node_info_in_db(node_id, node_output, existing_node.get('chunk_count', 0))
					else:
						logger.warning(f"⚠️ 节点 {node_id} 的 node_complete 事件中没有 output 字段，metadata keys={list(chunk.metadata.keys())}")
				else:
					logger.warning(f"⚠️ 节点 {node_id} 的 node_complete 事件，但未找到已收集的节点信息")
		
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
			logger.info(f"on_chunk 收集到 final chunk，content length={len(self.final_content) if self.final_content else 0}, content preview={self.final_content[:100] if self.final_content else 'None'}")
		
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
			logger.warning(f"无法保存消息：session_id={self.session_id}, db={self.db is not None}")
			return
		
		# 跳过临时会话（以temp_开头的session_id）
		if isinstance(self.session_id, str) and self.session_id.startswith('temp_'):
			logger.info(f"跳过临时会话的消息保存：session_id={self.session_id}")
			return
		
		try:
			from models.database_models import MessageCreate
			from services.session_service import MessageService
			
			# 这里需要从上下文中获取用户消息，暂时跳过用户消息的保存
			# 因为用户消息应该在请求开始时保存
			
			# 确定要保存的内容
			# 注意：on_final 可能在 on_chunk 之前被调用，所以优先使用 final_chunk.content
			# 如果 final_chunk.content 为空，再尝试使用 self.final_content
			content_to_save = None
			if final_chunk and final_chunk.content:
				content_to_save = final_chunk.content if isinstance(final_chunk.content, str) else str(final_chunk.content)
			elif self.final_content:
				content_to_save = self.final_content
			
			# 如果还是没有内容，记录警告
			if not content_to_save:
				logger.warning(f"⚠️ final_chunk.content 和 self.final_content 都为空，无法保存助手消息内容")
				content_to_save = ""
			
			logger.info(f"on_final 准备保存助手消息：session_id={self.session_id}, final_content length={len(self.final_content) if self.final_content else 0}, final_chunk.content length={len(final_chunk.content) if final_chunk.content else 0}, content_to_save length={len(content_to_save) if content_to_save else 0}, content_to_save preview={content_to_save[:100] if content_to_save else 'None'}")
			
			# 如果 final_chunk 有 metadata，尝试从 metadata 中获取节点信息并更新节点输出
			# 这样可以在 node_complete 事件之前就更新节点输出
			if final_chunk and final_chunk.metadata:
				node_id = final_chunk.metadata.get('node_id')
				if node_id:
					# 查找对应的节点并更新输出
					existing_node = next(
						(node for node in self.collected_nodes if node['node_id'] == node_id),
						None
					)
					if existing_node:
						# 如果节点是结束节点，且 content_to_save 为空，使用"结束"
						if existing_node.get('node_type') == 'end' and not content_to_save:
							content_to_save = "结束"
						
						if content_to_save:
							existing_node['output'] = content_to_save
							logger.info(f"✅ 在 on_final 中更新节点 {node_id} 的输出，length={len(content_to_save)}, preview={repr(content_to_save[:100])}")
			
			# 保存助手回复
			assistant_message_data = MessageCreate(
				session_id=self.session_id,
				user_id=self.user_id,
				message_type="assistant",
				content=content_to_save,
				agent_name=self.agent_name or "FlowAgent",
				metadata={"tools_used": self.tools_used}
			)
			assistant_message = MessageService.create_message(self.db, assistant_message_data)
			logger.info(f"✅ 保存助手消息成功：message_id={assistant_message.message_id}, session_id={self.session_id}, content length={len(content_to_save) if content_to_save else 0}")
			
			# 保存助手消息ID，用于后续保存节点信息
			# 注意：节点信息可能在 on_final 之后才更新（通过 node_complete 事件），所以延迟保存
			self.assistant_message_id = assistant_message.message_id
			
			# 尝试立即保存节点信息（如果已经收集到）
			# 注意：此时可能还有节点没有完成，所以节点输出可能还没有被更新
			# 节点信息会在 node_complete 事件中更新，并在所有节点完成后再次保存
			self._save_node_info()
			
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
			logger.warning(f"无法保存用户消息：session_id={self.session_id}, db={self.db is not None}")
			return
		
		# 跳过临时会话（以temp_开头的session_id）
		if isinstance(self.session_id, str) and self.session_id.startswith('temp_'):
			logger.info(f"跳过临时会话的用户消息保存：session_id={self.session_id}")
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
			user_message = MessageService.create_message(self.db, user_message_data)
			logger.info(f"✅ 保存用户消息成功：message_id={user_message.message_id}, session_id={self.session_id}")
		except Exception as e:
			logger.error(f"保存用户消息失败: {str(e)}", exc_info=True)
	
	def get_tools_used(self) -> List[str]:
		"""获取使用的工具列表"""
		return self.tools_used.copy()
	
	def _save_node_info(self) -> None:
		"""保存节点信息到数据库（如果助手消息ID已设置）"""
		if not self.assistant_message_id or not self.db:
			return
		
		try:
			if self.collected_nodes:
				from models.database_models import MessageNode
				
				logger.info(f"准备保存 {len(self.collected_nodes)} 个节点信息，节点列表：{[n['node_id'] for n in self.collected_nodes]}")
				saved_count = 0
				updated_count = 0
				for node_info in self.collected_nodes:
					node_output = node_info.get('output', '')
					node_id = node_info['node_id']
					chunk_count = node_info.get('chunk_count', 0)
					logger.info(f"保存节点记录：node_id={node_id}, node_type={node_info.get('node_type')}, output length={len(node_output) if node_output else 0}, chunk_count={chunk_count}, output preview={repr(node_output[:100]) if node_output else 'None'}")
					
					# 检查节点是否已经保存
					existing_node = self.db.query(MessageNode).filter(
						MessageNode.message_id == self.assistant_message_id,
						MessageNode.node_id == node_id
					).first()
					
					if existing_node:
						# 更新现有节点
						existing_node.content = node_output
						existing_node.node_type = node_info.get('node_type')
						existing_node.node_name = node_info.get('node_name')
						existing_node.node_label = node_info.get('node_label')
						existing_node.node_metadata = node_info.get('node_metadata', {})
						existing_node.chunk_count = chunk_count  # 更新 chunk_count
						updated_count += 1
						logger.info(f"✅ 更新节点记录：node_id={node_id}, chunk_count={chunk_count}")
					else:
						# 创建新节点（即使输出为空也要保存，确保所有节点都被记录）
						node_record = MessageNode(
							node_id=node_id,
							message_id=self.assistant_message_id,
							node_type=node_info.get('node_type', 'unknown'),
							node_name=node_info.get('node_name', node_id),
							node_label=node_info.get('node_label'),
							content=node_output,  # 使用节点的输出作为节点的 content
							node_metadata=node_info.get('node_metadata', {}),
							chunk_count=chunk_count  # 设置 chunk_count
						)
						self.db.add(node_record)
						saved_count += 1
						logger.info(f"✅ 添加节点记录：node_id={node_id}, node_type={node_info.get('node_type')}, chunk_count={chunk_count}")
				
				self.db.commit()
				logger.info(f"✅ 成功保存节点信息：新增 {saved_count} 个，更新 {updated_count} 个，总计 {len(self.collected_nodes)} 个节点，消息ID: {self.assistant_message_id}")
		except Exception as e:
			logger.warning(f"保存节点信息失败: {str(e)}")
			import traceback
			logger.error(traceback.format_exc())
	
	def _update_node_info_in_db(self, node_id: str, node_output: str, chunk_count: int = 0) -> None:
		"""更新数据库中的节点信息"""
		if not self.assistant_message_id or not self.db:
			return
		
		try:
			from models.database_models import MessageNode
			
			existing_node = self.db.query(MessageNode).filter(
				MessageNode.message_id == self.assistant_message_id,
				MessageNode.node_id == node_id
			).first()
			
			if existing_node:
				existing_node.content = node_output
				existing_node.chunk_count = chunk_count  # 更新 chunk_count
				self.db.commit()
				logger.info(f"✅ 更新节点 {node_id} 的输出到数据库，length={len(node_output)}, chunk_count={chunk_count}")
			else:
				# 如果节点不存在，尝试保存所有节点信息
				self._save_node_info()
		except Exception as e:
			logger.warning(f"更新节点信息失败: {str(e)}")

