"""工具节点实现"""
from typing import Dict, Any, AsyncGenerator, Optional

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
		
		# 预处理参数
		params = self._prepare_params(params)
		auto_params = self._get_auto_generated_params(context)
		if auto_params:
			logger.info(f"工具节点 {self.id} 使用自动推理参数: {auto_params}")
			params = auto_params
		
		# 调试日志：输出配置信息
		logger.info(f"工具节点 {self.id} 配置: tool_name={tool_name}, server={server}, tool={tool}, tool_type={tool_type}")
		logger.info(f"工具节点 {self.id} 参数: params_raw={params_raw}, params={params}, params_type={type(params)}")
		
		try:
			from main import agent_manager
			if not agent_manager:
				raise RuntimeError("智能体管理器未初始化")
			
			# 优先使用 ToolManager 执行工具
			# 如果有 tool_name 或者有 tool_type，尝试使用 ToolManager
			if (tool_name or tool_type) and agent_manager.tool_manager:
				tool_manager = agent_manager.tool_manager
				
				# 如果 tool_type 明确是 mcp，优先使用 MCP 方式构建 tool_name
				if tool_type == 'mcp':
					if server and tool:
						# 优先使用 server + tool 构建
						tool_name = f"mcp_{server}_{tool}"
						logger.info(f"工具节点 {self.id} 根据 tool_type=mcp 构建 tool_name: {tool_name}")
					elif tool_name and tool_name.startswith('mcp_'):
						# 如果 tool_name 已经是 MCP 格式，直接使用
						logger.info(f"工具节点 {self.id} 使用已有的 MCP tool_name: {tool_name}")
					elif tool:
						# 如果 tool_type 是 mcp 但没有 server，尝试查找匹配的 MCP 工具
						logger.warning(f"工具节点 {self.id} tool_type=mcp 但缺少 server，尝试查找可用 MCP 工具")
						available_tools = tool_manager.get_available_tools()
						for available_tool in available_tools:
							if available_tool.get('type') == 'mcp' and (available_tool.get('name') == tool or available_tool.get('name').endswith(f"_{tool}")):
								tool_name = available_tool.get('name')
								logger.info(f"工具节点 {self.id} 找到 MCP 工具: {tool_name}")
								break
				# 如果没有 tool_name 但有 tool，尝试构建 tool_name
				elif not tool_name and tool:
					if tool_type == 'temporary':
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
				
				logger.info(f"工具节点 {self.id} 最终 tool_name: {tool_name}, 将使用 ToolManager 执行")
				
				# 如果找到了 tool_name，使用 ToolManager 执行
				if tool_name:
					logger.info(f"工具节点 {self.id} 当前参数: {params}")
					
					# 获取工具的参数模式，检查必需参数
					tool_obj = tool_manager.get_tool(tool_name)
					if tool_obj:
						self._fill_required_params(tool_obj, params, message, context)
						logger.info(f"工具节点 {self.id} 填充必需参数后的参数: {params}")
					
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
		
		params = self._prepare_params(params)
		auto_params = self._get_auto_generated_params(context)
		if auto_params:
			logger.info(f"工具节点 {self.id} 使用自动推理参数: {auto_params}")
			params = auto_params
		
		# 调试日志：输出配置信息
		logger.info(f"工具节点 {self.id} 配置: tool_name={tool_name}, server={server}, tool={tool}, tool_type={tool_type}")
		logger.info(f"工具节点 {self.id} 参数: params_raw={params_raw}, params={params}, params_type={type(params)}")
		
		try:
			from main import agent_manager
			if not agent_manager:
				raise RuntimeError("智能体管理器未初始化")
			
			# 优先使用 ToolManager 执行工具
			if (tool_name or tool_type) and agent_manager.tool_manager:
				tool_manager = agent_manager.tool_manager
				
				# 如果 tool_type 明确是 mcp，优先使用 MCP 方式构建 tool_name
				if tool_type == 'mcp':
					if server and tool:
						# 优先使用 server + tool 构建
						tool_name = f"mcp_{server}_{tool}"
						logger.info(f"工具节点 {self.id} 根据 tool_type=mcp 构建 tool_name: {tool_name}")
					elif tool_name and tool_name.startswith('mcp_'):
						# 如果 tool_name 已经是 MCP 格式，直接使用
						logger.info(f"工具节点 {self.id} 使用已有的 MCP tool_name: {tool_name}")
					elif tool:
						# 如果 tool_type 是 mcp 但没有 server，尝试查找匹配的 MCP 工具
						logger.warning(f"工具节点 {self.id} tool_type=mcp 但缺少 server，尝试查找可用 MCP 工具")
						available_tools = tool_manager.get_available_tools()
						for available_tool in available_tools:
							if available_tool.get('type') == 'mcp' and (available_tool.get('name') == tool or available_tool.get('name').endswith(f"_{tool}")):
								tool_name = available_tool.get('name')
								logger.info(f"工具节点 {self.id} 找到 MCP 工具: {tool_name}")
								break
				# 如果没有 tool_name 但有 tool，尝试构建 tool_name
				elif not tool_name and tool:
					if tool_type == 'temporary':
						tool_name = f"temp_{tool}"
					elif tool_type == 'builtin':
						tool_name = tool
					else:
						available_tools = tool_manager.get_available_tools()
						for available_tool in available_tools:
							if available_tool.get('name') == tool or available_tool.get('name').endswith(f"_{tool}"):
								tool_name = available_tool.get('name')
								break
				
				logger.info(f"工具节点 {self.id} 最终 tool_name: {tool_name}, 将使用 ToolManager 执行")
				
				if tool_name:
					logger.info(f"工具节点 {self.id} 当前参数: {params}")
					
					tool_obj = tool_manager.get_tool(tool_name)
					if tool_obj:
						self._fill_required_params(tool_obj, params, message, context)
						logger.info(f"工具节点 {self.id} 填充必需参数后的参数: {params}")
					
					# 特殊处理：如果是报告工具且 file_names 为空或包含特殊标记，从 flow_state 获取
					if tool_name == "report" and isinstance(params, dict):
						file_names = params.get("file_names", [])
						flow_state = self._get_flow_state(context)
						
						# 如果 file_names 为空、None 或包含特殊标记，从 flow_state 获取
						if not file_names or file_names == [] or (isinstance(file_names, str) and "{{saved_files}}" in file_names):
							saved_files = flow_state.get("saved_files", [])
							if saved_files:
								params["file_names"] = saved_files
								logger.info(f"工具节点 {self.id} 从 flow_state 获取文件列表: {saved_files}")
							elif isinstance(file_names, str) and "{{saved_files}}" in file_names:
								# 如果使用了模板但 saved_files 为空，使用空列表
								params["file_names"] = []
					
					result = await tool_manager.execute_tool(tool_name, params)
					result_text = self._format_tool_result(result)
					
					# 处理结果并保存文件路径到 flow_state
					flow_state = self._get_flow_state(context)
					saved_file_path = None
					
					# 情况1：结果是字典且包含文件路径
					if isinstance(result, dict):
						if "file_path" in result or "file_name" in result:
							file_path = result.get("file_path") or result.get("file_name")
							if file_path:
								saved_file_path = file_path
					
					# 情况2：如果是搜索工具（builtin 或 MCP），且结果是字符串，自动保存到文件
					if not saved_file_path and isinstance(result_text, str) and result_text:
						# 检测是否是搜索工具
						is_search_tool = (
							tool_name in ["deepsearch", "mcp_1_search", "mcp_ddg_search"] or
							"search" in tool_name.lower() or
							(tool_type == "mcp" and tool and "search" in tool.lower())
						)
						
						# 检测结果是否包含搜索结果（通常包含 URL、标题等特征）
						has_search_results = (
							"Found" in result_text and "search results" in result_text.lower() or
							"URL:" in result_text or
							"http" in result_text or
							len(result_text) > 500  # 搜索结果通常比较长
						)
						
						if is_search_tool and has_search_results:
							try:
								import os
								from datetime import datetime
								
								# 创建搜索结果目录
								search_results_dir = "search_results"
								os.makedirs(search_results_dir, exist_ok=True)
								
								# 生成文件名
								timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
								# 从查询中提取关键词
								query = params.get("query", "") if isinstance(params, dict) else str(params)
								query_slug = "".join(c for c in query[:30] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
								if not query_slug:
									query_slug = "search"
								
								file_path = os.path.join(search_results_dir, f"{query_slug}_{timestamp}_search_result.txt")
								
								# 准备文件内容
								file_content_parts = []
								file_content_parts.append(f"搜索工具: {tool_name}\n")
								if isinstance(params, dict) and params.get("query"):
									file_content_parts.append(f"搜索查询: {params['query']}\n")
								file_content_parts.append(f"搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
								file_content_parts.append(f"=" * 80 + "\n\n")
								file_content_parts.append(result_text)
								
								# 写入文件
								with open(file_path, 'w', encoding='utf-8') as f:
									f.write("".join(file_content_parts))
								
								# 计算相对路径
								project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
								try:
									rel_path = os.path.relpath(file_path, project_root)
									rel_path = rel_path.replace("\\", "/")
								except ValueError:
									rel_path = file_path.replace("\\", "/")
								
								saved_file_path = rel_path
								logger.info(f"工具节点 {self.id} 自动保存搜索结果到文件: {saved_file_path}")
								
							except Exception as e:
								logger.warning(f"工具节点 {self.id} 自动保存搜索结果失败: {str(e)}")
					
					# 保存文件路径到 flow_state
					if saved_file_path:
						if "saved_files" not in flow_state:
							flow_state["saved_files"] = []
						if saved_file_path not in flow_state["saved_files"]:
							flow_state["saved_files"].append(saved_file_path)
							logger.info(f"工具节点 {self.id} 保存文件路径到 flow_state: {saved_file_path}")
						
						# 也保存为节点特定的键
						node_file_key = f"{self.id}_file_path"
						flow_state[node_file_key] = saved_file_path
					
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
			
			# 处理 MCP 工具结果并保存文件路径到 flow_state
			flow_state = self._get_flow_state(context)
			saved_file_path = None
			
			# 如果是搜索工具且结果是字符串，自动保存到文件
			if isinstance(result_text, str) and result_text:
				is_search_tool = (
					"search" in actual_tool.lower() or
					"search" in tool_name.lower()
				)
				
				has_search_results = (
					"Found" in result_text and "search results" in result_text.lower() or
					"URL:" in result_text or
					"http" in result_text or
					len(result_text) > 500
				)
				
				if is_search_tool and has_search_results:
					try:
						import os
						from datetime import datetime
						
						search_results_dir = "search_results"
						os.makedirs(search_results_dir, exist_ok=True)
						
						timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
						query = params.get("query", "") if isinstance(params, dict) else str(params)
						query_slug = "".join(c for c in query[:30] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
						if not query_slug:
							query_slug = "search"
						
						file_path = os.path.join(search_results_dir, f"{query_slug}_{timestamp}_search_result.txt")
						
						file_content_parts = []
						file_content_parts.append(f"搜索工具: {actual_server}.{actual_tool}\n")
						if isinstance(params, dict) and params.get("query"):
							file_content_parts.append(f"搜索查询: {params['query']}\n")
						file_content_parts.append(f"搜索时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
						file_content_parts.append(f"=" * 80 + "\n\n")
						file_content_parts.append(result_text)
						
						with open(file_path, 'w', encoding='utf-8') as f:
							f.write("".join(file_content_parts))
						
						project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
						try:
							rel_path = os.path.relpath(file_path, project_root)
							rel_path = rel_path.replace("\\", "/")
						except ValueError:
							rel_path = file_path.replace("\\", "/")
						
						saved_file_path = rel_path
						logger.info(f"工具节点 {self.id} (MCP) 自动保存搜索结果到文件: {saved_file_path}")
						
					except Exception as e:
						logger.warning(f"工具节点 {self.id} (MCP) 自动保存搜索结果失败: {str(e)}")
			
			# 保存文件路径到 flow_state
			if saved_file_path:
				if "saved_files" not in flow_state:
					flow_state["saved_files"] = []
				if saved_file_path not in flow_state["saved_files"]:
					flow_state["saved_files"].append(saved_file_path)
					logger.info(f"工具节点 {self.id} (MCP) 保存文件路径到 flow_state: {saved_file_path}")
				
				node_file_key = f"{self.id}_file_path"
				flow_state[node_file_key] = saved_file_path
			
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
		
		# 清理 params，确保不包含 schema 定义
		params = self._clean_params(params)
		
		for param_name in required_params:
			if param_name in params:
				# 确保参数值不是 schema 对象
				if isinstance(params[param_name], dict) and ('$defs' in params[param_name] or 'type' in params[param_name] or 'properties' in params[param_name]):
					logger.warning(f"工具节点 {self.id} 参数 {param_name} 是 schema 对象，将被替换")
					params[param_name] = None
				else:
					continue
			
			if param_name in ["query", "task"]:
				params[param_name] = message or self._get_flow_state(context).get('last_output', '') or ""
				logger.info(f"工具节点 {self.id} 自动填充必需参数 {param_name}={params[param_name][:50] if params[param_name] else 'None'}...")
			else:
				flow_state = self._get_flow_state(context)
				if param_name in flow_state:
					value = flow_state[param_name]
					# 确保从 flow_state 获取的值不是 schema 对象
					if isinstance(value, dict) and ('$defs' in value or 'type' in value or 'properties' in value):
						logger.warning(f"工具节点 {self.id} flow_state 中的 {param_name} 是 schema 对象，使用 message 替代")
						params[param_name] = message or ""
					else:
						params[param_name] = value
					logger.info(f"工具节点 {self.id} 从 flow_state 获取参数 {param_name}")
				elif message:
					params[param_name] = message
					logger.info(f"工具节点 {self.id} 使用 message 作为参数 {param_name} 的默认值")
				else:
					last_output = flow_state.get('last_output', '')
					params[param_name] = last_output
					logger.info(f"工具节点 {self.id} 使用 last_output 作为参数 {param_name} 的默认值")
	
	def _clean_params(self, params: Any) -> Dict[str, Any]:
		"""清理参数，移除 schema 定义字段"""
		if not isinstance(params, dict):
			return {}
		
		cleaned = {}
		for k, v in params.items():
			# 跳过 schema 定义字段
			if k.startswith('$') or k in ['$defs', '$schema', 'type', 'properties', 'required', 'definitions', 'title', 'description']:
				continue
			# 如果值是字典且包含 schema 特征，跳过
			if isinstance(v, dict) and ('$defs' in v or ('type' in v and 'properties' in v)):
				logger.warning(f"工具节点 {self.id} 跳过 schema 对象参数: {k}")
				continue
			cleaned[k] = v
		
		return cleaned
	
	def _prepare_params(self, params: Any) -> Dict[str, Any]:
		"""标准化参数对象"""
		params = self._extract_effective_params(params)
		if isinstance(params, dict):
			cleaned = self._clean_params(params)
			return cleaned if cleaned else {}
		if params:
			return {"query": str(params)}
		return {}
	
	def _get_auto_generated_params(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		auto_key = self.config.get('auto_param_key') or f"auto_params_{self.id}"
		if not auto_key:
			return None
		value = self._get_from_flow_state(context, auto_key)
		if not value:
			return None
		if isinstance(value, str):
			try:
				value = json.loads(value)
			except Exception:
				logger.warning(f"工具节点 {self.id} 无法解析自动推理字符串参数")
				return None
		if isinstance(value, dict):
			effective = self._extract_effective_params(value)
			return self._clean_params(effective)
		return None
	
	def _extract_effective_params(self, params: Any) -> Any:
		"""提取真正的工具入参（剥离 tool_call、tool_calls 结构）"""
		if isinstance(params, str):
			try:
				parsed = json.loads(params)
				return self._extract_effective_params(parsed)
			except Exception:
				return {"query": params}
		
		if isinstance(params, list) and params:
			return self._extract_effective_params(params[0])
		
		if isinstance(params, dict):
			# OpenAI style tool_calls
			if 'tool_calls' in params and isinstance(params['tool_calls'], list) and params['tool_calls']:
				return self._extract_effective_params(params['tool_calls'][0])
			
			# tool_call object (name/args/id/type)
			if 'args' in params and isinstance(params['args'], dict):
				logger.info(f"工具节点 {self.id} 解析 tool_call 结构，改用 args 字段作为真实入参")
				return params['args']
			
			# openai function style: arguments 是 JSON 字符串
			if 'arguments' in params:
				arguments = params['arguments']
				if isinstance(arguments, str):
					try:
						return json.loads(arguments)
					except Exception:
						return {"query": arguments}
				if isinstance(arguments, dict):
					return arguments
			
			# 继续递归可能嵌套的字段
			for key in ['output', 'content']:
				if key in params and isinstance(params[key], (dict, list)):
					return self._extract_effective_params(params[key])
		
		return params
	
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



