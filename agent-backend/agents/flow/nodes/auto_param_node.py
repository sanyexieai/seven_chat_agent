"""自动推理工具入参节点"""
from typing import Dict, Any, AsyncGenerator, Optional

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
from utils.prompt_templates import PromptTemplates

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
		schema_json = json.dumps(schema, ensure_ascii=False, indent=2) if schema else "{}"
		previous_output = inputs.get('last_output')
		
		# 如果使用默认提示词模板，使用统一模板生成
		if system_prompt == self._default_system_prompt(tool_name):
			system_text = system_prompt  # 系统提示词不需要格式化
		else:
			# 自定义系统提示词，尝试格式化
			try:
				system_text = system_prompt.format(
					message=message,
					tool_name=tool_name or "",
					tool_type=tool_type or "",
					server=server or "",
					schema_json=schema_json,
					previous_output=previous_output or "",
					target_tool_node_id=target_node_id or ""
				)
			except Exception:
				system_text = system_prompt
		
		# 如果使用默认用户提示词模板，使用统一模板生成
		if user_prompt == self._default_user_prompt():
			user_text = PromptTemplates.get_auto_infer_user_prompt(
				tool_name=tool_name or "",
				tool_type=tool_type,
				server=server,
				schema_json=schema_json,
				message=message,
				previous_output=previous_output,
				required_fields_text="",  # auto_param_node 不单独列出必填字段
				use_simple=True  # 使用简化模板
			)
		else:
			# 自定义用户提示词，尝试格式化
			try:
				user_text = user_prompt.format(
					message=message,
					tool_name=tool_name or "",
					tool_type=tool_type or "",
					server=server or "",
					schema_json=schema_json,
					previous_output=previous_output or "",
					target_tool_node_id=target_node_id or "",
					required_fields_text=""  # 兼容旧模板
				)
			except Exception:
				# 兼容旧版 {{ }} 模板写法
				user_text = self._render_template_value(user_prompt, {
					'message': message,
					'tool_name': tool_name or "",
					'tool_type': tool_type or "",
					'server': server or "",
					'schema_json': schema_json,
					'previous_output': previous_output or "",
					'target_tool_node_id': target_node_id or ""
				})
		
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
				schema = self.config.get('tool_schema')
			else:
				tool_manager = agent_manager.tool_manager
				target_name = tool_name
				if tool_type == 'mcp' and server and tool_name and not tool_name.startswith('mcp_'):
					target_name = f"mcp_{server}_{tool_name}"
				tool_obj = tool_manager.get_tool(target_name) if target_name else None
				if tool_obj:
					schema = tool_obj.get_parameters_schema()
				else:
					schema = self.config.get('tool_schema')
			
			# 过滤掉已废弃的参数（如 model）
			if schema and isinstance(schema, dict):
				schema = schema.copy()
				# 从 properties 中移除 model 参数
				if 'properties' in schema and isinstance(schema['properties'], dict):
					schema['properties'] = {k: v for k, v in schema['properties'].items() if k != 'model'}
				# 从 required 列表中移除 model
				if 'required' in schema and isinstance(schema['required'], list):
					schema['required'] = [r for r in schema['required'] if r != 'model']
			
			return schema
		except Exception as exc:
			logger.warning(f"自动推理节点 {self.id} 获取工具 schema 失败: {exc}")
			schema = self.config.get('tool_schema')
			# 即使出错也尝试过滤
			if schema and isinstance(schema, dict):
				schema = schema.copy()
				if 'properties' in schema and isinstance(schema['properties'], dict):
					schema['properties'] = {k: v for k, v in schema['properties'].items() if k != 'model'}
				if 'required' in schema and isinstance(schema['required'], list):
					schema['required'] = [r for r in schema['required'] if r != 'model']
			return schema
	
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
		"""获取默认系统提示词（从统一模板获取）"""
		return PromptTemplates.get_auto_infer_system_prompt()
	
	def _default_user_prompt(self) -> str:
		"""获取默认用户提示词模板标识（用于比较）"""
		# 返回一个标识字符串，用于判断是否使用默认模板
		# 实际模板内容通过 PromptTemplates.get_auto_infer_user_prompt() 获取
		return "__DEFAULT_AUTO_INFER_USER_PROMPT__"
	
	def _get_auto_param_key(self) -> str:
		return self.config.get('auto_param_key') or f"auto_params_{self.config.get('target_tool_node_id') or self.id}"

