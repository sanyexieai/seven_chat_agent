"""LLM 节点实现"""
from typing import Dict, Any, AsyncGenerator

from models.chat_models import AgentMessage, StreamChunk
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper

from ..base_node import BaseFlowNode

import json
import re


logger = get_logger("flow_llm_node")


class LLMNode(BaseFlowNode):
	"""LLM 节点实现：调用 LLM 生成响应"""
	
	async def execute(self, user_id: str, message: str, context: Dict[str, Any], agent_name: str = None) -> AgentMessage:
		"""执行 LLM 调用（同步）"""
		inputs = self.prepare_inputs(message, context)
		
		# 获取配置
		system_prompt = self._render_template_value(self.config.get('system_prompt', ''), inputs)
		user_prompt = self._render_template_value(self.config.get('user_prompt', message), inputs)
		
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
			
			# 流式执行完成后，发送 final chunk 标记结束
			logger.info(f"LLM节点 {self.id} 流式执行完成，发送 final chunk，content length={len(accumulated) if accumulated else 0}")
			final_chunk = self._create_stream_chunk(
				chunk_type="final",
				content=accumulated,
				agent_name=agent_name,
				is_end=True,
				metadata={'is_final': True}
			)
			yield final_chunk
			
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
			clean = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
			match = re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", clean)
			candidate = match.group(1) if match else clean.strip()
			parsed = json.loads(candidate)
			if isinstance(parsed, dict):
				for k, v in parsed.items():
					flow_state[str(k)] = v
		except Exception:
			# 忽略解析失败
			pass

