"""规划节点实现：根据任务自动生成流程图并执行"""
from typing import Dict, Any, AsyncGenerator, Optional, List
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
2. 所有节点必须通过 edges 连接
3. 如果使用 tool 节点，建议在前面添加 auto_infer 节点来自动生成参数
4. 节点 ID 必须唯一
5. 只输出 JSON，不要包含其他文字说明"""

PLANNER_USER_PROMPT_TEMPLATE = """请为以下任务生成一个流程图配置：

任务：{task}

上下文信息：
{context}

可用工具列表：
{available_tools}

请生成一个完整的流程图配置 JSON，确保：
1. **不要包含 start 和 end 节点**（这些节点会在执行时自动添加）
2. 所有节点通过 edges 正确连接
3. 节点配置完整（特别是 tool 节点的 tool_name, tool_type, server）
4. 如果使用工具，建议添加 auto_infer 节点
5. 流程图逻辑清晰，能够完成任务

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
			yield self._create_stream_chunk(
				chunk_type="flow_nodes_extend",
				content="",
				agent_name=agent_name,
				metadata={
					'planner_node_id': self.id,
					'planner_next_node_id': planner_next_node_id,  # 规划节点的原始下一个节点
					'remove_planner_edge': True,  # 标记需要移除规划节点到原始下一个节点的边
					'nodes': generated_nodes,
					'edges': flow_config.get('edges', []),
					'flow_name': flow_name,
					'node_count': node_count
				}
			)
			
			# 2. 执行生成的节点（流式）
			async for chunk in self._execute_generated_nodes_stream(user_id, message, context, generated_nodes, flow_config.get('edges', []), planner_next_node_id, agent_name):
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
				available_tools=available_tools
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
				self._generated_flow_config = flow_config
				logger.info(f"规划节点 {self.id} 成功生成流程图配置，包含 {len(flow_config.get('nodes', []))} 个节点")
			
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
			
			# 确保有 edges（如果没有则生成）
			if not config['edges']:
				config['edges'] = self._generate_edges_from_nodes(config.get('nodes', []))
			
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
	
	async def _get_available_tools(self) -> str:
		"""获取可用工具列表"""
		try:
			from main import agent_manager
			if not agent_manager or not agent_manager.tool_manager:
				return "暂无可用工具"
			
			tool_manager = agent_manager.tool_manager
			tools = tool_manager.get_all_tools()
			
			if not tools:
				return "暂无可用工具"
			
			tool_list = []
			for tool_name, tool_obj in tools.items():
				tool_desc = tool_obj.description if hasattr(tool_obj, 'description') else tool_name
				tool_list.append(f"- {tool_name}: {tool_desc}")
			
			return "\n".join(tool_list) if tool_list else "暂无可用工具"
		except Exception as e:
			logger.warning(f"获取可用工具列表失败: {str(e)}")
			return "获取工具列表失败"
	
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
		agent_name: str = None
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
			if last_node_id and planner_next_node_id:
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
			
			while current_node_id and current_node_id not in executed_nodes:
				executed_nodes.add(current_node_id)
				node = engine._node_map.get(current_node_id)
				if not node:
					logger.warning(f"规划节点 {self.id} 节点不存在: {current_node_id}")
					break
				
				# 执行节点（流式）
				try:
					async for chunk in node.execute_stream(user_id, message, context, agent_name):
						# 透传节点的流式输出
						yield chunk
				except Exception as e:
					logger.error(f"规划节点 {self.id} 执行节点 {current_node_id} 失败: {str(e)}")
					yield self._create_stream_chunk(
						chunk_type="content",
						content=f"❌ 节点 {node.name} 执行失败: {str(e)}\n",
						agent_name=agent_name
					)
				
				# 选择下一个节点
				next_node_id = node.get_next_node_id(0)
				# 如果下一个节点是规划节点的原始下一个节点，结束执行（让 FlowEngine 继续执行）
				if next_node_id == planner_next_node_id:
					logger.info(f"规划节点 {self.id} 生成的节点执行完成，将继续执行规划节点的下一个节点 {planner_next_node_id}")
					current_node_id = None
				elif next_node_id and next_node_id in engine._node_map:
					current_node_id = next_node_id
				else:
					# 没有下一个节点，结束
					current_node_id = None
					
		except Exception as e:
			logger.error(f"规划节点 {self.id} 流式执行生成的节点失败: {str(e)}")
			error_msg = f"执行生成的节点失败: {str(e)}"
			yield self._create_stream_chunk(
				chunk_type="content",
				content=f"❌ {error_msg}\n",
				agent_name=agent_name,
				is_end=True
			)

