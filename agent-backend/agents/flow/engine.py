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
		"""
		nodes_cfg: List[Dict[str, Any]] = graph_config.get('nodes', [])
		edges_cfg: List[Dict[str, Any]] = graph_config.get('edges', [])
		
		self._node_map.clear()
		self._adj.clear()
		self._in_degree.clear()
		
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
		
		return self
	
	def get_start_node_id(self, explicit_start: Optional[str] = None) -> Optional[str]:
		if explicit_start and explicit_start in self._node_map:
			return explicit_start
		# 优先：类别为 START
		for node in self._node_map.values():
			if node.category == NodeCategory.START:
				return node.id
		# 其次：入度为 0 的节点
		candidates = [nid for nid, deg in self._in_degree.items() if deg == 0]
		return candidates[0] if candidates else (next(iter(self._node_map.keys())) if self._node_map else None)
	
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
		
		final_chunk = None
		
		while current_id:
			node = self._node_map.get(current_id)
			if not node:
				logger.warning(f"Node not found: {current_id}")
				break
			
			# 发送节点开始事件
			node_start_chunk = node._create_stream_chunk(
				chunk_type="node_start",
				content=node.name,
				session_id=session_id,
				agent_name=agent_name,
				metadata={"node_id": node.id}
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
			async for chunk in node.execute_stream(user_id=user_id, message=message, context=context, agent_name=agent_name):
				# 若为内容流，尝试增量保存 last_output
				try:
					if chunk.type == "content" and hasattr(node, "save_output") and chunk.content is not None:
						node.save_output(context, chunk.content)
				except Exception:
					pass
				
				# 调用钩子处理块
				if self.on_chunk:
					chunk = self.on_chunk(chunk)
				
				# 如果是最终块，保存引用
				if chunk and chunk.type == "final":
					final_chunk = chunk
				
				# 透传节点流
				if chunk:
					yield chunk
			
			# 发送节点完成事件
			node_complete_chunk = node._create_stream_chunk(
				chunk_type="node_complete",
				content=node.name,
				session_id=session_id,
				agent_name=agent_name,
				metadata={"node_id": node.id, "output": context.get('flow_state', {}).get('last_output')}
			)
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
			
			current_id = next_id
		
		# 如果没有最终块，创建一个
		if not final_chunk:
			final_content = context.get('flow_state', {}).get('last_output', '')
			final_chunk = StreamChunk(
				chunk_id=str(uuid.uuid4()),
				session_id=session_id,
				type="final",
				content=final_content,
				agent_name=agent_name or "FlowEngine",
				is_end=True
			)
		
		# 调用最终钩子
		if self.on_final:
			try:
				self.on_final(final_chunk)
			except Exception as e:
				logger.error(f"Final hook failed: {e}")
		
		# 发送最终块
		if self.on_chunk:
			final_chunk = self.on_chunk(final_chunk) or final_chunk
		if final_chunk:
			yield final_chunk


