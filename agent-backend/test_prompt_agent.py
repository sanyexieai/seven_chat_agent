#!/usr/bin/env python3
"""
测试提示词驱动智能体
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.agent_manager import AgentManager
from utils.log_helper import get_logger

logger = get_logger("test_prompt_agent")

async def test_prompt_agents():
    """测试提示词驱动智能体"""
    try:
        # 初始化智能体管理器
        agent_manager = AgentManager()
        await agent_manager.initialize()
        
        print("=== 测试提示词驱动智能体 ===")
        print(f"可用智能体: {list(agent_manager.agents.keys())}")
        
        # 测试消息
        test_messages = [
            "你好，请帮我翻译一下这句话：Hello, how are you?",
            "请帮我写一个Python函数来计算斐波那契数列",
            "请帮我写一篇关于人工智能的文章"
        ]
        
        for i, message in enumerate(test_messages, 1):
            print(f"\n--- 测试 {i}: {message} ---")
            
            # 处理消息
            response = await agent_manager.process_message("test_user", message)
            
            print(f"智能体: {response.agent_name}")
            print(f"响应: {response.content}")
            print(f"消息类型: {response.type}")
            
    except Exception as e:
        print(f"测试失败: {str(e)}")
        logger.error(f"测试失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_prompt_agents()) 