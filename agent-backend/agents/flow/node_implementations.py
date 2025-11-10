"""
节点实现：提供常用的节点实现类

这些实现类继承自 BaseFlowNode，提供具体的执行逻辑。
"""
from typing import Dict, Any, AsyncGenerator, Optional
from .base_node import BaseFlowNode, NodeCategory
from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
import json
import uuid

logger = get_logger("flow_node_implementations")


class LLMNode(BaseFlowNode):
	"""LLM 节点实现：调用 LLM 生成响应"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行 LLM 调用（同步）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		system_prompt = self._render_template_value(self.config.get('system_prompt', ''), inputs)
		user_prompt = self._render_template_value(self.config.get('user_prompt', message), inputs)
		save_as = self.config.get('save_as', 'last_output')
		
		# 构建消息
		messages = []
		if system_prompt:
			messages.append({"role": "system", "content": system_prompt})
		messages.append({"role": "user", "content": user_prompt})
		
		# 调用 LLM
		try:
			llm_helper = get_llm_helper()
			response = await llm_helper.call_llm(messages)
			
			# 保存输出
			self.save_output(context, response)
			
			# 尝试解析 JSON 并合并到 flow_state
			self._merge_json_into_flow_state(response, context.get('flow_state', {}))
			
			return self._create_agent_message(response, agent_name)
		except Exception as e:
			logger.error(f"LLM节点执行失败: {str(e)}")
			error_msg = f"LLM调用失败: {str(e)}"
			return self._create_agent_message(error_msg, agent_name, metadata={'error': str(e)})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""执行 LLM 调用（流式）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		system_prompt = self._render_template_value(self.config.get('system_prompt', ''), inputs)
		user_prompt = self._render_template_value(self.config.get('user_prompt', message), inputs)
		save_as = self.config.get('save_as', 'last_output')
		
		# 构建消息
		messages = []
		if system_prompt:
			messages.append({"role": "system", "content": system_prompt})
		messages.append({"role": "user", "content": user_prompt})
		
		# 流式调用 LLM
		try:
			llm_helper = get_llm_helper()
			accumulated = ""
			
			async for chunk in llm_helper.call_stream(messages):
				if not chunk:
					continue
				
				accumulated += chunk
				
				# 流式输出内容
				yield self._create_stream_chunk(
					chunk_type="content",
					content=chunk,
					agent_name=agent_name
				)
				
				# 增量保存
				self.save_output(context, accumulated)
			
			# 尝试解析 JSON 并合并到 flow_state
			self._merge_json_into_flow_state(accumulated, context.get('flow_state', {}))
			
		except Exception as e:
			logger.error(f"LLM节点流式执行失败: {str(e)}")
			yield self._create_stream_chunk(
				chunk_type="error",
				content=f"LLM调用失败: {str(e)}",
				agent_name=agent_name,
				metadata={'error': str(e)}
			)
	
	def _merge_json_into_flow_state(self, text: str, flow_state: Dict[str, Any]):
		"""尝试从 LLM 文本中提取 JSON 并合并到 flow_state 中"""
		if not text:
			return
		try:
			import re
			clean = text
			# 去除<think>段落
			clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE|re.DOTALL)
			# 提取代码块中的 JSON 或直接解析
			m = re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", clean)
			if m:
				candidate = m.group(1)
			else:
				candidate = clean.strip()
			parsed = json.loads(candidate)
			if isinstance(parsed, dict):
				for k, v in parsed.items():
					flow_state[str(k)] = v
		except Exception:
			# 忽略解析失败
			pass


class ToolNode(BaseFlowNode):
	"""工具节点实现：调用 MCP 工具"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行工具调用（同步）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		server = self._render_template_value(self.config.get('server'), inputs)
		tool = self._render_template_value(self.config.get('tool'), inputs)
		params_raw = self.config.get('params', {})
		params = self._render_template_value(params_raw, inputs)
		save_as = self.config.get('save_as', 'last_output')
		
		try:
			from main import agent_manager
			if not agent_manager or not getattr(agent_manager, 'mcp_helper', None):
				raise RuntimeError("MCP助手未初始化")
			mcp = agent_manager.mcp_helper
			
			# 处理 server_tool 格式
			actual_server = server
			actual_tool = tool
			if tool and '_' in tool and not server:
				parts = tool.split('_', 1)
				actual_server = parts[0]
				actual_tool = parts[1]
			if not actual_server:
				services = await mcp.get_available_services()
				if not services:
					raise RuntimeError("没有可用的MCP服务")
				actual_server = services[0]
			
			# 调用工具
			result = await mcp.call_tool(
				server_name=actual_server,
				tool_name=actual_tool,
				**(params if isinstance(params, dict) else {"query": str(params)})
			)
			
			# 格式化结果
			try:
				result_text = json.dumps(result, ensure_ascii=False)
			except Exception:
				result_text = str(result)
			
			# 保存输出
			self.save_output(context, result_text)
			
			return self._create_agent_message(result_text, agent_name, metadata={
				'tool_name': f"{actual_server}_{actual_tool}",
				'tool_result': result
			})
		except Exception as e:
			logger.error(f"工具节点执行失败: {str(e)}")
			error_msg = f"工具调用失败: {str(e)}"
			return self._create_agent_message(error_msg, agent_name, metadata={'error': str(e)})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""执行工具调用（流式）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		server = self._render_template_value(self.config.get('server'), inputs)
		tool = self._render_template_value(self.config.get('tool'), inputs)
		params_raw = self.config.get('params', {})
		params = self._render_template_value(params_raw, inputs)
		
		try:
			from main import agent_manager
			if not agent_manager or not getattr(agent_manager, 'mcp_helper', None):
				raise RuntimeError("MCP助手未初始化")
			mcp = agent_manager.mcp_helper
			
			# 处理 server_tool 格式
			actual_server = server
			actual_tool = tool
			if tool and '_' in tool and not server:
				parts = tool.split('_', 1)
				actual_server = parts[0]
				actual_tool = parts[1]
			if not actual_server:
				services = await mcp.get_available_services()
				if not services:
					raise RuntimeError("没有可用的MCP服务")
				actual_server = services[0]
			
			# 调用工具
			result = await mcp.call_tool(
				server_name=actual_server,
				tool_name=actual_tool,
				**(params if isinstance(params, dict) else {"query": str(params)})
			)
			
			# 格式化结果
			try:
				result_text = json.dumps(result, ensure_ascii=False)
			except Exception:
				result_text = str(result)
			
			# 保存输出
			self.save_output(context, result_text)
			
			# 输出工具结果
			yield self._create_stream_chunk(
				chunk_type="tool_result",
				content=result_text,
				agent_name=agent_name,
				metadata={
					'tool_name': f"{actual_server}_{actual_tool}",
					'tool_result': result
				}
			)
		except Exception as e:
			logger.error(f"工具节点流式执行失败: {str(e)}")
			yield self._create_stream_chunk(
				chunk_type="tool_error",
				content=f"工具调用失败: {str(e)}",
				agent_name=agent_name,
				metadata={'error': str(e)}
			)


class StartNode(BaseFlowNode):
	"""起始节点：流程入口，通常只是传递消息"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""起始节点执行：保存初始消息"""
		self.save_output(context, message)
		return self._create_agent_message(f"流程开始: {message}", agent_name)
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""起始节点流式执行"""
		self.save_output(context, message)
		yield self._create_stream_chunk(
			chunk_type="content",
			content=f"流程开始",
			agent_name=agent_name
		)


class EndNode(BaseFlowNode):
	"""结束节点：流程出口，输出最终结果"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""结束节点执行：返回最终结果"""
		flow_state = self._get_flow_state(context)
		final_content = flow_state.get('last_output', '')
		return self._create_agent_message(final_content, agent_name, metadata={'is_final': True})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		"""结束节点流式执行"""
		flow_state = self._get_flow_state(context)
		final_content = flow_state.get('last_output', '')
		yield self._create_stream_chunk(
			chunk_type="final",
			content=final_content,
			agent_name=agent_name,
			is_end=True,
			metadata={'is_final': True}
		)

