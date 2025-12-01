from typing import Any, Dict, List, Optional, AsyncGenerator, Callable, Tuple
from utils.log_helper import get_logger
from .base_node import BaseFlowNode, NodeCategory, NodeRegistry
from models.chat_models import AgentMessage, StreamChunk
import uuid
import asyncio

logger = get_logger("flow_engine")


class FlowEngine:
	"""
	工作流引擎：负责构建与执行由 BaseFlowNode 组成的节点有向图
	
	能力：
	- 从 {nodes, edges} 配置构建图
	- 自动检测起始节点（显式指定、START类别、或入度为0）
	- 顺序执行节点；路由节点通过其 connections 决定下一跳
	- 同步与流式执行（yield StreamChunk）
	- 标准化发出 node_start/node_complete 事件
	- 通过节点的 requires_mount()/get_mount_spec() 暴露挂载容器的钩子
	
	可插拔点：
	- mount_provider: Callable[[Dict[str, Any]], Any]
	  负责根据 mount 规范准备外部环境（例如 Docker 容器），返回可选的 handler
	- on_chunk: Callable[[StreamChunk], Optional[StreamChunk]]
	  处理每个流式块的回调，可以修改或过滤块
	- on_final: Callable[[StreamChunk], None]
	  处理最终响应的回调，用于保存数据等业务逻辑
	"""
	
	def __init__(
		self,
		mount_provider: Optional[Callable[[Dict[str, Any]], Any]] = None,
		on_chunk: Optional[Callable[[StreamChunk], Optional[StreamChunk]]] = None,
		on_final: Optional[Callable[[StreamChunk], None]] = None
	):
		self.mount_provider = mount_provider
		self.on_chunk = on_chunk
		self.on_final = on_final
		self._node_map: Dict[str, BaseFlowNode] = {}
		self._adj: Dict[str, List[Optional[str]]] = {}
		self._in_degree: Dict[str, int] = {}
	
	# ========== 构建 ==========
	def build_from_config(self, graph_config: Dict[str, Any]) -> "FlowEngine":
		"""
		graph_config:
		{
			"nodes": [ node_config, ... ],
			"edges": [
				{"source": "id1", "target": "id2", "sourceIndex": 0}, ...
			]
		}
		- 若不提供 edges，则从各节点 config/connections 中读取
		- 确保第一个节点是开始节点，最后一个节点是结束节点
		"""
		nodes_cfg: List[Dict[str, Any]] = graph_config.get('nodes', [])
		edges_cfg: List[Dict[str, Any]] = graph_config.get('edges', [])
		
		logger.info(f"📋 加载流程配置：nodes={len(nodes_cfg)}, edges={len(edges_cfg)}")
		if edges_cfg:
			logger.info(f"📋 边配置详情：{edges_cfg}")
		
		self._node_map.clear()
		self._adj.clear()
		self._in_degree.clear()
		
		# 确保有开始和结束节点
		has_start = False
		has_end = False
		start_node_id = None
		end_node_id = None
		
		# 检查现有节点
		for cfg in nodes_cfg:
			node_data = cfg.get('data', {})
			node_type = cfg.get('type', '')
			implementation = cfg.get('implementation', node_type)
			
			# 检查是否是开始或结束节点
			if implementation == 'start' or node_data.get('isStartNode'):
				has_start = True
				start_node_id = cfg.get('id')
			if implementation == 'end' or node_data.get('isEndNode'):
				has_end = True
				end_node_id = cfg.get('id')
		
		# 如果没有开始节点，创建默认的开始节点
		if not has_start and nodes_cfg:
			start_node_id = 'start_node'
			start_cfg = {
				'id': start_node_id,
				'type': 'start',
				'implementation': 'start',
				'data': {
					'label': '开始',
					'config': {}
				},
				'position': {'x': 0, 'y': 0}
			}
			nodes_cfg.insert(0, start_cfg)
			logger.info(f"自动添加开始节点: {start_node_id}")
		
		# 如果没有结束节点，创建默认的结束节点
		if not has_end and nodes_cfg:
			end_node_id = 'end_node'
			end_cfg = {
				'id': end_node_id,
				'type': 'end',
				'implementation': 'end',
				'data': {
					'label': '结束',
					'config': {}
				},
				'position': {'x': 0, 'y': 0}
			}
			nodes_cfg.append(end_cfg)
			logger.info(f"自动添加结束节点: {end_node_id}")
			
			# 如果没有边，将最后一个非结束节点连接到结束节点
			if not edges_cfg and len(nodes_cfg) > 1:
				# 找到最后一个非结束节点
				last_non_end = None
				for cfg in reversed(nodes_cfg[:-1]):  # 排除刚添加的结束节点
					if cfg.get('id') != end_node_id:
						last_non_end = cfg.get('id')
						break
				if last_non_end:
					edges_cfg.append({
						'source': last_non_end,
						'target': end_node_id
					})
		
		# 实例化节点
		for cfg in nodes_cfg:
			node = BaseFlowNode.from_config(cfg)
			self._node_map[node.id] = node
			self._adj[node.id] = list(node.connections or [])
			self._in_degree[node.id] = 0
		
		# 应用 edges（覆盖/填充节点的 connections）
		if edges_cfg:
			for node in self._node_map.values():
				self._adj[node.id] = []
			# 将 edge 写入 adjacency（按 sourceIndex 放置，否则 append）
			for e in edges_cfg:
				src = e.get('source')
				tgt = e.get('target')
				idx = e.get('sourceIndex')
				if src not in self._node_map or tgt not in self._node_map:
					logger.warning(f"Edge references unknown node: {src} -> {tgt}")
					continue
				if idx is not None:
					# 扩展长度至 idx+1
					while len(self._adj[src]) <= idx:
						self._adj[src].append(None)
					self._adj[src][idx] = tgt
				else:
					self._adj[src].append(tgt)
		
		# 计算入度
		for src, outs in self._adj.items():
			for tgt in outs:
				if tgt:
					self._in_degree[tgt] = self._in_degree.get(tgt, 0) + 1
		
		# 将 connections 写回节点，保持一致
		for node_id, outs in self._adj.items():
			self._node_map[node_id].set_connections(outs)
		
		# 打印调试信息：显示所有节点及其连接关系
		logger.info(f"📊 流程构建完成，共 {len(self._node_map)} 个节点")
		for node_id, node in self._node_map.items():
			connections = self._adj.get(node_id, [])
			logger.info(f"  - 节点 {node_id} ({node.name}, {node.category.value if hasattr(node.category, 'value') else node.category}, {node.implementation}): 连接 -> {connections}")
		
		return self
	
	def get_start_node_id(self, explicit_start: Optional[str] = None) -> Optional[str]:
		"""获取开始节点ID，确保返回的是开始节点"""
		if explicit_start and explicit_start in self._node_map:
			return explicit_start
		# 优先：类别为 START
		for node in self._node_map.values():
			if node.category == NodeCategory.START:
				return node.id
		# 其次：implementation 为 'start' 的节点
		for node in self._node_map.values():
			if node.implementation == 'start':
				return node.id
		# 再次：入度为 0 的节点
		candidates = [nid for nid, deg in self._in_degree.items() if deg == 0]
		return candidates[0] if candidates else (next(iter(self._node_map.keys())) if self._node_map else None)
	
	def get_end_node_id(self) -> Optional[str]:
		"""获取结束节点ID"""
		# 优先：类别为 END
		for node in self._node_map.values():
			if node.category == NodeCategory.END:
				return node.id
		# 其次：implementation 为 'end' 的节点
		for node in self._node_map.values():
			if node.implementation == 'end':
				return node.id
		# 再次：出度为 0 的节点
		candidates = [nid for nid in self._node_map.keys() if not self._adj.get(nid) or all(not tgt for tgt in self._adj.get(nid, []))]
		return candidates[0] if candidates else None
	
	# ========== 执行（同步） ==========
	async def run(
		self,
		user_id: str,
		message: str,
		context: Optional[Dict[str, Any]],
		start_node_id: Optional[str] = None,
		agent_name: Optional[str] = None
	) -> List[AgentMessage]:
		context = context or {}
		
		# 初始化 Pipeline（如果尚未初始化）
		from .pipeline import get_pipeline
		pipeline = get_pipeline(context)
		pipeline.sync_to_flow_state(context)
		
		results: List[AgentMessage] = []
		
		current_id = self.get_start_node_id(start_node_id)
		if not current_id:
			logger.warning("No start node found.")
			return results
		
		while current_id:
			node = self._node_map.get(current_id)
			if not node:
				logger.warning(f"Node not found: {current_id}")
				break
			
			mount_handler = None
			if node.requires_mount() and self.mount_provider:
				try:
					mount_handler = self.mount_provider(node.get_mount_spec() or {})
				except Exception as e:
					logger.error(f"Mount provider failed for node {node.id}: {e}")
			
			msg = await node.execute(user_id=user_id, message=message, context=context, agent_name=agent_name)
			if msg:
				results.append(msg)
				# 若节点未自行保存，尝试用消息内容保存标准输出
				try:
					if hasattr(node, "save_output") and msg.content is not None:
						node.save_output(context, msg.content)
				except Exception:
					pass
			
			# 选择下一跳
			# 路由节点需要根据选中的分支选择
			if node.category == NodeCategory.ROUTER:
				# 从节点数据中获取选中的分支
				selected_branch = node.get_node_value(context, 'selected_branch', node_id=node.id)
				if selected_branch == 'true' and len(node.connections) > 0:
					next_id = node.connections[0]  # 第一个分支：真值分支
				elif selected_branch == 'false' and len(node.connections) > 1:
					next_id = node.connections[1]  # 第二个分支：假值分支
				elif len(node.connections) > 0:
					next_id = node.connections[0]  # 只有一个分支，继续执行
				else:
					next_id = None
			else:
				next_id = node.get_next_node_id(0)  # 缺省走第一个分支
			
			if node.category == NodeCategory.END:
				next_id = None
			
			current_id = next_id
		
		return results
	
	# ========== 执行（流式） ==========
	async def run_stream(
		self,
		user_id: str,
		message: str,
		context: Optional[Dict[str, Any]],
		start_node_id: Optional[str] = None,
		agent_name: Optional[str] = None,
		session_id: Optional[str] = None
	) -> AsyncGenerator[StreamChunk, None]:
		context = context or {}
		session_id = session_id or str(uuid.uuid4())
		
		current_id = self.get_start_node_id(start_node_id)
		if not current_id:
			logger.warning("No start node found.")
			error_chunk = StreamChunk(
				chunk_id=str(uuid.uuid4()),
				session_id=session_id,
				type="error",
				content="工作流未找到起始节点",
				agent_name=agent_name or "FlowEngine",
				is_end=True
			)
			if self.on_chunk:
				error_chunk = self.on_chunk(error_chunk) or error_chunk
			if error_chunk:
				yield error_chunk
			return
		
		logger.info(f"FlowEngine.run_stream 开始执行，start_node_id={current_id}, session_id={session_id}, on_final={self.on_final is not None}")
		final_chunk = None
		
		while current_id:
			node = self._node_map.get(current_id)
			if not node:
				logger.warning(f"Node not found: {current_id}")
				break
			
			# 发送节点开始事件
			# _create_stream_chunk 会自动添加 node_id, node_category, node_implementation, node_name, node_label 到 metadata
			node_start_chunk = node._create_stream_chunk(
				chunk_type="node_start",
				content=node.name,
				session_id=session_id,
				agent_name=agent_name,
				metadata={}  # 基础信息由 _create_stream_chunk 自动添加
			)
			if self.on_chunk:
				node_start_chunk = self.on_chunk(node_start_chunk)
			if node_start_chunk:
				yield node_start_chunk
			
			mount_handler = None
			if node.requires_mount() and self.mount_provider:
				try:
					mount_handler = self.mount_provider(node.get_mount_spec() or {})
				except Exception as e:
					logger.error(f"Mount provider failed for node {node.id}: {e}")
			
			# 执行节点流
			# 收集当前节点的输出内容（从 content chunk 中收集）
			# 注意：只收集属于当前节点的 content chunk，不收集其他类型的 chunk
			node_output_content = ""
			current_node_final_chunk = None  # 当前节点的 final chunk（如果有）
			async for chunk in node.execute_stream(user_id=user_id, message=message, context=context, agent_name=agent_name):
				# 收集 content 类型的 chunk 内容
				if chunk.type == "content" and chunk.content is not None:
					# 累加节点的输出内容
					# 注意：对于流式输出，每个 chunk 是增量内容，直接累加即可
					chunk_content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
					node_output_content += chunk_content
					logger.debug(f"节点 {node.id} 累加 content chunk，当前 node_output_content length={len(node_output_content)}")
					# 若为内容流，尝试增量保存 last_output
					try:
						if hasattr(node, "save_output"):
							node.save_output(context, chunk_content)
					except Exception:
						pass
				# 对于 tool_result 类型，也收集内容（工具节点会同时发送 tool_result 和 content）
				elif chunk.type == "tool_result" and chunk.content is not None:
					# 工具结果已经通过 content chunk 发送，这里不需要重复收集
					pass
				
				# 如果是最终块，在调用钩子之前先保存引用（避免钩子修改或过滤）
				if chunk and chunk.type == "final":
					final_chunk_content = chunk.content if isinstance(chunk.content, str) else str(chunk.content) if chunk.content else ""
					logger.info(f"节点 {node.id} 发送了 final chunk，保存引用，content type={type(chunk.content)}, content length={len(final_chunk_content)}, node_output_content length={len(node_output_content)}, content preview={repr(final_chunk_content[:200]) if final_chunk_content else 'None'}")
					final_chunk = chunk
					current_node_final_chunk = chunk  # 保存当前节点的 final chunk
					
					# 对于 LLM 节点，final chunk 包含完整的输出内容
					# 优先使用 final chunk 的内容（它包含完整的输出），因为它可能比累加的 node_output_content 更完整
					if final_chunk_content:
						# 如果 final chunk 的内容更长或 node_output_content 为空，使用 final chunk 的内容
						if len(final_chunk_content) >= len(node_output_content):
							node_output_content = final_chunk_content
							logger.info(f"节点 {node.id} 使用 final chunk 的内容更新 node_output_content，length={len(node_output_content)}")
						else:
							logger.warning(f"节点 {node.id} final chunk 的内容比 node_output_content 短，final_chunk length={len(final_chunk_content)}, node_output_content length={len(node_output_content)}")
					
					# 注意：不要在这里调用 on_final 钩子，因为流程可能还没有执行到结束节点
					# on_final 钩子应该在所有节点执行完成后调用（在 while 循环结束后）
					# 但是，由于 api/chat.py 在收到 final chunk 后会 break，我们需要延迟调用 on_final
					# 暂时不调用，让流程继续执行到结束节点
					# 但是，我们需要确保消息被保存，所以如果这是第一个 final chunk，先保存消息
					# 但不要 break，让流程继续执行到结束节点
				
				# 调用钩子处理块
				if self.on_chunk:
					chunk = self.on_chunk(chunk)
					# 如果钩子返回 None，说明被过滤了，但我们已经保存了 final_chunk 的引用
				
				# 透传节点流
				if chunk:
					yield chunk
			
			# 节点执行完成后，优先使用收集到的内容
			# 如果没有收集到内容，尝试从节点的 outputs 列表中获取最后输出
			if not node_output_content:
				try:
					node_outputs = node.get_node_outputs(context, node.id)
					if node_outputs:
						# 获取最后一个输出（通常是完整的累积输出）
						# 注意：LLM 节点会多次调用 save_output，每次保存累积内容
						# 所以最后一个输出是完整的输出
						last_output = node_outputs[-1]
						if isinstance(last_output, str):
							node_output_content = last_output
						else:
							node_output_content = str(last_output)
				except Exception:
					pass
			
			# 如果还是没有，尝试从节点的最后输出获取（这个方法会调用 get_node_outputs）
			if not node_output_content:
				try:
					last_output = node.get_last_output_of_node(context, node.id)
					if last_output:
						if isinstance(last_output, str):
							node_output_content = last_output
						else:
							node_output_content = str(last_output)
				except Exception:
					pass
			
			# 如果还是没有，根据节点类型决定
			if not node_output_content:
				if node.category.value == 'start':
					# start 节点通常没有输出内容
					node_output_content = ""
				elif node.category.value == 'end':
					# end 节点如果没有输出内容，使用默认的"结束"
					node_output_content = "结束"
				elif node.category.value == 'router':
					# 路由节点：尝试从路由决策中获取
					try:
						router_decision = context.get('flow_state', {}).get('router_decision', {})
						if router_decision:
							field = router_decision.get('field', '')
							value = router_decision.get('value', '')
							selected_branch = router_decision.get('selected_branch', '')
							node_output_content = f"路由决策: {field}={value} -> {selected_branch}"
					except Exception:
						pass
				else:
					# 其他节点类型，不使用全局 last_output（避免显示错误的内容）
					# 如果确实没有输出，就显示空字符串
					node_output_content = ""
			
			# 发送节点完成事件
			# _create_stream_chunk 会自动添加 node_id, node_category, node_implementation, node_name, node_label 到 metadata
			# 对于 LLM 节点，如果发送了 final chunk，应该使用 final chunk 的内容作为节点输出
			# 否则使用收集到的 node_output_content
			final_output = node_output_content
			if current_node_final_chunk and current_node_final_chunk.content:
				# 如果当前节点发送了 final chunk，优先使用 final chunk 的内容（它包含完整的输出）
				# 但是，如果 node_output_content 更长，说明它已经包含了所有内容，使用它
				final_chunk_content = current_node_final_chunk.content if isinstance(current_node_final_chunk.content, str) else str(current_node_final_chunk.content)
				if len(final_chunk_content) > len(node_output_content):
					final_output = final_chunk_content
					logger.info(f"📝 节点 {node.id} ({node.name}) 使用 final chunk 的内容作为输出，length={len(final_output)}, preview={repr(final_output[:100])}")
				else:
					# node_output_content 已经包含了完整内容，使用它
					final_output = node_output_content
					logger.info(f"📝 节点 {node.id} ({node.name}) 使用收集到的 node_output_content（比 final chunk 更长），length={len(final_output)}, preview={repr(final_output[:100])}")
			elif node_output_content:
				logger.info(f"📝 节点 {node.id} ({node.name}) 使用收集到的 node_output_content，length={len(node_output_content)}, preview={repr(node_output_content[:100])}")
			else:
				logger.warning(f"⚠️ 节点 {node.id} ({node.name}) 没有输出内容")
			
			node_complete_chunk = node._create_stream_chunk(
				chunk_type="node_complete",
				content=node.name,
				session_id=session_id,
				agent_name=agent_name,
				metadata={"output": final_output}  # 使用当前节点的输出，而不是全局的 last_output
			)
			logger.info(f"📤 发送节点完成事件：node_id={node.id}, output length={len(final_output) if final_output else 0}")
			if self.on_chunk:
				node_complete_chunk = self.on_chunk(node_complete_chunk)
			if node_complete_chunk:
				yield node_complete_chunk
			
			# 选择下一跳
			# 路由节点需要根据选中的分支选择
			if node.category == NodeCategory.ROUTER:
				# 从节点数据中获取选中的分支
				selected_branch = node.get_node_value(context, 'selected_branch', node_id=node.id)
				if selected_branch == 'true' and len(node.connections) > 0:
					next_id = node.connections[0]  # 第一个分支：真值分支
				elif selected_branch == 'false' and len(node.connections) > 1:
					next_id = node.connections[1]  # 第二个分支：假值分支
				elif len(node.connections) > 0:
					next_id = node.connections[0]  # 只有一个分支，继续执行
				else:
					next_id = None
			else:
				next_id = node.get_next_node_id(0)
			
			if node.category == NodeCategory.END:
				next_id = None
			
			logger.info(f"🔄 节点 {node.id} ({node.name}) 执行完成，下一个节点: {next_id}, 当前连接列表: {node.connections}")
			current_id = next_id
		
		# while循环结束后，处理最终块和钩子
		logger.info(f"while循环结束，current_id={current_id}, final_chunk={final_chunk is not None}")
		
		# 如果没有最终块，创建一个
		if not final_chunk:
			final_content = context.get('flow_state', {}).get('last_output', '')
			logger.info(f"未找到 final chunk，创建新的 final chunk，content length={len(final_content) if final_content else 0}")
			# 在最终响应中包含 flow_state（包含 pipeline 数据）
			flow_state = context.get('flow_state', {})
			final_chunk = StreamChunk(
				chunk_id=str(uuid.uuid4()),
				session_id=session_id,
				type="final",
				content=final_content,
				agent_name=agent_name or "FlowEngine",
				metadata={
					'flow_state': flow_state  # 包含 pipeline_data, pipeline_files, pipeline_history
				},
				is_end=True
			)
		else:
			logger.info(f"找到 final chunk，type={final_chunk.type}, content length={len(final_chunk.content) if final_chunk.content else 0}")
		
		# 调用最终钩子（在yield之前调用，确保消息被保存）
		# 注意：如果 final chunk 已经在 while 循环中被处理，on_final 已经在那个时候被调用了
		# 但是，此时所有节点应该都已经完成了，所以需要再次保存节点信息以确保所有节点输出都被保存
		if self.on_final:
			if not final_chunk:
				# 如果没有 final chunk，创建一个并调用 on_final
				try:
					logger.info(f"while循环结束后没有 final chunk，创建新的并调用 on_final 钩子")
					self.on_final(final_chunk)
					logger.info("on_final 钩子执行完成")
				except Exception as e:
					logger.error(f"Final hook failed: {e}", exc_info=True)
			else:
				# 此时所有节点应该都已经完成了，包括结束节点
				# 调用 on_final 钩子保存消息和节点信息
				try:
					logger.info(f"while循环结束后调用 on_final 钩子，final_chunk type={final_chunk.type}, content length={len(final_chunk.content) if final_chunk.content else 0}")
					self.on_final(final_chunk)
					logger.info("on_final 钩子执行完成")
				except Exception as e:
					logger.error(f"Final hook failed: {e}", exc_info=True)
		else:
			logger.warning("on_final 钩子未设置，无法保存助手消息")
		
		# 发送最终块（在on_final之后发送，确保消息已保存）
		# 确保 final_chunk 包含 flow_state（如果还没有）
		if final_chunk and not final_chunk.metadata.get('flow_state'):
			flow_state = context.get('flow_state', {})
			if final_chunk.metadata:
				final_chunk.metadata['flow_state'] = flow_state
			else:
				final_chunk.metadata = {'flow_state': flow_state}
		
		if self.on_chunk:
			final_chunk = self.on_chunk(final_chunk) or final_chunk
		if final_chunk:
			logger.info(f"yield final chunk，type={final_chunk.type}, content length={len(final_chunk.content) if final_chunk.content else 0}")
			yield final_chunk
		
		logger.info("FlowEngine.run_stream 执行完成")


