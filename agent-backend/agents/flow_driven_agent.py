from typing import Dict, Any, AsyncGenerator, List, Optional
from agents.base_agent import BaseAgent
from models.chat_models import AgentMessage, StreamChunk, MessageType, AgentContext
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
import asyncio
import json
import uuid
from enum import Enum

logger = get_logger("flow_driven_agent")

class NodeType(str, Enum):
    """节点类型枚举"""
    AGENT = "agent"           # 智能体节点
    CONDITION = "condition"    # 条件节点
    ACTION = "action"         # 动作节点
    INPUT = "input"           # 输入节点
    OUTPUT = "output"         # 输出节点

class FlowNode:
    """流程图节点"""
    def __init__(self, node_id: str, node_type: NodeType, name: str, config: Dict[str, Any] = None):
        self.id = node_id
        self.type = node_type
        self.name = name
        self.config = config or {}
        self.position = self.config.get('position', {'x': 0, 'y': 0})
        self.connections = self.config.get('connections', [])  # 连接到的其他节点ID列表

class FlowDrivenAgent(BaseAgent):
    """流程图驱动智能体
    
    通过在线编辑流程图的形式，将其他基础智能体作为节点创建复杂的多智能体组合。
    支持条件分支、循环、并行执行等复杂的流程控制。
    """
    
    def __init__(self, name: str, description: str, flow_config: Dict[str, Any] = None):
        super().__init__(name, description)
        
        # 流程图配置
        self.flow_config = flow_config or {}
        self.nodes = {}  # 节点字典 {node_id: FlowNode}
        self.start_node_id = None  # 起始节点ID
        
        # 初始化LLM助手
        try:
            self.llm_helper = get_llm_helper()
            logger.info(f"流程图驱动智能体 {name} 初始化成功")
        except Exception as e:
            logger.error(f"LLM初始化失败: {str(e)}")
            raise
        
        # 加载流程图配置
        self._load_flow_config()
        logger.info(f"流程图驱动智能体 {name} 初始化完成")
    
    def _load_flow_config(self):
        """加载流程图配置"""
        try:
            if not self.flow_config:
                logger.warning("流程图配置为空")
                return
            
            # 解析节点配置
            nodes_config = self.flow_config.get('nodes', [])
            for node_config in nodes_config:
                node_id = node_config.get('id')
                node_type = NodeType(node_config.get('type', 'agent'))
                node_name = node_config.get('name', '')
                
                node = FlowNode(node_id, node_type, node_name, node_config)
                self.nodes[node_id] = node
                
                # 如果是起始节点
                if node_config.get('isStart', False):
                    self.start_node_id = node_id
            
            logger.info(f"加载了 {len(self.nodes)} 个流程图节点")
            logger.info(f"起始节点: {self.start_node_id}")
            
        except Exception as e:
            logger.error(f"加载流程图配置失败: {str(e)}")
    
    def set_flow_config(self, config: Dict[str, Any]):
        """设置流程图配置"""
        self.flow_config = config
        self._load_flow_config()
        logger.info(f"智能体 {self.name} 流程图配置已更新")
    
    def get_flow_config(self) -> Dict[str, Any]:
        """获取流程图配置"""
        return self.flow_config
    
    def add_node(self, node_id: str, node_type: NodeType, name: str, config: Dict[str, Any] = None):
        """添加节点"""
        node = FlowNode(node_id, node_type, name, config)
        self.nodes[node_id] = node
        logger.info(f"添加节点: {node_id} ({node_type.value})")
    
    def remove_node(self, node_id: str):
        """删除节点"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            logger.info(f"删除节点: {node_id}")
    
    def connect_nodes(self, from_node_id: str, to_node_id: str):
        """连接节点"""
        if from_node_id in self.nodes and to_node_id in self.nodes:
            if to_node_id not in self.nodes[from_node_id].connections:
                self.nodes[from_node_id].connections.append(to_node_id)
                logger.info(f"连接节点: {from_node_id} -> {to_node_id}")
    
    async def execute_flow(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """执行流程图"""
        if not self.start_node_id:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content="流程图未配置起始节点，无法执行。",
                agent_name=self.name,
                metadata={'flow_executed': False, 'error': 'no_start_node'}
            )
        
        try:
            # 执行流程图
            result = await self._execute_node(self.start_node_id, user_id, message, context)
            return result
        except Exception as e:
            logger.error(f"执行流程图失败: {str(e)}")
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=f"执行流程图时发生错误: {str(e)}",
                agent_name=self.name,
                metadata={'flow_executed': False, 'error': str(e)}
            )
    
    async def _execute_node(self, node_id: str, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行单个节点"""
        if node_id not in self.nodes:
            raise ValueError(f"节点 {node_id} 不存在")
        
        node = self.nodes[node_id]
        logger.info(f"执行节点: {node_id} ({node.type.value})")
        
        try:
            if node.type == NodeType.AGENT:
                return await self._execute_agent_node(node, user_id, message, context)
            elif node.type == NodeType.CONDITION:
                return await self._execute_condition_node(node, user_id, message, context)
            elif node.type == NodeType.ACTION:
                return await self._execute_action_node(node, user_id, message, context)
            elif node.type == NodeType.INPUT:
                return await self._execute_input_node(node, user_id, message, context)
            elif node.type == NodeType.OUTPUT:
                return await self._execute_output_node(node, user_id, message, context)
            else:
                raise ValueError(f"不支持的节点类型: {node.type}")
        except Exception as e:
            logger.error(f"执行节点 {node_id} 失败: {str(e)}")
            raise
    
    async def _execute_agent_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行智能体节点"""
        agent_name = node.config.get('agent_name')
        if not agent_name:
            raise ValueError(f"智能体节点 {node.id} 未配置智能体名称")
        
        # 这里需要从AgentManager获取对应的智能体
        # 暂时使用LLM直接处理
        prompt = f"作为智能体 '{agent_name}'，请处理以下用户消息：\n{message}"
        
        try:
            response = await self.llm_helper.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )
            
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=response,
                agent_name=f"{self.name}->{agent_name}",
                metadata={'node_id': node.id, 'node_type': node.type.value, 'agent_name': agent_name}
            )
        except Exception as e:
            logger.error(f"执行智能体节点失败: {str(e)}")
            raise
    
    async def _execute_condition_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行条件节点"""
        condition = node.config.get('condition', '')
        if not condition:
            raise ValueError(f"条件节点 {node.id} 未配置条件")
        
        # 使用LLM判断条件
        prompt = f"判断以下条件是否成立：\n条件：{condition}\n用户消息：{message}\n请回答 'true' 或 'false'"
        
        try:
            response = await self.llm_helper.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                stream=False
            )
            
            # 解析结果
            is_true = 'true' in response.lower()
            
            # 根据条件选择下一个节点
            next_node_id = None
            if is_true and node.connections:
                next_node_id = node.connections[0]  # 第一个连接为true分支
            elif len(node.connections) > 1:
                next_node_id = node.connections[1]  # 第二个连接为false分支
            
            if next_node_id:
                return await self._execute_node(next_node_id, user_id, message, context)
            else:
                return AgentMessage(
                    message_id=str(uuid.uuid4()),
                    session_id=context.get('session_id', ''),
                    type=MessageType.AGENT,
                    content=f"条件判断结果：{is_true}，但未找到后续节点",
                    agent_name=self.name,
                    metadata={'node_id': node.id, 'node_type': node.type.value, 'condition_result': is_true}
                )
        except Exception as e:
            logger.error(f"执行条件节点失败: {str(e)}")
            raise
    
    async def _execute_action_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行动作节点"""
        action = node.config.get('action', '')
        if not action:
            raise ValueError(f"动作节点 {node.id} 未配置动作")
        
        # 执行动作（这里可以扩展为调用具体的工具或API）
        result = f"执行动作：{action}"
        
        # 如果有后续节点，继续执行
        if node.connections:
            next_node_id = node.connections[0]
            return await self._execute_node(next_node_id, user_id, message, context)
        else:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=result,
                agent_name=self.name,
                metadata={'node_id': node.id, 'node_type': node.type.value, 'action': action}
            )
    
    async def _execute_input_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行输入节点"""
        input_prompt = node.config.get('prompt', '请输入：')
        
        # 如果有后续节点，继续执行
        if node.connections:
            next_node_id = node.connections[0]
            return await self._execute_node(next_node_id, user_id, message, context)
        else:
            return AgentMessage(
                message_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=input_prompt,
                agent_name=self.name,
                metadata={'node_id': node.id, 'node_type': node.type.value}
            )
    
    async def _execute_output_node(self, node: FlowNode, user_id: str, message: str, context: Dict[str, Any]) -> AgentMessage:
        """执行输出节点"""
        output_template = node.config.get('template', '处理结果：{message}')
        output_content = output_template.format(message=message)
        
        return AgentMessage(
            message_id=str(uuid.uuid4()),
            session_id=context.get('session_id', ''),
            type=MessageType.AGENT,
            content=output_content,
            agent_name=self.name,
            metadata={'node_id': node.id, 'node_type': node.type.value}
        )
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        return await self.execute_flow(user_id, message, context)
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        try:
            result = await self.execute_flow(user_id, message, context)
            
            # 将结果转换为流式输出
            yield StreamChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=result.content,
                agent_name=result.agent_name,
                metadata=result.metadata,
                is_end=True
            )
        except Exception as e:
            logger.error(f"流式处理消息失败: {str(e)}")
            yield StreamChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=context.get('session_id', ''),
                type=MessageType.AGENT,
                content=f"处理消息时发生错误: {str(e)}",
                agent_name=self.name,
                metadata={'error': str(e)},
                is_end=True
            ) 