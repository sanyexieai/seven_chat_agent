from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, AsyncGenerator, Set
from models.chat_models import AgentMessage, AgentContext, ToolCall, StreamChunk
from tools.base_tool import BaseTool
import asyncio
import uuid
from datetime import datetime
from enum import Enum
import json
from pydantic import BaseModel

class MemoryLevel(str, Enum):
    """记忆级别枚举"""
    SHORT_TERM = "short_term"      # 短期记忆
    INSTINCT = "instinct"           # 本能
    SKILL = "skill"                 # 技能
    LONG_TERM = "long_term"         # 长期记忆

class MemoryType(str, Enum):
    """记忆类型枚举"""
    EFFECTIVE = "effective"         # 有效记忆
    RANDOM_THOUGHT = "random_thought"  # 胡思乱想

class KnowledgeItem(BaseModel):
    """知识项模型"""
    id: str
    content: str
    memory_level: MemoryLevel
    memory_type: Optional[MemoryType] = None
    category: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    usage_count: int = 0
    metadata: Dict[str, Any] = {}

class AgentNode:
    """智能体节点"""
    def __init__(self, agent_id: str, agent_name: str, agent_type: str, capabilities: List[str]):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.attention_score = 0.0
        self.last_activity = datetime.now()

class AgentRelationship:
    """智能体关系"""
    def __init__(self, from_agent: str, to_agent: str, weight: float, relationship_type: str):
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.weight = weight
        self.relationship_type = relationship_type
        self.last_interaction = datetime.now()

class ChatAgent(BaseAgent):
    """聊天智能体 - 实现分级知识库和节点沟通机制"""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        
        # 分级知识库
        self.knowledge_base = {
            MemoryLevel.SHORT_TERM: [],      # 短期记忆
            MemoryLevel.INSTINCT: [],        # 本能
            MemoryLevel.SKILL: [],           # 技能
            MemoryLevel.LONG_TERM: {         # 长期记忆
                MemoryType.EFFECTIVE: [],    # 有效记忆
                MemoryType.RANDOM_THOUGHT: [] # 胡思乱想
            }
        }
        
        # 智能体节点管理
        self.agent_nodes: Dict[str, AgentNode] = {}
        self.relationships: List[AgentRelationship] = []
        self.active_session_agents: Set[str] = set()
        
        # 配置参数
        self.max_short_term_memory = 100    # 短期记忆最大容量
        self.attention_threshold = 0.5      # 注意力阈值
        self.relationship_threshold = 0.3   # 关系权重阈值
        
        # 初始化本能知识
        self._initialize_instincts()
    
    def _initialize_instincts(self):
        """初始化本能知识"""
        instinct_rules = [
            {
                "content": "始终遵循用户指令，优先考虑用户需求",
                "category": "core_rule",
                "tags": ["用户优先", "指令遵循"]
            },
            {
                "content": "在不确定时主动询问用户澄清",
                "category": "communication",
                "tags": ["主动澄清", "用户交互"]
            },
            {
                "content": "保持对话的连贯性和上下文一致性",
                "category": "conversation",
                "tags": ["连贯性", "上下文"]
            }
        ]
        
        for rule in instinct_rules:
            self.add_knowledge(
                content=rule["content"],
                memory_level=MemoryLevel.INSTINCT,
                category=rule["category"],
                tags=rule["tags"]
            )
    
    def add_knowledge(self, content: str, memory_level: MemoryLevel, 
                     category: str, tags: List[str], memory_type: Optional[MemoryType] = None) -> str:
        """添加知识到指定级别"""
        knowledge_id = str(uuid.uuid4())
        knowledge_item = KnowledgeItem(
            id=knowledge_id,
            content=content,
            memory_level=memory_level,
            memory_type=memory_type,
            category=category,
            tags=tags,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        if memory_level == MemoryLevel.LONG_TERM:
            if memory_type:
                self.knowledge_base[memory_level][memory_type].append(knowledge_item)
            else:
                # 默认添加到有效记忆
                self.knowledge_base[memory_level][MemoryType.EFFECTIVE].append(knowledge_item)
        else:
            self.knowledge_base[memory_level].append(knowledge_item)
        
        return knowledge_id
    
    def get_knowledge(self, memory_level: MemoryLevel, category: str = None, 
                     tags: List[str] = None, limit: int = 10) -> List[KnowledgeItem]:
        """获取指定级别的知识"""
        if memory_level == MemoryLevel.LONG_TERM:
            # 合并两种类型的长期记忆
            all_long_term = (self.knowledge_base[memory_level][MemoryType.EFFECTIVE] + 
                           self.knowledge_base[memory_level][MemoryType.RANDOM_THOUGHT])
        else:
            all_long_term = self.knowledge_base[memory_level]
        
        # 过滤和排序
        filtered_knowledge = all_long_term
        
        if category:
            filtered_knowledge = [k for k in filtered_knowledge if k.category == category]
        
        if tags:
            filtered_knowledge = [k for k in filtered_knowledge if any(tag in k.tags for tag in tags)]
        
        # 按使用次数和更新时间排序
        filtered_knowledge.sort(key=lambda x: (x.usage_count, x.updated_at), reverse=True)
        
        return filtered_knowledge[:limit]
    
    def consolidate_memory(self):
        """整理记忆 - 将短期记忆整理到长期记忆"""
        short_term = self.knowledge_base[MemoryLevel.SHORT_TERM]
        if len(short_term) > self.max_short_term_memory:
            # 选择要保存到长期记忆的内容
            to_preserve = short_term[:self.max_short_term_memory // 2]
            
            for item in to_preserve:
                # 创建新的长期记忆项
                long_term_item = KnowledgeItem(
                    id=str(uuid.uuid4()),
                    content=item.content,
                    memory_level=MemoryLevel.LONG_TERM,
                    memory_type=MemoryType.EFFECTIVE,
                    category=item.category,
                    tags=item.tags,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    usage_count=item.usage_count + 1
                )
                
                self.knowledge_base[MemoryLevel.LONG_TERM][MemoryType.EFFECTIVE].append(long_term_item)
            
            # 清空短期记忆
            self.knowledge_base[MemoryLevel.SHORT_TERM] = []
    
    def add_agent_node(self, agent_id: str, agent_name: str, agent_type: str, capabilities: List[str]):
        """添加智能体节点"""
        agent_node = AgentNode(agent_id, agent_name, agent_type, capabilities)
        self.agent_nodes[agent_id] = agent_node
    
    def add_relationship(self, from_agent: str, to_agent: str, weight: float, relationship_type: str):
        """添加智能体关系"""
        relationship = AgentRelationship(from_agent, to_agent, weight, relationship_type)
        self.relationships.append(relationship)
    
    def get_agent_relationships(self, agent_id: str) -> List[AgentRelationship]:
        """获取指定智能体的关系"""
        return [r for r in self.relationships if r.from_agent == agent_id or r.to_agent == agent_id]
    
    def calculate_attention_score(self, agent_id: str) -> float:
        """计算智能体的注意力分数"""
        if agent_id not in self.agent_nodes:
            return 0.0
        
        agent = self.agent_nodes[agent_id]
        
        # 基于关系权重计算注意力
        relationships = self.get_agent_relationships(agent_id)
        relationship_score = sum(r.weight for r in relationships) / max(len(relationships), 1)
        
        # 基于最近活动计算时间衰减
        time_diff = (datetime.now() - agent.last_activity).total_seconds()
        time_decay = max(0, 1 - time_diff / 3600)  # 1小时内的衰减
        
        # 基于能力计算基础分数
        capability_score = len(agent.capabilities) / 10.0
        
        attention_score = (relationship_score * 0.4 + time_decay * 0.3 + capability_score * 0.3)
        agent.attention_score = attention_score
        
        return attention_score
    
    def determine_speaking_order(self, session_agents: List[str]) -> List[str]:
        """确定发言顺序"""
        # 计算所有参与智能体的注意力分数
        agent_scores = []
        for agent_id in session_agents:
            score = self.calculate_attention_score(agent_id)
            agent_scores.append((agent_id, score))
        
        # 按注意力分数排序
        agent_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [agent_id for agent_id, score in agent_scores if score >= self.attention_threshold]
    
    def should_respond_to_agent(self, current_agent: str, speaking_agent: str) -> bool:
        """判断是否应该回复指定智能体"""
        relationships = self.get_agent_relationships(current_agent)
        
        for rel in relationships:
            if (rel.from_agent == speaking_agent or rel.to_agent == speaking_agent) and rel.weight >= self.relationship_threshold:
                return True
        
        return False
    
    async def process_message(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AgentMessage:
        """处理用户消息"""
        # 将用户消息添加到短期记忆
        self.add_knowledge(
            content=f"用户消息: {message}",
            memory_level=MemoryLevel.SHORT_TERM,
            category="user_input",
            tags=["用户消息", "短期记忆"]
        )
        
        # 整理记忆
        self.consolidate_memory()
        
        # 基于知识库生成回复
        response_content = await self._generate_response(message, context)
        
        # 将回复添加到短期记忆
        self.add_knowledge(
            content=f"智能体回复: {response_content}",
            memory_level=MemoryLevel.SHORT_TERM,
            category="agent_response",
            tags=["智能体回复", "短期记忆"]
        )
        
        return self.create_message(response_content, "agent")
    
    async def process_message_stream(self, user_id: str, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """流式处理用户消息"""
        # 将用户消息添加到短期记忆
        self.add_knowledge(
            content=f"用户消息: {message}",
            memory_level=MemoryLevel.SHORT_TERM,
            category="user_input",
            tags=["用户消息", "短期记忆"]
        )
        
        # 整理记忆
        self.consolidate_memory()
        
        # 基于知识库生成流式回复
        async for chunk in self._generate_stream_response(message, context):
            yield chunk
        
        # 将完整回复添加到短期记忆
        self.add_knowledge(
            content=f"智能体流式回复完成",
            memory_level=MemoryLevel.SHORT_TERM,
            category="agent_response",
            tags=["智能体回复", "短期记忆", "流式"]
        )
    
    async def _generate_response(self, message: str, context: Dict[str, Any] = None) -> str:
        """生成回复内容"""
        # 从知识库中检索相关信息
        relevant_knowledge = []
        
        # 从短期记忆中检索
        short_term = self.get_knowledge(MemoryLevel.SHORT_TERM, limit=5)
        relevant_knowledge.extend(short_term)
        
        # 从本能中检索
        instincts = self.get_knowledge(MemoryLevel.INSTINCT, limit=3)
        relevant_knowledge.extend(instincts)
        
        # 从技能中检索
        skills = self.get_knowledge(MemoryLevel.SKILL, limit=5)
        relevant_knowledge.extend(skills)
        
        # 从长期记忆中检索
        long_term = self.get_knowledge(MemoryLevel.LONG_TERM, limit=3)
        relevant_knowledge.extend(long_term)
        
        # 基于检索到的知识生成回复
        response_parts = [f"基于我的知识库，我理解您的问题：{message}"]
        
        if relevant_knowledge:
            response_parts.append("\n相关背景信息：")
            for i, knowledge in enumerate(relevant_knowledge[:3], 1):
                response_parts.append(f"{i}. {knowledge.content}")
        
        response_parts.append("\n我会根据这些信息为您提供帮助。")
        
        return "\n".join(response_parts)
    
    async def _generate_stream_response(self, message: str, context: Dict[str, Any] = None) -> AsyncGenerator[StreamChunk, None]:
        """生成流式回复内容"""
        response_content = await self._generate_response(message, context)
        
        # 分段发送
        words = response_content.split()
        for i, word in enumerate(words):
            chunk = StreamChunk(
                chunk_id=str(uuid.uuid4()),
                session_id=context.get("session_id", "default") if context else "default",
                type="text",
                content=word + " ",
                agent_name=self.name,
                is_end=(i == len(words) - 1)
            )
            yield chunk
            await asyncio.sleep(0.1)  # 模拟流式效果
    
    def get_knowledge_summary(self) -> Dict[str, Any]:
        """获取知识库摘要"""
        summary = {}
        for level, content in self.knowledge_base.items():
            if level == MemoryLevel.LONG_TERM:
                summary[level] = {
                    "effective": len(content[MemoryType.EFFECTIVE]),
                    "random_thought": len(content[MemoryType.RANDOM_THOUGHT])
                }
            else:
                summary[level] = len(content)
        
        return summary
    
    def get_agent_network_summary(self) -> Dict[str, Any]:
        """获取智能体网络摘要"""
        return {
            "total_agents": len(self.agent_nodes),
            "total_relationships": len(self.relationships),
            "active_session_agents": len(self.active_session_agents),
            "agents": [
                {
                    "id": agent.agent_id,
                    "name": agent.agent_name,
                    "type": agent.agent_type,
                    "attention_score": agent.attention_score,
                    "capabilities": agent.capabilities
                }
                for agent in self.agent_nodes.values()
            ]
        } 