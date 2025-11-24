"""自动推理工具入参节点"""
from typing import Dict, Any, AsyncGenerator, Optional

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper

from ..base_node import BaseFlowNode, NodeCategory

import json


logger = get_logger("flow_auto_param_node")


class AutoParamNode(BaseFlowNode):
	"""自动推理节点：通过 LLM 生成工具可用的入参"""
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		if self.category != NodeCategory.PROCESSOR:
			self.category = NodeCategory.PROCESSOR
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		params = await self._generate_params(message, context)
		auto_param_key = self._get_auto_param_key()
		self._save_to_flow_state(context, auto_param_key, params, also_save_as_last_output=False)
		self.set_node_value(context, 'generated_params', params)
		content = f"已生成工具参数：{json.dumps(params, ensure_ascii=False)}"
		return self._create_agent_message(content, agent_name, metadata={
			'auto_param_key': auto_param_key,
			'params': params
		})
	
	async def execute_stream(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AsyncGenerator[StreamChunk, None]:
		result = await self.execute(user_id, message, context, agent_name)
		yield self._create_stream_chunk(
			chunk_type="content",
			content=result.content,
			agent_name=agent_name,
			metadata=result.metadata
		)
		yield self._create_stream_chunk(
			chunk_type="final",
			content=result.content,
			agent_name=agent_name,
			is_end=True,
			metadata=result.metadata
		)
	
	async def _generate_params(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
		tool_name = self.config.get('tool_name') or self.config.get('tool')
		tool_type = self.config.get('tool_type')
		server = self.config.get('server')
		target_node_id = self.config.get('target_tool_node_id')
		schema = await self._get_tool_schema(tool_name, tool_type, server)
		system_prompt = self.config.get('system_prompt') or self._default_system_prompt(tool_name)
		user_prompt = self.config.get('user_prompt') or self._default_user_prompt()
		
		inputs = self.prepare_inputs(message, context)
		prompt_variables = {
			'message': message,
			'tool_name': tool_name,
			'tool_type': tool_type,
			'server': server,
			'schema_json': json.dumps(schema, ensure_ascii=False, indent=2) if schema else "{}",
			'previous_output': inputs.get('last_output'),
			'target_tool_node_id': target_node_id
		}
		
		system_text = system_prompt.format(**prompt_variables)
		try:
			user_text = user_prompt.format(**prompt_variables)
		except Exception:
			# 兼容旧版 {{ }} 模板写法
			user_text = self._render_template_value(user_prompt, prompt_variables)
		
		llm_helper = get_llm_helper()
		messages = [
			{"role": "system", "content": system_text},
			{"role": "user", "content": user_text}
		]
		try:
			response = await llm_helper.call(messages, max_tokens=self.config.get('max_tokens', 800))
			params = self._parse_params(response)
			if not params:
				params = self._fallback_params(message, schema)
			return params
		except Exception as exc:
			logger.error(f"自动推理节点 {self.id} 调用 LLM 失败: {exc}")
			return self._fallback_params(message, schema)
	
	async def _get_tool_schema(self, tool_name: Optional[str], tool_type: Optional[str], server: Optional[str]) -> Optional[Dict[str, Any]]:
		try:
			from main import agent_manager
			if not agent_manager or not agent_manager.tool_manager:
				return self.config.get('tool_schema')
			tool_manager = agent_manager.tool_manager
			target_name = tool_name
			if tool_type == 'mcp' and server and tool_name and not tool_name.startswith('mcp_'):
				target_name = f"mcp_{server}_{tool_name}"
			tool_obj = tool_manager.get_tool(target_name) if target_name else None
			if tool_obj:
				return tool_obj.get_parameters_schema()
		except Exception as exc:
			logger.warning(f"自动推理节点 {self.id} 获取工具 schema 失败: {exc}")
		return self.config.get('tool_schema')
	
	def _parse_params(self, text: str) -> Optional[Dict[str, Any]]:
		if not text:
			return None
		try:
			clean = text.strip()
			if clean.startswith("```"):
				clean = clean.strip("`")
				clean = clean.replace("json", "", 1).strip()
			return json.loads(clean)
		except Exception:
			return None
	
	def _fallback_params(self, message: str, schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
		params: Dict[str, Any] = {}
		required = schema.get('required') if isinstance(schema, dict) else None
		if isinstance(required, list) and required:
			for field in required:
				params[field] = message
		else:
			params['query'] = message
		return params
	
	def _default_system_prompt(self, tool_name: Optional[str]) -> str:
		return (
			"你是一个工具参数推理助手。请根据用户输入和工具描述，生成满足工具 schema 的 JSON 参数。"
			"必须输出 JSON，对每个必填字段给出合理值。"
		)
	
	def _default_user_prompt(self) -> str:
		return (
			"工具名称：{tool_name}\n"
			"工具类型：{tool_type}\n"
			"服务器：{server}\n"
			"参数 Schema：\n{schema_json}\n\n"
			"用户输入：{message}\n"
			"如果需要上下文，可参考上一节点输出：{previous_output}\n\n"
			"请输出 JSON，严格遵守 schema 格式。"
		)
	
	def _get_auto_param_key(self) -> str:
		return self.config.get('auto_param_key') or f"auto_params_{self.config.get('target_tool_node_id') or self.id}"

