"""工具节点实现"""
from typing import Dict, Any, AsyncGenerator

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger

from ..base_node import BaseFlowNode

import json
import re


logger = get_logger("flow_tool_node")


class ToolNode(BaseFlowNode):
	"""工具节点实现：调用所有类型的工具（内置工具、MCP工具、临时工具）"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行工具调用（同步）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		tool_name = self._render_template_value(self.config.get('tool_name'), inputs)
		server = self._render_template_value(self.config.get('server'), inputs)
		tool = self._render_template_value(self.config.get('tool'), inputs)
		tool_type = self.config.get('tool_type')  # builtin, mcp, temporary
		params_raw = self.config.get('params', {})
		params = self._render_template_value(params_raw, inputs)
		
		try:
			from main import agent_manager
			if not agent_manager:
				raise RuntimeError("智能体管理器未初始化")
			
			# 优先使用 ToolManager 执行工具
			# 如果有 tool_name 或者有 tool_type，尝试使用 ToolManager
			if (tool_name or tool_type) and agent_manager.tool_manager:
				tool_manager = agent_manager.tool_manager
				
				# 如果没有 tool_name 但有 tool，尝试构建 tool_name
				if not tool_name and tool:
					if tool_type == 'mcp' and server:
						tool_name = f"mcp_{server}_{tool}"
					elif tool_type == 'temporary':
						tool_name = f"temp_{tool}"
					elif tool_type == 'builtin':
						tool_name = tool
					else:
						# 尝试从 tool_manager 中查找匹配的工具
						available_tools = tool_manager.get_available_tools()
						for available_tool in available_tools:
							if available_tool.get('name') == tool or available_tool.get('name').endswith(f"_{tool}"):
								tool_name = available_tool.get('name')
								break
				
				# 如果找到了 tool_name，使用 ToolManager 执行
				if tool_name:
					# 确保参数是字典格式
					if not isinstance(params, dict):
						params = {"query": str(params)} if params else {}
					
					# 如果参数为空，尝试从上下文中获取默认值
					if not params:
						params = {}
					
					# 获取工具的参数模式，检查必需参数
					tool_obj = tool_manager.get_tool(tool_name)
					if tool_obj:
						self._fill_required_params(tool_obj, params, message, context)
					
					# 执行工具
					result = await tool_manager.execute_tool(tool_name, params)
					
					result_text = self._format_tool_result(result)
					
					# 保存输出
					self.save_output(context, result_text)
					
					return self._create_agent_message(result_text, agent_name, metadata={
						'tool_name': tool_name,
						'tool_type': tool_type,
						'tool_result': result
					})
			
			# 向后兼容：如果没有 tool_name，使用旧的 MCP 调用方式
			if not agent_manager.mcp_helper:
				raise RuntimeError("MCP助手未初始化，且未指定工具名称")
			
			mcp = agent_manager.mcp_helper
			
			# 处理 server_tool 格式
			actual_server, actual_tool = await self._resolve_server_tool(server, tool, mcp)
			
			# 调用工具
			result = await mcp.call_tool(
				server_name=actual_server,
				tool_name=actual_tool,
				**(params if isinstance(params, dict) else {"query": str(params)})
			)
			
			result_text = self._format_tool_result(result)
			
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
		tool_name = self._render_template_value(self.config.get('tool_name'), inputs)
		server = self._render_template_value(self.config.get('server'), inputs)
		tool = self._render_template_value(self.config.get('tool'), inputs)
		tool_type = self.config.get('tool_type')  # builtin, mcp, temporary
		params_raw = self.config.get('params', {})
		params = self._render_template_value(params_raw, inputs)
		
		try:
			from main import agent_manager
			if not agent_manager:
				raise RuntimeError("智能体管理器未初始化")
			
			# 优先使用 ToolManager 执行工具
			if (tool_name or tool_type) and agent_manager.tool_manager:
				tool_manager = agent_manager.tool_manager
				
				# 如果没有 tool_name 但有 tool，尝试构建 tool_name
				if not tool_name and tool:
					if tool_type == 'mcp' and server:
						tool_name = f"mcp_{server}_{tool}"
					elif tool_type == 'temporary':
						tool_name = f"temp_{tool}"
					elif tool_type == 'builtin':
						tool_name = tool
					else:
						available_tools = tool_manager.get_available_tools()
						for available_tool in available_tools:
							if available_tool.get('name') == tool or available_tool.get('name').endswith(f"_{tool}"):
								tool_name = available_tool.get('name')
								break
				
				if tool_name:
					if not isinstance(params, dict):
						params = {"query": str(params)} if params else {}
					if not params:
						params = {}
					
					tool_obj = tool_manager.get_tool(tool_name)
					if tool_obj:
						self._fill_required_params(tool_obj, params, message, context)
					
					result = await tool_manager.execute_tool(tool_name, params)
					result_text = self._format_tool_result(result)
					
					self.save_output(context, result_text)
					self.append_node_output(context, result_text, node_id=self.id, also_save_as_last_output=False)
					
					download_info = self._extract_report_info(tool_name, result_text)
					
					yield self._create_stream_chunk(
						chunk_type="tool_result",
						content=result_text,
						agent_name=agent_name,
						metadata={
							'tool_name': tool_name,
							'tool_type': tool_type,
							'tool_result': result,
							'download_info': download_info
						}
					)
					
					display_content = download_info.get('full_content') if download_info and 'full_content' in download_info else result_text
					
					yield self._create_stream_chunk(
						chunk_type="content",
						content=display_content,
						agent_name=agent_name,
						metadata={
							'tool_name': tool_name,
							'tool_type': tool_type,
							'download_info': download_info
						}
					)
					
					final_chunk = self._create_stream_chunk(
						chunk_type="final",
						content=display_content,
						agent_name=agent_name,
						is_end=True,
						metadata={
							'is_final': True,
							'tool_name': tool_name,
							'tool_type': tool_type,
							'tool_result': result,
							'download_info': download_info
						}
					)
					yield final_chunk
					return
			
			# 向后兼容：如果没有 tool_name，使用旧的 MCP 调用方式
			if not agent_manager.mcp_helper:
				raise RuntimeError("MCP助手未初始化，且未指定工具名称")
			
			mcp = agent_manager.mcp_helper
			actual_server, actual_tool = await self._resolve_server_tool(server, tool, mcp)
			
			result = await mcp.call_tool(
				server_name=actual_server,
				tool_name=actual_tool,
				**(params if isinstance(params, dict) else {"query": str(params)})
			)
			
			result_text = self._format_tool_result(result)
			
			self.save_output(context, result_text)
			self.append_node_output(context, result_text, node_id=self.id, also_save_as_last_output=False)
			
			yield self._create_stream_chunk(
				chunk_type="tool_result",
				content=result_text,
				agent_name=agent_name,
				metadata={
					'tool_name': f"{actual_server}_{actual_tool}",
					'tool_result': result
				}
			)
			yield self._create_stream_chunk(
				chunk_type="content",
				content=result_text,
				agent_name=agent_name,
				metadata={
					'tool_name': f"{actual_server}_{actual_tool}"
				}
			)
			
			final_chunk = self._create_stream_chunk(
				chunk_type="final",
				content=result_text,
				agent_name=agent_name,
				is_end=True,
				metadata={
					'is_final': True,
					'tool_name': f"{actual_server}_{actual_tool}",
					'tool_result': result
				}
			)
			yield final_chunk
		except Exception as e:
			logger.error(f"工具节点流式执行失败: {str(e)}")
			yield self._create_stream_chunk(
				chunk_type="tool_error",
				content=f"工具调用失败: {str(e)}",
				agent_name=agent_name,
				metadata={'error': str(e)}
			)
	
	def _fill_required_params(self, tool_obj, params: Dict[str, Any], message: str, context: Dict[str, Any]):
		"""检查并补全工具所需的参数"""
		schema = tool_obj.get_parameters_schema()
		required_params = schema.get("required", [])
		
		for param_name in required_params:
			if param_name in params:
				continue
			if param_name in ["query", "task"]:
				params[param_name] = message or self._get_flow_state(context).get('last_output', '') or ""
				logger.info(f"工具节点 {self.id} 自动填充必需参数 {param_name}={params[param_name][:50]}...")
			else:
				flow_state = self._get_flow_state(context)
				if param_name in flow_state:
					params[param_name] = flow_state[param_name]
					logger.info(f"工具节点 {self.id} 从 flow_state 获取参数 {param_name}")
				elif message:
					params[param_name] = message
					logger.info(f"工具节点 {self.id} 使用 message 作为参数 {param_name} 的默认值")
				else:
					last_output = flow_state.get('last_output', '')
					params[param_name] = last_output
					logger.info(f"工具节点 {self.id} 使用 last_output 作为参数 {param_name} 的默认值")
	
	async def _resolve_server_tool(self, server: str, tool: str, mcp_helper):
		"""解析 server 和 tool 名称"""
		actual_server = server
		actual_tool = tool
		if tool and '_' in tool and not server:
			parts = tool.split('_', 1)
			actual_server = parts[0]
			actual_tool = parts[1]
		if not actual_server:
			services = await mcp_helper.get_available_services()
			if not services:
				raise RuntimeError("没有可用的MCP服务")
			actual_server = services[0]
		return actual_server, actual_tool
	
	def _format_tool_result(self, result: Any) -> str:
		"""格式化工具结果为字符串"""
		if isinstance(result, dict):
			if 'frontend_output' in result:
				return result.get('frontend_output', '')
			return json.dumps(result, ensure_ascii=False)
		if isinstance(result, list):
			return "\n".join(str(item) for item in result)
		return str(result)
	
	def _extract_report_info(self, tool_name: str, result_text: str):
		"""提取报告工具的下载信息"""
		if tool_name != "report":
			return None
		match = re.search(r'<!-- REPORT_DOWNLOAD_INFO: ({.*?}) -->', result_text, re.DOTALL)
		if not match:
			return None
		try:
			return json.loads(match.group(1))
		except Exception:
			return None



