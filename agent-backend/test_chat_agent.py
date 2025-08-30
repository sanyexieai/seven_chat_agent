#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ChatAgent类功能
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.chat_agent import ChatAgent, MemoryLevel, MemoryType

async def test_chat_agent():
    """测试ChatAgent的基本功能"""
    print("=== 测试ChatAgent类 ===\n")
    
    # 创建ChatAgent实例
    chat_agent = ChatAgent("智能助手", "一个具有分级知识库的智能聊天助手")
    
    print("1. 测试知识库初始化")
    knowledge_summary = chat_agent.get_knowledge_summary()
    print(f"知识库摘要: {knowledge_summary}\n")
    
    print("2. 测试添加知识")
    # 添加技能知识
    skill_id = chat_agent.add_knowledge(
        content="Python编程技能：能够编写和调试Python代码",
        memory_level=MemoryLevel.SKILL,
        category="programming",
        tags=["Python", "编程", "技能"]
    )
    print(f"添加技能知识，ID: {skill_id}")
    
    # 添加长期记忆
    long_term_id = chat_agent.add_knowledge(
        content="用户偏好：喜欢简洁明了的回答",
        memory_level=MemoryLevel.LONG_TERM,
        category="user_preference",
        tags=["用户偏好", "简洁"],
        memory_type=MemoryType.EFFECTIVE
    )
    print(f"添加长期记忆，ID: {long_term_id}")
    
    print("3. 测试知识检索")
    skills = chat_agent.get_knowledge(MemoryLevel.SKILL, category="programming")
    print(f"检索到的编程技能: {len(skills)} 项")
    for skill in skills:
        print(f"  - {skill.content}")
    
    print("\n4. 测试智能体节点管理")
    # 添加智能体节点
    chat_agent.add_agent_node("agent_001", "规划专家", "planner", ["任务分解", "流程设计"])
    chat_agent.add_agent_node("agent_002", "执行专家", "executor", ["代码执行", "结果验证"])
    chat_agent.add_agent_node("agent_003", "分析专家", "analyzer", ["数据分析", "报告生成"])
    
    # 添加关系
    chat_agent.add_relationship("agent_001", "agent_002", 0.8, "plan_execute")
    chat_agent.add_relationship("agent_002", "agent_003", 0.6, "execute_analyze")
    chat_agent.add_relationship("agent_001", "agent_003", 0.7, "plan_analyze")
    
    print("智能体网络摘要:")
    network_summary = chat_agent.get_agent_network_summary()
    print(f"  总智能体数: {network_summary['total_agents']}")
    print(f"  总关系数: {network_summary['total_relationships']}")
    
    print("\n5. 测试注意力分数计算")
    for agent_id in ["agent_001", "agent_002", "agent_003"]:
        score = chat_agent.calculate_attention_score(agent_id)
        print(f"  {agent_id} 注意力分数: {score:.3f}")
    
    print("\n6. 测试发言顺序确定")
    session_agents = ["agent_001", "agent_002", "agent_003"]
    speaking_order = chat_agent.determine_speaking_order(session_agents)
    print(f"发言顺序: {speaking_order}")
    
    print("\n7. 测试关系响应判断")
    should_respond = chat_agent.should_respond_to_agent("agent_002", "agent_001")
    print(f"agent_002 是否应该回复 agent_001: {should_respond}")
    
    print("\n8. 测试消息处理")
    user_message = "请帮我分析一下这个Python代码的性能问题"
    response = await chat_agent.process_message("user_123", user_message)
    print(f"用户消息: {user_message}")
    print(f"智能体回复: {response.content}")
    
    print("\n9. 测试记忆整理")
    # 添加大量短期记忆来触发整理
    for i in range(110):
        chat_agent.add_knowledge(
            content=f"测试短期记忆项 {i}",
            memory_level=MemoryLevel.SHORT_TERM,
            category="test",
            tags=["测试", "短期记忆"]
        )
    
    print("添加短期记忆后:")
    knowledge_summary = chat_agent.get_knowledge_summary()
    print(f"  短期记忆数量: {knowledge_summary[MemoryLevel.SHORT_TERM]}")
    print(f"  长期记忆有效数量: {knowledge_summary[MemoryLevel.LONG_TERM]['effective']}")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    # 在Windows环境下运行
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    asyncio.run(test_chat_agent()) 