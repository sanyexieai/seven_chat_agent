"""
智能体适配器：将智能体的工作流配置转换为 FlowEngine 执行

支持从智能体（如 FlowDrivenAgent）获取工作流配置，并使用 FlowEngine 执行。
"""
from typing import Dict, Any, Optional, AsyncGenerator
from agents.base_agent import BaseAgent
from agents.flow.engine import FlowEngine
from agents.flow.business_handler import FlowBusinessHandler
from models.chat_models import StreamChunk
from utils.log_helper import get_logger
from sqlalchemy.orm import Session

# 导入 flow 模块以触发节点实现注册
import agents.flow  # noqa: F401

logger = get_logger("flow_agent_adapter")


def create_engine_from_agent(
	agent: BaseAgent,
	db: Optional[Session] = None,
	user_id: Optional[str] = None,
	session_id: Optional[str] = None,
	agent_name: Optional[str] = None
) -> Optional[FlowEngine]:
	"""
	从智能体创建 FlowEngine 实例
	
	Args:
		agent: 智能体实例
		db: 数据库会话（可选）
		user_id: 用户ID（可选）
		session_id: 会话ID（可选）
		agent_name: 智能体名称（可选）
		
	Returns:
		FlowEngine 实例，如果智能体不支持工作流则返回 None
	"""
	# 检查智能体是否有工作流配置
	flow_config = None
	if hasattr(agent, 'flow_config') and agent.flow_config:
		flow_config = agent.flow_config
	elif hasattr(agent, 'get_flow_config'):
		flow_config = agent.get_flow_config()
	
	if not flow_config:
		return None
	
	# 创建业务逻辑处理器
	business_handler = FlowBusinessHandler(db=db)
	business_handler.user_id = user_id
	business_handler.session_id = session_id
	business_handler.agent_name = agent_name or (agent.description if hasattr(agent, 'description') else agent.name)
	
	# 创建引擎
	engine = FlowEngine(
		on_chunk=business_handler.on_chunk,
		on_final=business_handler.on_final
	)
	
	# 构建工作流
	engine.build_from_config(flow_config)
	
	return engine


async def execute_agent_stream(
	agent: BaseAgent,
	user_id: str,
	message: str,
	context: Dict[str, Any],
	db: Optional[Session] = None,
	session_id: Optional[str] = None,
	business_handler: Optional[FlowBusinessHandler] = None
) -> AsyncGenerator[StreamChunk, None]:
	"""
	执行智能体的流式处理（优先使用工作流引擎，否则回退到智能体的 process_message_stream）
	
	Args:
		agent: 智能体实例
		user_id: 用户ID
		message: 用户消息
		context: 上下文字典
		db: 数据库会话（可选）
		session_id: 会话ID（可选）
		business_handler: 业务逻辑处理器（可选，如果提供则使用，否则创建新的）
		
	Yields:
		StreamChunk: 流式响应块
	"""
	# 检查智能体是否有工作流配置
	flow_config = None
	if hasattr(agent, 'flow_config') and agent.flow_config:
		flow_config = agent.flow_config
	elif hasattr(agent, 'get_flow_config'):
		flow_config = agent.get_flow_config()
	
	if flow_config:
		# 使用工作流引擎执行
		logger.info(f"使用工作流引擎执行智能体: {agent.name}")
		
		# 创建或使用提供的业务逻辑处理器
		if not business_handler:
			business_handler = FlowBusinessHandler(db=db)
			business_handler.user_id = user_id
			business_handler.session_id = session_id
			business_handler.agent_name = agent.description if hasattr(agent, 'description') else agent.name
		
		# 创建引擎
		engine = FlowEngine(
			on_chunk=business_handler.on_chunk,
			on_final=business_handler.on_final
		)
		
		# 构建工作流
		engine.build_from_config(flow_config)
		
		# 保存用户消息
		if session_id and db:
			business_handler.save_user_message(message)
		
		# 执行工作流
		agent_name = agent.description if hasattr(agent, 'description') else agent.name
		async for chunk in engine.run_stream(
			user_id=user_id,
			message=message,
			context=context,
			agent_name=agent_name,
			session_id=session_id
		):
			yield chunk
		
		# 发送完成信号
		yield StreamChunk(
			chunk_id="",
			session_id=session_id,
			type="done",
			content="",
			agent_name=agent_name,
			is_end=True
		)
	else:
		# 回退到智能体的 process_message_stream
		logger.info(f"智能体 {agent.name} 不支持工作流，使用 process_message_stream")
		async for chunk in agent.process_message_stream(user_id, message, context):
			yield chunk

