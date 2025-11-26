"""规划节点实现：根据任务自动生成流程图并执行"""
from typing import Dict, Any, AsyncGenerator, Optional, List, Tuple
from collections import defaultdict
import json
import re

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
from ..base_node import BaseFlowNode
from ..engine import FlowEngine

logger = get_logger("flow_planner_node")

# 规划节点的默认提示词
PLANNER_SYSTEM_PROMPT = """你是一个流程图规划专家。根据用户任务，生成一个可执行的流程图配置。

流程图配置格式（JSON）：
{
  "nodes": [
    {
      "id": "节点唯一ID",
      "type": "节点类型（start/end/llm/tool/router/auto_infer等）",
      "category": "节点类别（start/end/processor/router）",
      "implementation": "节点实现（start/end/llm/tool/router_llm/auto_infer等）",
      "position": {"x": 数字, "y": 数字},
      "data": {
        "label": "节点显示名称",
        "nodeType": "节点类型（与type相同）",
        "config": {
          // 节点特定配置
          // 对于 tool 节点：tool_name, tool_type, server, params 等
          // 对于 llm 节点：system_prompt, user_prompt 等
          // 对于 auto_infer 节点：target_tool_node_id, auto_param_key 等
        },
        "isStartNode": true/false,
        "isEndNode": true/false
      }
    }
  ],
  "edges": [
    {
      "id": "边唯一ID",
      "source": "源节点ID",
      "target": "目标节点ID",
      "type": "default"
    }
  ],
  "metadata": {
    "name": "流程图名称",
    "description": "流程图描述",
    "version": "1.0.0"
  }
}

可用节点类型：
- start: 开始节点（必须有且只有一个）
- end: 结束节点（必须有且只有一个）
- llm: LLM调用节点
- tool: 工具调用节点（需要配置 tool_name, tool_type, server）
- auto_infer: 自动推理节点（用于工具参数推理）
- router: 路由节点（条件判断）

重要规则：
1. **不要包含 start 和 end 节点**（这些节点会在执行时自动添加）
2. **所有节点必须串行连接**（一个接一个，形成一条链，不能有分支或并行）
3. **所有节点都必须在从开始到结束的路径上**（不能有游离节点）
4. 如果使用 tool 节点，建议在前面添加 auto_infer 节点来自动生成参数
5. 节点 ID 必须唯一
6. 只输出 JSON，不要包含其他文字说明"""

PLANNER_USER_PROMPT_TEMPLATE = """请为以下任务生成一个流程图配置：

任务：{task}

上下文信息：
{context}

{error_context}

当前规划信息：
- 规划节点ID：{planner_id}
- 本次规划序号（0表示首次规划，>=1表示第几次重试）：{retry_index}

可用工具列表：
{available_tools}

工具使用规则：
1. **内置工具**：tool_type 为 "builtin"，tool_name 直接使用工具名称（如 "report", "deep_search"），不需要 server 参数
2. **MCP工具**：tool_type 为 "mcp"，tool_name 格式为 "mcp_{{server}}_{{tool_name}}"（如 "mcp_1_search"），server 为服务器编号（字符串格式，如 "1"）
3. **临时工具**：tool_type 为 "temporary"，tool_name 格式为 "temp_{{tool_name}}"，不需要 server 参数
4. 使用工具时，**必须**在前面添加 auto_infer 节点来自动生成参数
5. auto_infer 节点的 target_tool_node_id 应该指向对应的 tool 节点 ID

ID 与连线规则（必须严格遵守）：
1. 所有节点 id 必须使用格式：`{planner_id}_retry_{retry_index}_N`
   - 其中 `N` 从 1 开始递增（1, 2, 3, ...），不要跳号也不要复用旧的 N
2. 重新规划（retry_index >= 1）时：
   - 本次生成的所有节点 id 必须是全新的，**不得与历史节点 id 相同**
   - 禁止复用之前规划产生的任何节点 id
3. edges 中的 source 和 target：
   - 必须全部来自本次 `nodes` 数组中定义的 id
   - **严禁**连接到历史节点或系统自动创建的节点（例如开始、结束或之前规划产生的节点）
4. 不要在本次输出中包含任何 start / end 节点，也不要连接到这些节点

请生成一个完整的流程图配置 JSON，确保：
1. **不要包含 start 和 end 节点**（这些节点会在执行时自动添加）
2. **所有节点必须串行连接**（节点1 -> 节点2 -> 节点3 -> ...，形成一条链，不能有分支）
3. **所有节点都必须在路径上**（每个节点都有且仅有一个前驱和一个后继，除了第一个节点没有前驱，最后一个节点没有后继）
4. 节点配置完整：
   - tool 节点：必须包含 tool_name, tool_type, server（MCP工具需要）
   - auto_infer 节点：必须包含 target_tool_node_id（指向对应的 tool 节点）
5. 如果使用工具，**必须**在前面添加 auto_infer 节点
6. 流程图逻辑清晰，能够完成任务
7. 优先使用系统提供的工具，根据任务需求选择合适的工具

**重要**：edges 数组应该按照节点顺序连接，例如：
- 如果有3个节点 [node1, node2, node3]，edges 应该是 [{{"source": "node1", "target": "node2"}}, {{"source": "node2", "target": "node3"}}]
- 不能有多个节点指向同一个节点，也不能有一个节点指向多个节点
- 所有 edges 的 source/target 必须来自本次 nodes 数组中定义的 id，**禁止连接到历史节点或系统自动创建的节点**（例如开始、结束或之前规划产生的节点）
- 当上文中包含错误信息（说明这是重新规划）时：本次生成的所有节点 id **必须是全新的，不得与历史节点 id 重复**，不要复用之前的节点 id

只输出 JSON 配置，不要包含任何其他文字。"""


class PlannerNode(BaseFlowNode):
	"""规划节点：根据任务自动生成流程图并执行"""
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._generated_flow_config: Optional[Dict[str, Any]] = None
		self._subflow_engine: Optional[FlowEngine] = None
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行规划节点（同步）"""
		try:
			# 1. 生成流程图配置
			flow_config = await self._generate_flow_config(message, context)
			if not flow_config:
				error_msg = "规划节点：生成流程图配置失败"
				logger.error(error_msg)
				return self._create_agent_message(error_msg, agent_name, metadata={'error': error_msg})
			
			# 2. 创建并执行流程图
			result = await self._execute_generated_flow(user_id, message, context, flow_config, agent_name)
			
			return result
		except Exception as e:
			logger.error(f"规划节点 {self.id} 执行失败: {str(e)}")
			error_msg = f"规划节点执行失败: {str(e)}"
			return self._create_agent_message(error_msg, agent_name, metadata={'error': str(e)})
	
	async def execute_stream(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		agent_name: str = None
	) -> AsyncGenerator[StreamChunk, None]:
		"""执行规划节点（流式）"""
		try:
			# 1. 生成流程图配置
			yield self._create_stream_chunk(
				chunk_type="content",
				content="📋 正在规划流程图...\n",
				agent_name=agent_name
			)
			
			flow_config = await self._generate_flow_config(message, context)
			if not flow_config:
				error_msg = "规划节点：生成流程图配置失败"
				logger.error(error_msg)
				yield self._create_stream_chunk(
					chunk_type="content",
					content=f"❌ {error_msg}\n",
					agent_name=agent_name,
					is_end=True
				)
				return
			
			# 输出生成的流程图信息
			flow_name = flow_config.get('metadata', {}).get('name', '未命名流程图')
			generated_nodes = flow_config.get('nodes', [])
			node_count = len(generated_nodes)
			yield self._create_stream_chunk(
				chunk_type="content",
				content=f"✅ 已生成 {node_count} 个节点：{flow_name}\n\n",
				agent_name=agent_name
			)
			
			# 将生成的节点配置保存到 flow_state，以便前端实时更新
			flow_state = self._get_flow_state(context)
			flow_state['planner_generated_nodes'] = generated_nodes
			flow_state['planner_generated_edges'] = flow_config.get('edges', [])
			logger.info(f"规划节点 {self.id} 已将生成的节点配置保存到 flow_state，共 {node_count} 个节点")
			
			# 获取规划节点的原始下一个节点（规划节点在原始流程图中的下一个节点）
			planner_next_node_id = self.get_next_node_id(0) if self.connections else None
			
			# 临时清空规划节点的 connections，移除到原始下一个节点的连接
			# 这样 FlowEngine 就不会继续执行原始的下一个节点，而是等待生成的节点执行完
			original_connections = self.connections.copy() if self.connections else []
			self.connections = []  # 清空连接，避免直接连接到原始下一个节点
			logger.info(f"规划节点 {self.id} 临时清空 connections，原始连接: {original_connections}")
			
			# 发送节点扩展事件给前端（添加到现有流程图，而不是替换）
			# 不再要求前端删除原有规划节点到下一个节点的边，只追加新子流程结构。
			yield self._create_stream_chunk(
				chunk_type="flow_nodes_extend",
				content="",
				agent_name=agent_name,
				metadata={
					'planner_node_id': self.id,
					'planner_next_node_id': planner_next_node_id,  # 规划节点的原始下一个节点
					'nodes': generated_nodes,
					'edges': flow_config.get('edges', []),
					'flow_name': flow_name,
					'node_count': node_count
				}
			)
			
			# 2. 执行生成的节点（流式）
			async for chunk in self._execute_generated_nodes_stream(
				user_id, message, context, generated_nodes,
				flow_config.get('edges', []), planner_next_node_id, agent_name
			):
				yield chunk
				
		except Exception as e:
			logger.error(f"规划节点 {self.id} 流式执行失败: {str(e)}")
			error_msg = f"规划节点执行失败: {str(e)}"
			yield self._create_stream_chunk(
				chunk_type="content",
				content=f"❌ {error_msg}\n",
				agent_name=agent_name,
				is_end=True
			)
	
	def _format_failed_nodes_summary(self, failed_nodes: List[Dict[str, str]]) -> str:
		"""格式化失败节点摘要"""
		if not failed_nodes:
			return ""
		
		summary_parts = ["执行失败的节点："]
		for i, failed in enumerate(failed_nodes, 1):
			summary_parts.append(f"{i}. 节点 {failed['node_name']} ({failed['node_id']}): {failed['error']}")
		
		return "\n".join(summary_parts)
	
	async def _generate_flow_config_with_errors(
		self, 
		task: str, 
		context: Dict[str, Any], 
		error_summary: str,
		retry_index: int,
	) -> Optional[Dict[str, Any]]:
		"""生成包含错误信息的流程图配置（用于重新规划）"""
		try:
			# 获取可用工具列表
			available_tools = await self._get_available_tools()
			
			# 准备上下文信息
			context_info = self._format_context_info(context)
			
			# 构建错误上下文
			error_context = f"""
执行错误信息：
{error_summary}

请根据以上错误信息，重新规划流程图，避免之前的错误：
1. 分析失败节点的错误原因
2. 调整节点配置或替换为其他工具/方法
3. 确保新规划的节点能够成功执行
4. 如果工具调用失败，尝试使用其他工具或调整参数
"""
			
			# 构建提示词
			system_prompt = self.config.get('system_prompt') or PLANNER_SYSTEM_PROMPT
			user_prompt_template = self.config.get('user_prompt') or PLANNER_USER_PROMPT_TEMPLATE
			user_prompt = user_prompt_template.format(
				task=task,
				context=context_info,
				error_context=error_context,
				available_tools=available_tools,
				planner_id=self.id,
				retry_index=retry_index,
			)
			
			# 调用 LLM
			llm_helper = get_llm_helper()
			messages = [
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt}
			]
			
			response = await llm_helper.call(messages, max_tokens=4000)
			
			# 解析 JSON
			flow_config = self._parse_flow_config(response)
			
			if flow_config:
				# 为重新规划得到的流程图也做一次参数推理节点兜底处理
				flow_config = self._ensure_auto_infer_edges(flow_config)
				logger.info(
					f"规划节点 {self.id} 重新规划成功，包含 {len(flow_config.get('nodes', []))} 个节点"
				)
			
			return flow_config
		except Exception as e:
			logger.error(f"规划节点 {self.id} 重新规划失败: {str(e)}")
			return None
	
	def _find_last_node_id(
		self,
		nodes: List[Dict[str, Any]],
		edges: List[Dict[str, Any]]
	) -> Optional[str]:
		"""寻找没有出边的最后一个节点"""
		if not nodes:
			return None
		
		node_ids = [node.get('id') for node in nodes if node.get('id')]
		if not node_ids:
			return None
		
		outgoing_nodes = set()
		for edge in edges or []:
			source = edge.get('source')
			if source:
				outgoing_nodes.add(source)
		
		for node_id in reversed(node_ids):
			if node_id not in outgoing_nodes:
				return node_id
		
		return node_ids[-1]
	
	def _build_display_flow_with_virtual_end(
		self,
		nodes: List[Dict[str, Any]],
		edges: List[Dict[str, Any]],
		last_node_id: Optional[str]
	) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
		"""
		根据生成的节点和边，构建用于前端展示的流程图。
		
		注意：为了保证所有不同路线最终汇聚到全局唯一的结束节点，
		这里不再在子流程内部创建独立的虚拟 end 节点，仅透传原有 nodes/edges。
		"""
		display_nodes = list(nodes)
		display_edges = list(edges)
		return display_nodes, display_edges
	
	def _build_retry_flow_display_nodes(
		self,
		root_planner_id: str,
		retry_index: int,
		nodes: List[Dict[str, Any]],
		edges: List[Dict[str, Any]],
		last_node_id: Optional[str]
	) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
		"""
		构建“重新规划节点 + 新子流程”的展示结构：
		- 在原规划节点下方新增一个虚拟的 retry 节点
		- 从原规划节点连接到 retry 节点
		- 从 retry 节点连接到新子流程的起始节点
		- 子流程末尾不再创建独立的虚拟 end 节点，而是统一连接到全局 end_node
		
		返回：display_nodes, display_edges, retry_node_id
		"""
		# 子流程内部仅使用自身的 nodes/edges，不再创建虚拟 end 节点
		child_nodes, child_edges = self._build_display_flow_with_virtual_end(nodes, edges, last_node_id)

		retry_node_id = f"{root_planner_id}_retry_{retry_index}"
		retry_label = "重新规划" if retry_index == 1 else f"重新规划 {retry_index} 次"

		retry_node = {
			'id': retry_node_id,
			'type': 'planner_retry',
			'nodeType': 'planner_retry',
			'data': {
				'label': retry_label,
				'nodeType': 'planner_retry'
			}
		}

		# 计算子流程起始节点（入度为 0 的节点）
		node_ids = [n.get('id') for n in nodes if n.get('id')]
		target_ids = {e.get('target') for e in edges or [] if e.get('target')}
		start_node_id: Optional[str] = None
		for nid in node_ids:
			if nid not in target_ids:
				start_node_id = nid
				break
		if not start_node_id and node_ids:
			start_node_id = node_ids[0]

		display_nodes = [retry_node] + child_nodes
		display_edges = list(child_edges)

		# 从原规划节点连接到 retry 节点（保证 retry 节点不是孤儿节点）
		display_edges.append({
			'id': f"edge_{root_planner_id}_{retry_node_id}",
			'source': root_planner_id,
			'target': retry_node_id,
			'type': 'default'
		})

		# 从 retry 节点连接到新子流程起始节点（保证子流程与 retry 相连）
		if start_node_id:
			display_edges.append({
				'id': f"edge_{retry_node_id}_{start_node_id}",
				'source': retry_node_id,
				'target': start_node_id,
				'type': 'default'
			})

		# 所有不同的路线最终统一连接到全局唯一的结束节点 end_node
		global_end_id = "end_node"
		if last_node_id:
			display_edges.append({
				'id': f"edge_{last_node_id}_{global_end_id}",
				'source': last_node_id,
				'target': global_end_id,
				'type': 'default'
			})

		return display_nodes, display_edges, retry_node_id
	
	def _ensure_auto_infer_edges(self, flow_config: Dict[str, Any]) -> Dict[str, Any]:
		"""
		后端兜底：保证参数推理节点（auto_infer）至少有一条出边指向目标工具节点，
		否则将其从流程图中移除，避免在前端出现完全没有上下文的孤立节点。
		"""
		if not flow_config:
			return flow_config
		
		nodes = flow_config.get("nodes", []) or []
		edges = flow_config.get("edges", []) or []
		
		# 方便查找节点与边
		node_map: Dict[str, Dict[str, Any]] = {}
		for n in nodes:
			nid = n.get("id")
			if nid:
				node_map[nid] = n
		
		outgoing_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
		for e in edges:
			src = e.get("source")
			if src:
				outgoing_by_source[src].append(e)
		
		new_edges = list(edges)
		nodes_to_keep: List[Dict[str, Any]] = []
		
		for n in nodes:
			nid = n.get("id")
			if not nid:
				continue
			
			# 判断是否是 auto_infer 节点
			raw_type = (n.get("type") or "").lower()
			data_node_type = (n.get("data", {}).get("nodeType") or "").lower()
			is_auto_infer = ("auto_infer" in raw_type) or ("auto_infer" in data_node_type)
			
			if not is_auto_infer:
				nodes_to_keep.append(n)
				continue
			
			# 已经有出边则认为不是孤立的（至少连接到别的节点）
			has_outgoing = nid in outgoing_by_source and len(outgoing_by_source[nid]) > 0
			
			if not has_outgoing:
				# 尝试从 config 中读取目标工具节点 ID，并补一条出边
				config = n.get("data", {}).get("config", {}) or {}
				target_id = (
					config.get("target_tool_node_id")
					or config.get("targetNodeId")
					or config.get("target_tool_id")
				)
				
				if target_id and target_id in node_map:
					edge_id = f"edge_{nid}_{target_id}"
					new_edge = {
						"id": edge_id,
						"source": nid,
						"target": target_id,
						"type": "default",
					}
					new_edges.append(new_edge)
					outgoing_by_source[nid].append(new_edge)
					has_outgoing = True
					logger.info(
						f"规划节点 {self.id} 为参数推理节点 {nid} 自动补充出边 -> {target_id}，避免孤立"
					)
			
			# 如果最终仍然没有任何出边，则认为是“无法正确挂载的孤儿节点”，直接丢弃
			if has_outgoing:
				nodes_to_keep.append(n)
			else:
				logger.warning(
					f"规划节点 {self.id} 检测到孤立参数推理节点 {nid}，且无法确定目标工具节点，已从流程图中移除"
				)
		
		flow_config["nodes"] = nodes_to_keep
		flow_config["edges"] = new_edges
		return flow_config

	def _namespace_flow_nodes_for_retry(
		self,
		flow_config: Dict[str, Any],
		retry_index: int
	) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
		"""
		为重新规划出来的节点生成独立的 ID 命名空间：
		- 每个节点 ID 加上前缀: {planner_id}_retry_{retry_index}_原ID
		- 同时修正 edges 中的 source/target
		- 修正节点 config 中引用其它节点 ID 的字段（如 target_tool_node_id）
		
		这样新路线上的节点与老路线完全独立，不会复用之前的 node_id。
		"""
		nodes = flow_config.get("nodes", []) or []
		edges = flow_config.get("edges", []) or []

		id_map: Dict[str, str] = {}
		for n in nodes:
			old_id = n.get("id")
			if not old_id:
				continue
			new_id = f"{self.id}_retry_{retry_index}_{old_id}"
			id_map[old_id] = new_id

		# 重写节点 ID 以及 config 中的目标节点引用
		new_nodes: List[Dict[str, Any]] = []
		for n in nodes:
			old_id = n.get("id")
			if not old_id:
				continue
			n_copy = json.loads(json.dumps(n))  # 深拷贝以避免修改原配置
			n_copy["id"] = id_map.get(old_id, old_id)

			# 修正 data.config 中可能引用其它节点 ID 的字段
			data = n_copy.get("data") or {}
			config = data.get("config") or {}
			changed = False
			for key in ("target_tool_node_id", "targetNodeId", "target_tool_id"):
				ref_id = config.get(key)
				if isinstance(ref_id, str) and ref_id in id_map:
					config[key] = id_map[ref_id]
					changed = True

			# 重试分支：为节点 label 添加“重试”后缀，方便前端区分不同线路
			if retry_index > 0:
				label = data.get("label") or data.get("nodeType") or n_copy.get("type") or old_id
				retry_suffix = f"重试{retry_index}" if retry_index > 1 else "重试1"
				data["label"] = f"{label} ({retry_suffix})"
				changed = True

			if changed:
				data["config"] = config
				n_copy["data"] = data

			new_nodes.append(n_copy)

		# 重写边的 source/target，仅保留“完全在本子图内部”的边
		new_edges: List[Dict[str, Any]] = []
		for e in edges:
			e_copy = dict(e)
			src = e_copy.get("source")
			tgt = e_copy.get("target")
			# 只保留 source 和 target 都属于当前重试子图节点的边，丢弃指向老节点的边
			if src not in id_map or tgt not in id_map:
				continue
			e_copy["source"] = id_map[src]
			e_copy["target"] = id_map[tgt]
			# 为避免与旧路线的边 ID 冲突，重试子流程的每条边都使用基于新 source/target 的唯一 ID
			e_copy["id"] = f"edge_{e_copy.get('source')}_{e_copy.get('target')}"
			new_edges.append(e_copy)

		# 兜底：如果子图内部仍然有“断链”，按节点顺序补一条链式边，保证重试子图连成一条路
		if new_nodes:
			existing_pairs = {(e["source"], e["target"]) for e in new_edges}
			ordered_ids = [n["id"] for n in new_nodes]
			for i in range(len(ordered_ids) - 1):
				src_id = ordered_ids[i]
				tgt_id = ordered_ids[i + 1]
				if (src_id, tgt_id) not in existing_pairs:
					edge_id = f"edge_{src_id}_{tgt_id}"
					new_edges.append({
						"id": edge_id,
						"source": src_id,
						"target": tgt_id,
						"type": "default",
					})
					existing_pairs.add((src_id, tgt_id))

		return new_nodes, new_edges
	
	async def _generate_flow_config(self, task: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		"""使用 LLM 生成流程图配置"""
		try:
			# 获取可用工具列表
			available_tools = await self._get_available_tools()
			
			# 准备上下文信息
			context_info = self._format_context_info(context)
			
			# 构建提示词
			system_prompt = self.config.get('system_prompt') or PLANNER_SYSTEM_PROMPT
			user_prompt_template = self.config.get('user_prompt') or PLANNER_USER_PROMPT_TEMPLATE
			user_prompt = user_prompt_template.format(
				task=task,
				context=context_info,
				error_context="",  # 首次规划时没有错误信息
				available_tools=available_tools,
				planner_id=self.id,
				retry_index=0,
			)
			
			# 调用 LLM
			llm_helper = get_llm_helper()
			messages = [
				{"role": "system", "content": system_prompt},
				{"role": "user", "content": user_prompt}
			]
			
			response = await llm_helper.call(messages, max_tokens=4000)
			
			# 解析 JSON
			flow_config = self._parse_flow_config(response)
			
			if flow_config:
				# 先为参数推理节点兜底补边 / 过滤孤立 auto_infer 节点
				flow_config = self._ensure_auto_infer_edges(flow_config)
				self._generated_flow_config = flow_config
				logger.info(
					f"规划节点 {self.id} 成功生成流程图配置，包含 {len(flow_config.get('nodes', []))} 个节点"
				)
			
			return flow_config
		except Exception as e:
			logger.error(f"规划节点 {self.id} 生成流程图配置失败: {str(e)}")
			return None
	
	def _parse_flow_config(self, text: str) -> Optional[Dict[str, Any]]:
		"""从 LLM 响应中解析流程图配置"""
		if not text:
			return None
		
		try:
			# 尝试提取 JSON（可能在代码块中）
			clean = text.strip()
			
			# 如果包含 ```json 或 ```，提取其中的内容
			if "```json" in clean:
				start = clean.find("```json") + 7
				end = clean.find("```", start)
				if end > start:
					clean = clean[start:end].strip()
			elif "```" in clean:
				start = clean.find("```") + 3
				end = clean.find("```", start)
				if end > start:
					clean = clean[start:end].strip()
			
			# 解析 JSON
			config = json.loads(clean)
			
			# 验证配置结构
			if not isinstance(config, dict):
				logger.error("流程图配置不是字典格式")
				return None
			
			if 'nodes' not in config:
				logger.error("流程图配置缺少 nodes 字段")
				return None
			
			# 过滤掉 start 和 end 节点
			nodes = config.get('nodes', [])
			filtered_nodes = []
			for node in nodes:
				node_data = node.get('data', {})
				node_type = node.get('type', '')
				# 跳过开始和结束节点
				if (node_data.get('isStartNode') or node_type == 'start' or 
				    node_data.get('isEndNode') or node_type == 'end' or
				    node.get('id') == 'start_node' or node.get('id') == 'end_node'):
					continue
				filtered_nodes.append(node)
			
			config['nodes'] = filtered_nodes
			
			# 过滤掉连接到 start 或 end 节点的边
			edges = config.get('edges', [])
			filtered_edges = []
			start_end_ids = {'start_node', 'end_node'}
			for edge in edges:
				source = edge.get('source', '')
				target = edge.get('target', '')
				# 跳过连接到 start 或 end 节点的边
				if source in start_end_ids or target in start_end_ids:
					continue
				filtered_edges.append(edge)
			
			config['edges'] = filtered_edges
			
			# 验证并修复节点连接，确保所有节点串行连接
			config = self._ensure_serial_connection(config)
			
			# 确保有 metadata
			if 'metadata' not in config:
				config['metadata'] = {
					"name": "自动生成的流程图",
					"description": "",
					"version": "1.0.0"
				}
			
			return config
		except json.JSONDecodeError as e:
			logger.error(f"解析流程图配置 JSON 失败: {str(e)}")
			logger.debug(f"原始响应: {text[:500]}")
			return None
		except Exception as e:
			logger.error(f"解析流程图配置失败: {str(e)}")
			return None
	
	def _generate_edges_from_nodes(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		"""根据节点列表自动生成边连接（不包含 start 和 end 节点）"""
		edges = []
		
		if len(nodes) < 2:
			return edges
		
		# 节点依次连接
		for i in range(len(nodes) - 1):
			edges.append({
				"id": f"edge_{nodes[i].get('id')}_{nodes[i+1].get('id')}",
				"source": nodes[i].get('id'),
				"target": nodes[i+1].get('id'),
				"type": "default"
			})
		
		return edges
	
	def _ensure_serial_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
		"""确保所有节点串行连接，移除游离节点和分支"""
		nodes = config.get('nodes', [])
		edges = config.get('edges', [])
		
		if not nodes:
			config['edges'] = []
			return config
		
		if len(nodes) == 1:
			# 只有一个节点，不需要边
			config['edges'] = []
			return config
		
		# 构建节点ID到节点的映射
		node_map = {node.get('id'): node for node in nodes}
		node_ids = list(node_map.keys())
		
		# 构建入度和出度统计
		in_degree = {node_id: 0 for node_id in node_ids}
		out_degree = {node_id: 0 for node_id in node_ids}
		edge_map = {}  # source -> [targets]
		
		for edge in edges:
			source = edge.get('source')
			target = edge.get('target')
			if source in node_map and target in node_map:
				if source not in edge_map:
					edge_map[source] = []
				edge_map[source].append(target)
				out_degree[source] = out_degree.get(source, 0) + 1
				in_degree[target] = in_degree.get(target, 0) + 1
		
		# 检查是否有分支或游离节点
		has_branch = False
		orphan_nodes = []
		
		# 检查是否有多个出边（分支）
		for node_id, out_count in out_degree.items():
			if out_count > 1:
				has_branch = True
				logger.warning(f"节点 {node_id} 有 {out_count} 个出边，存在分支")
		
		# 检查是否有多个入边（合并）
		for node_id, in_count in in_degree.items():
			if in_count > 1:
				has_branch = True
				logger.warning(f"节点 {node_id} 有 {in_count} 个入边，存在合并")
		
		# 检查游离节点（没有入边也没有出边）
		for node_id in node_ids:
			in_count = in_degree.get(node_id, 0)
			out_count = out_degree.get(node_id, 0)
			# 第一个节点应该没有入边但有出边，最后一个节点应该没有出边但有入边
			# 中间节点应该都有入边和出边
			# 如果节点既没有入边也没有出边，就是游离节点
			if in_count == 0 and out_count == 0:
				orphan_nodes.append(node_id)
				logger.warning(f"节点 {node_id} 是游离节点（没有连接）")
		
		# 如果有分支或游离节点，重新生成串行连接
		if has_branch or orphan_nodes:
			logger.info(f"检测到非串行连接，重新生成串行边。分支: {has_branch}, 游离节点: {orphan_nodes}")
			
			# 移除游离节点
			if orphan_nodes:
				nodes = [node for node in nodes if node.get('id') not in orphan_nodes]
				node_ids = [node.get('id') for node in nodes]
				logger.info(f"移除了 {len(orphan_nodes)} 个游离节点，剩余 {len(nodes)} 个节点")
			
			# 重新生成串行边
			new_edges = []
			for i in range(len(nodes) - 1):
				source_id = nodes[i].get('id')
				target_id = nodes[i+1].get('id')
				new_edges.append({
					"id": f"edge_{source_id}_{target_id}",
					"source": source_id,
					"target": target_id,
					"type": "default"
				})
			
			config['nodes'] = nodes
			config['edges'] = new_edges
			logger.info(f"重新生成了 {len(new_edges)} 条串行边")
		else:
			# 验证是否所有节点都在路径上
			# 找到起始节点（入度为0）
			start_nodes = [node_id for node_id, in_count in in_degree.items() if in_count == 0]
			if len(start_nodes) != 1:
				logger.warning(f"起始节点数量不正确: {len(start_nodes)}，期望1个")
				# 重新生成串行边
				new_edges = []
				for i in range(len(nodes) - 1):
					source_id = nodes[i].get('id')
					target_id = nodes[i+1].get('id')
					new_edges.append({
						"id": f"edge_{source_id}_{target_id}",
						"source": source_id,
						"target": target_id,
						"type": "default"
					})
				config['edges'] = new_edges
			else:
				# 验证路径完整性：从起始节点开始，检查是否能到达所有节点
				visited = set()
				start_node_id = start_nodes[0]
				current = start_node_id
				
				while current and current not in visited:
					visited.add(current)
					# 获取下一个节点
					next_nodes = edge_map.get(current, [])
					if len(next_nodes) > 1:
						# 有分支，只取第一个
						logger.warning(f"节点 {current} 有多个后继，只保留第一个")
						next_nodes = [next_nodes[0]]
					current = next_nodes[0] if next_nodes else None
				
				# 检查是否有未访问的节点
				unvisited = set(node_ids) - visited
				if unvisited:
					logger.warning(f"有 {len(unvisited)} 个节点不在路径上: {unvisited}")
					# 重新生成串行边
					new_edges = []
					for i in range(len(nodes) - 1):
						source_id = nodes[i].get('id')
						target_id = nodes[i+1].get('id')
						new_edges.append({
							"id": f"edge_{source_id}_{target_id}",
							"source": source_id,
							"target": target_id,
							"type": "default"
						})
					config['edges'] = new_edges
		
		return config
	
	async def _get_available_tools(self) -> str:
		"""获取系统内所有可用工具列表（包括内置工具、MCP工具、临时工具）
		
		规则：
		- ToolManager 先按评分从高到低排序
		- 这里再按 (type, category) 分组，**每组只保留评分最高的一个工具**
		  也就是说：多个功能相近（同一类型+同一类别）的工具时，只暴露评分最高的那个给规划 LLM，避免低分工具被选择。
		"""
		try:
			from main import agent_manager
			if not agent_manager or not agent_manager.tool_manager:
				logger.warning("AgentManager 或 ToolManager 未初始化")
				return "暂无可用工具"
			
			tool_manager = agent_manager.tool_manager
			# 获取所有可用工具（包括内置、MCP、临时工具），已按评分从高到低排序
			all_tools = tool_manager.get_available_tools()
			
			if not all_tools:
				logger.warning("未获取到任何工具")
				return "暂无可用工具"
			
			# 按 (type, category) 分组，只保留每组评分最高的一个
			grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
			for t in all_tools:
				t_type = t.get("type", "unknown")
				t_category = t.get("category", "utility")
				grouped[(t_type, t_category)].append(t)
			
			filtered_tools: List[Dict[str, Any]] = []
			for (t_type, t_category), group in grouped.items():
				# group 已经是整体排序之后的切片，但为稳妥再局部排序一次
				group_sorted = sorted(group, key=lambda x: x.get("score", 1.0), reverse=True)
				best_tool = group_sorted[0]
				filtered_tools.append(best_tool)
				if len(group_sorted) > 1:
					removed_names = [g.get("name", "unknown") for g in group_sorted[1:]]
					logger.info(
						f"规划节点按 (type={t_type}, category={t_category}) 分组，只保留评分最高工具 "
						f"{best_tool.get('name')} (score={best_tool.get('score')})，"
						f"过滤掉同组其它工具: {removed_names}"
					)
			
			logger.info(
				f"规划节点获取到 {len(all_tools)} 个原始工具，按功能分组后保留 {len(filtered_tools)} 个代表工具"
			)
			
			# 按类型分组工具（基于过滤后的列表）
			tools_by_type: Dict[str, List[Dict[str, Any]]] = {}
			for tool_info in filtered_tools:
				tool_type = tool_info.get('type', 'unknown')
				if tool_type not in tools_by_type:
					tools_by_type[tool_type] = []
				tools_by_type[tool_type].append(tool_info)
			
			# 格式化工具信息
			tool_sections: List[str] = []
			
			# 内置工具（每个功能类别只保留一个代表工具，按评分从高到低展示）
			if 'builtin' in tools_by_type:
				tool_sections.append("## 内置工具（每个功能类别只保留评分最高的一个，按评分从高到低排序）：")
				for tool_info in sorted(tools_by_type['builtin'], key=lambda x: x.get('score', 1.0), reverse=True):
					tool_name = tool_info.get('name', 'unknown')
					tool_desc = tool_info.get('description', '无描述')
					params = tool_info.get('parameters', {})
					params_desc = self._format_parameters_schema(params)
					score = tool_info.get('score', 1.0)
					category = tool_info.get('category', 'utility')
					tool_sections.append(f"- **{tool_name}** (类别: {category}, 评分: {score:.2f}): {tool_desc}")
					if params_desc:
						tool_sections.append(f"  参数: {params_desc}")
			
			# MCP工具（每个服务器+类别只保留评分最高的一个，在每个服务器内按评分从高到低展示）
			mcp_tools = [t for t in filtered_tools if t.get('type') == 'mcp']
			if mcp_tools:
				tool_sections.append("\n## MCP工具（按评分从高到低排序，优先选择高评分工具）：")
				# 按服务器分组
				tools_by_server = {}
				for tool_info in mcp_tools:
					# 从工具名称中提取服务器名（格式：mcp_{server}_{tool_name}）
					tool_name = tool_info.get('name', '')
					if tool_name.startswith('mcp_'):
						parts = tool_name.split('_', 2)
						if len(parts) >= 3:
							server_name = parts[1]
							if server_name not in tools_by_server:
								tools_by_server[server_name] = []
							tools_by_server[server_name].append(tool_info)
				
				for server_name, server_tools in tools_by_server.items():
					# 每个服务器内按评分排序
					server_tools_sorted = sorted(server_tools, key=lambda t: t.get('score', 1.0), reverse=True)
					tool_sections.append(f"\n### 服务器 {server_name}：")
					for tool_info in server_tools_sorted:
						tool_name = tool_info.get('name', 'unknown')
						tool_desc = tool_info.get('description', '无描述')
						params = tool_info.get('parameters', {})
						params_desc = self._format_parameters_schema(params)
						score = tool_info.get('score', 1.0)
						# 提取实际工具名（去掉 mcp_{server}_ 前缀）
						actual_tool_name = tool_name.split('_', 2)[-1] if '_' in tool_name else tool_name
						tool_sections.append(f"- **{actual_tool_name}** (工具名: {tool_name}, 评分: {score:.2f}): {tool_desc}")
						if params_desc:
							tool_sections.append(f"  参数: {params_desc}")
						tool_sections.append(f"  服务器: {server_name}")
			
			# 临时工具（同样按评分从高到低排序）
			if 'temporary' in tools_by_type:
				tool_sections.append("\n## 临时工具（按评分从高到低排序，优先选择高评分工具）：")
				sorted_temp_tools = sorted(tools_by_type['temporary'], key=lambda t: t.get('score', 1.0), reverse=True)
				for tool_info in sorted_temp_tools:
					tool_name = tool_info.get('name', 'unknown')
					tool_desc = tool_info.get('description', '无描述')
					params = tool_info.get('parameters', {})
					params_desc = self._format_parameters_schema(params)
					score = tool_info.get('score', 1.0)
					# 提取实际工具名（去掉 temp_ 前缀）
					actual_tool_name = tool_name.replace('temp_', '') if tool_name.startswith('temp_') else tool_name
					tool_sections.append(f"- **{actual_tool_name}** (工具名: {tool_name}, 评分: {score:.2f}): {tool_desc}")
					if params_desc:
						tool_sections.append(f"  参数: {params_desc}")
			
			result = "\n".join(tool_sections) if tool_sections else "暂无可用工具"
			logger.info(f"规划节点工具列表格式化完成，长度: {len(result)} 字符")
			return result
			
		except Exception as e:
			logger.error(f"获取可用工具列表失败: {str(e)}", exc_info=True)
			return f"获取工具列表失败: {str(e)}"
	
	def _format_parameters_schema(self, params_schema: Dict[str, Any]) -> str:
		"""格式化参数 schema 为易读的字符串"""
		if not params_schema or not isinstance(params_schema, dict):
			return ""
		
		try:
			properties = params_schema.get('properties', {})
			required = params_schema.get('required', [])
			
			if not properties:
				return ""
			
			param_descs = []
			for param_name, param_info in properties.items():
				param_type = param_info.get('type', 'string')
				param_desc = param_info.get('description', '')
				is_required = param_name in required
				required_mark = "(必填)" if is_required else "(可选)"
				
				if param_type == 'object':
					param_descs.append(f"{param_name}: 对象 {required_mark}")
				elif param_type == 'array':
					items = param_info.get('items', {})
					item_type = items.get('type', 'string')
					param_descs.append(f"{param_name}: {item_type}数组 {required_mark}")
				else:
					param_descs.append(f"{param_name}: {param_type} {required_mark}")
				if param_desc:
					param_descs[-1] += f" - {param_desc}"
			
			return ", ".join(param_descs)
		except Exception as e:
			logger.warning(f"格式化参数 schema 失败: {str(e)}")
			return ""
	
	def _format_context_info(self, context: Dict[str, Any]) -> str:
		"""格式化上下文信息"""
		flow_state = context.get('flow_state', {})
		if not flow_state:
			return "无上下文信息"
		
		info_parts = []
		if 'last_output' in flow_state:
			info_parts.append(f"上一节点输出: {str(flow_state['last_output'])[:200]}")
		if 'saved_files' in flow_state:
			info_parts.append(f"已保存文件: {', '.join(flow_state['saved_files'])}")
		
		return "\n".join(info_parts) if info_parts else "无上下文信息"
	
	async def _execute_generated_flow(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		flow_config: Dict[str, Any],
		agent_name: str = None
	) -> AgentMessage:
		"""执行生成的流程图（同步）"""
		try:
			# 创建 FlowEngine
			engine = FlowEngine()
			engine.build_from_config(flow_config)
			
			# 执行流程图
			results = await engine.run(
				user_id=user_id,
				message=message,
				context=context,
				start_node_id=None,  # 使用默认起始节点
				agent_name=agent_name
			)
			
			# 合并所有结果
			content_parts = []
			for result in results:
				if result.content:
					content_parts.append(result.content)
			
			final_content = "\n\n".join(content_parts) if content_parts else "流程图执行完成"
			
			return self._create_agent_message(
				final_content,
				agent_name,
				metadata={
					'planner_node_id': self.id,
					'generated_flow_config': flow_config,
					'execution_results_count': len(results)
				}
			)
		except Exception as e:
			logger.error(f"规划节点 {self.id} 执行生成的流程图失败: {str(e)}")
			error_msg = f"执行生成的流程图失败: {str(e)}"
			return self._create_agent_message(error_msg, agent_name, metadata={'error': str(e)})
	
	async def _execute_generated_nodes_stream(
		self,
		user_id: str,
		message: str,
		context: Dict[str, Any],
		generated_nodes: List[Dict[str, Any]],
		generated_edges: List[Dict[str, Any]],
		planner_next_node_id: Optional[str] = None,
		agent_name: str = None,
		retry_index: int = 0
	) -> AsyncGenerator[StreamChunk, None]:
		"""执行生成的节点（流式）"""
		if not generated_nodes:
			logger.warning(f"规划节点 {self.id} 没有生成任何节点")
			return
		
		try:
			# 创建临时 FlowEngine 来执行生成的节点
			# 注意：这里不添加 start 和 end 节点，直接执行生成的节点
			from ..engine import FlowEngine
			engine = FlowEngine()
			
			# 构建节点图（不自动添加 start/end）
			engine._node_map.clear()
			engine._adj.clear()
			engine._in_degree.clear()
			
			# 实例化生成的节点
			for node_cfg in generated_nodes:
				try:
					node = BaseFlowNode.from_config(node_cfg)
					engine._node_map[node.id] = node
					engine._adj[node.id] = []
					engine._in_degree[node.id] = 0
					logger.info(f"规划节点 {self.id} 实例化生成节点: {node.id} ({node.name})")
				except Exception as e:
					logger.error(f"规划节点 {self.id} 实例化节点失败 {node_cfg.get('id', 'unknown')}: {str(e)}")
					continue
			
			# 构建边连接
			for edge_cfg in generated_edges:
				source_id = edge_cfg.get('source')
				target_id = edge_cfg.get('target')
				if source_id in engine._node_map and target_id in engine._node_map:
					if target_id not in engine._adj[source_id]:
						engine._adj[source_id].append(target_id)
					engine._in_degree[target_id] = engine._in_degree.get(target_id, 0) + 1
					# 更新节点的 connections
					source_node = engine._node_map[source_id]
					if target_id not in source_node.connections:
						source_node.add_connection(target_id)
			
			# 找到最后一个节点（出度为0的节点，即没有后续连接的节点）
			last_node_id = None
			for node_id in engine._node_map.keys():
				# 检查该节点是否有出边（连接到其他生成节点）
				has_outgoing_to_generated = any(
					target_id in engine._node_map 
					for target_id in engine._adj.get(node_id, [])
				)
				if not has_outgoing_to_generated:
					last_node_id = node_id
					break
			
			# 如果没有找到出度为0的节点，使用最后一个节点
			if not last_node_id and engine._node_map:
				# 找到执行顺序中的最后一个节点
				start_nodes = [node_id for node_id, in_deg in engine._in_degree.items() if in_deg == 0]
				if start_nodes:
					current = start_nodes[0]
					while True:
						next_id = engine._node_map[current].get_next_node_id(0)
						if next_id and next_id in engine._node_map:
							current = next_id
						else:
							last_node_id = current
							break
				else:
					last_node_id = list(engine._node_map.keys())[-1]
			
			# 将最后一个生成节点连接到规划节点的原始下一个节点
			# 注意：这里仅用于首轮规划，重新规划时我们不再从新路线连回原来的下一个节点，
			# 以保证新旧两条路线在图结构上完全独立。
			if last_node_id and planner_next_node_id and retry_index == 0:
				last_node = engine._node_map.get(last_node_id)
				if last_node:
					last_node.add_connection(planner_next_node_id)
					logger.info(f"规划节点 {self.id} 将最后一个生成节点 {last_node_id} 连接到规划节点的下一个节点 {planner_next_node_id}")
			
			# 找到起始节点（入度为0的节点）
			start_nodes = [node_id for node_id, in_deg in engine._in_degree.items() if in_deg == 0]
			if not start_nodes:
				# 如果没有入度为0的节点，使用第一个节点
				start_nodes = [list(engine._node_map.keys())[0]] if engine._node_map else []
			
			if not start_nodes:
				logger.warning(f"规划节点 {self.id} 没有找到起始节点")
				return
			
			# 执行生成的节点（从第一个起始节点开始）
			current_node_id = start_nodes[0]
			executed_nodes = set()
			failed_nodes: List[Dict[str, str]] = []  # 收集失败节点信息
			
			while current_node_id and current_node_id not in executed_nodes:
				executed_nodes.add(current_node_id)
				node = engine._node_map.get(current_node_id)
				if not node:
					logger.warning(f"规划节点 {self.id} 节点不存在: {current_node_id}")
					break
				
				# 执行节点（流式）
				node_failed = False
				node_error = None
				node_start_sent = False
				node_complete_sent = False
				node_label = node.config.get('label') if hasattr(node, 'config') else None
				node_metadata = {
					'node_id': node.id,
					'node_type': getattr(getattr(node, 'type', None), 'value', getattr(node, 'type', 'unknown')),
					'node_name': getattr(node, 'name', node.id),
					'node_label': node_label or getattr(node, 'name', node.id)
				}
				node_output_chunks: List[str] = []
				
				def emit_node_start_chunk():
					nonlocal node_start_sent
					if node_start_sent:
						return None
					node_start_sent = True
					return node._create_stream_chunk(
						chunk_type="node_start",
						content=f"🚀 开始执行 {getattr(node, 'name', node.id)} 节点",
						agent_name=agent_name,
						metadata=node_metadata.copy()
					)
				
				def emit_node_complete_chunk(status: str, output: Optional[str] = None, error: Optional[str] = None):
					nonlocal node_complete_sent
					if node_complete_sent:
						return None
					node_complete_sent = True
					metadata = node_metadata.copy()
					metadata['status'] = status
					if output:
						metadata['output'] = output
					if error:
						metadata['error'] = error
					return node._create_stream_chunk(
						chunk_type="node_complete",
						content=f"{'✅' if status == 'completed' else '⚠️'} {getattr(node, 'name', node.id)} 节点执行{ '完成' if status == 'completed' else '结束'}",
						agent_name=agent_name,
						metadata=metadata
					)
				
				try:
					start_chunk = emit_node_start_chunk()
					if start_chunk:
						yield start_chunk
					
					async for chunk in node.execute_stream(user_id, message, context, agent_name):
						if chunk.type == "node_start":
							node_start_sent = True
						if chunk.type == "node_complete":
							node_complete_sent = True
						if chunk.type in ("content", "final_response", "final") and isinstance(chunk.content, str):
							node_output_chunks.append(chunk.content)
						
						# 检查是否是错误事件
						if chunk.type == "node_error":
							node_failed = True
							node_error = chunk.content or chunk.metadata.get('error', '节点执行失败')
							logger.warning(f"规划节点 {self.id} 检测到节点 {current_node_id} 执行失败: {node_error}")
						elif chunk.type == "node_complete" and chunk.metadata:
							# 检查节点完成事件中是否标记为失败
							if chunk.metadata.get('status') == 'failed' or chunk.metadata.get('error'):
								node_failed = True
								node_error = chunk.metadata.get('error', chunk.metadata.get('output', '节点执行失败'))
								logger.warning(f"规划节点 {self.id} 检测到节点 {current_node_id} 执行失败: {node_error}")
						
						# 透传节点的流式输出
						yield chunk
				except Exception as e:
					node_failed = True
					node_error = str(e)
					logger.error(f"规划节点 {self.id} 执行节点 {current_node_id} 失败: {str(e)}")
					yield self._create_stream_chunk(
						chunk_type="content",
						content=f"❌ 节点 {node.name} 执行失败: {str(e)}\n",
						agent_name=agent_name
					)
				
				if not node_failed:
					complete_chunk = emit_node_complete_chunk(
						status="completed",
						output=("".join(node_output_chunks)).strip() if node_output_chunks else None
					)
					if complete_chunk:
						yield complete_chunk
				
				# 如果节点失败，记录错误信息并立即停止流程
				if node_failed:
					failed_nodes.append({
						'node_id': current_node_id,
						'node_name': node.name,
						'error': node_error or '节点执行失败'
					})
					failed_chunk = emit_node_complete_chunk(
						status="failed",
						output=("".join(node_output_chunks)).strip() if node_output_chunks else None,
						error=node_error
					)
					if failed_chunk:
						yield failed_chunk
					
					# 一旦检测到失败，立即停止执行后续节点
					logger.warning(f"规划节点 {self.id} 检测到节点 {current_node_id} 失败，立即停止流程执行")
					current_node_id = None  # 停止执行
					break  # 跳出循环，不再执行后续节点
				
				# 选择下一个节点
				next_node_id = node.get_next_node_id(0)
				# 如果下一个节点是规划节点的原始下一个节点，结束执行（让 FlowEngine 继续执行）
				# 对于重试场景（retry_index > 0），新子流程不再连回原路线，直接在本子流程内终止。
				if retry_index == 0 and next_node_id == planner_next_node_id:
					logger.info(f"规划节点 {self.id} 生成的节点执行完成，将继续执行规划节点的下一个节点 {planner_next_node_id}")
					current_node_id = None
				elif next_node_id and next_node_id in engine._node_map:
					current_node_id = next_node_id
				else:
					# 没有下一个节点，结束
					current_node_id = None
			
			# 首次规划且全程无失败时，将子流程最后一个节点连到全局唯一的结束节点 end_node，
			# 这样所有不同的路线（初始路线 + 各次重试）最终都会在前端汇聚到同一个结束节点。
			if not failed_nodes and last_node_id and retry_index == 0:
				global_end_id = "end_node"
				end_edge = {
					'id': f"edge_{last_node_id}_{global_end_id}",
					'source': last_node_id,
					'target': global_end_id,
					'type': 'default'
				}
				logger.info(f"规划节点 {self.id} 首次规划成功，连接 {last_node_id} -> {global_end_id} 作为统一结束节点")
				yield self._create_stream_chunk(
					chunk_type="flow_nodes_extend",
					content="",
					agent_name=agent_name,
					metadata={
						'planner_node_id': self.id,
						'planner_next_node_id': planner_next_node_id,
						'remove_planner_edge': False,
						'nodes': [],
						'edges': [end_edge],
						'flow_name': '连接到全局结束节点',
						'node_count': 0,
						'is_virtual_end': False
					}
				)
			
			# 如果检测到失败节点，立即停止流程，并在规划节点下新增“重新规划”子节点挂载新子流程
			if failed_nodes:
				logger.warning(f"规划节点 {self.id} 检测到 {len(failed_nodes)} 个失败节点，停止当前流程，重新规划新线路")

				# 计算本次重试的虚拟规划节点ID和标签（用于前端和左侧聊天节点）
				next_retry_index = retry_index + 1
				retry_planner_node_id = f"{self.id}_retry_{next_retry_index}"
				retry_label = "重新规划" if next_retry_index == 1 else f"重新规划 {next_retry_index} 次"

				# 为“重新规划”创建一个单独的节点（左侧聊天中的新节点）
				yield self._create_stream_chunk(
					chunk_type="node_start",
					content=f"🔁 {retry_label}：准备重新规划新的子流程...\n",
					agent_name=agent_name,
					metadata={
						"node_id": retry_planner_node_id,
						"node_type": "planner_retry",
						"node_name": self.name,
						"node_label": retry_label,
					},
				)

				# 将失败说明也归入这个“重新规划”节点
				yield self._create_stream_chunk(
					chunk_type="content",
					content=f"\n⚠️ 检测到节点执行失败，已停止当前流程，正在重新规划新线路...\n\n",
					agent_name=agent_name,
					metadata={
						"node_id": retry_planner_node_id,
						"node_type": "planner_retry",
						"node_name": self.name,
						"node_label": retry_label,
					},
				)
				
				# 收集错误信息
				error_summary = self._format_failed_nodes_summary(failed_nodes)
				
				# 重新生成流程图配置（包含错误信息）
				retry_flow_config = await self._generate_flow_config_with_errors(
					message, context, error_summary, next_retry_index
				)
				
				if retry_flow_config:
					flow_name = retry_flow_config.get('metadata', {}).get('name', '重新规划的流程图')
					retry_nodes = retry_flow_config.get('nodes', [])
					node_count = len(retry_nodes)

					# 将“重新生成新线路”的说明文本也归入重新规划节点
					yield self._create_stream_chunk(
						chunk_type="content",
						content=f"✅ 已重新生成 {node_count} 个节点的新线路：{flow_name}\n\n",
						agent_name=agent_name,
						metadata={
							"node_id": retry_planner_node_id,
							"node_type": "planner_retry",
							"node_name": self.name,
							"node_label": retry_label,
						},
					)

					# 找到最后一个生成节点ID（用于连接虚拟结束节点）
					last_retry_node_id = self._find_last_node_id(retry_nodes, retry_flow_config.get('edges', []))
					
					# 生成“重新规划节点 + 新子流程”展示结构
					display_retry_nodes, display_retry_edges, retry_planner_node_id = self._build_retry_flow_display_nodes(
						self.id,
						next_retry_index,
						retry_nodes,
						retry_flow_config.get('edges', []),
						last_retry_node_id
					)
					
					yield self._create_stream_chunk(
						chunk_type="flow_nodes_extend",
						content="",
						agent_name=agent_name,
						metadata={
							'planner_node_id': self.id,                 # 原始规划节点ID（用于从原规划节点连到 retry 节点）
							'planner_next_node_id': planner_next_node_id,
							'remove_planner_edge': False,               # 不移除原有连接，保留失败路径
							'replace_existing_nodes': False,           # 追加模式，保留旧节点
							'nodes': display_retry_nodes,
							'edges': display_retry_edges,
							'flow_name': flow_name,
							'node_count': len(display_retry_nodes),
							'is_retry': True,                          # 标记为重新规划
							'root_planner_node_id': self.id,
							'retry_planner_node_id': retry_planner_node_id,
							'retry_index': next_retry_index
						}
					)

					# 标记“重新规划”节点完成，让左侧聊天中的该节点状态为已完成
					retry_output_summary = f"{retry_label}：已重新生成 {node_count} 个节点的新线路：{flow_name}"
					yield self._create_stream_chunk(
						chunk_type="node_complete",
						content=f"✅ {retry_label} 完成，共生成 {node_count} 个节点的新子流程",
						agent_name=agent_name,
						metadata={
							"node_id": retry_planner_node_id,
							"node_type": "planner_retry",
							"node_name": self.name,
							"node_label": retry_label,
							"status": "completed",
							"output": retry_output_summary,
						},
					)
					
					# 执行重新规划的节点（递归调用，支持多次重试）
					async for chunk in self._execute_generated_nodes_stream(
						user_id, message, context, retry_nodes, 
						retry_flow_config.get('edges', []), planner_next_node_id, agent_name, next_retry_index
					):
						yield chunk
				else:
					yield self._create_stream_chunk(
						chunk_type="content",
						content=f"❌ 重新规划失败，无法生成新的流程图配置\n",
						agent_name=agent_name
					)
					
		except Exception as e:
			logger.error(f"规划节点 {self.id} 流式执行生成的节点失败: {str(e)}")
			error_msg = f"执行生成的节点失败: {str(e)}"
			yield self._create_stream_chunk(
				chunk_type="content",
				content=f"❌ {error_msg}\n",
				agent_name=agent_name,
				is_end=True
			)

