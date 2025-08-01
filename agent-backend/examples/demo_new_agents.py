#!/usr/bin/env python3
"""
新智能体类型演示脚本
展示提示词驱动和工具驱动智能体的功能
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.prompt_driven_agent import PromptDrivenAgent
from agents.tool_driven_agent import ToolDrivenAgent
from utils.log_helper import get_logger

logger = get_logger("agent_demo")

async def demo_prompt_driven_agents():
    """演示提示词驱动智能体"""
    print("\n=== 提示词驱动智能体演示 ===")
    
    # 创建不同角色的提示词驱动智能体
    agents = {
        "翻译助手": PromptDrivenAgent(
            "translator", 
            "翻译助手", 
            "你是一个专业的翻译助手。请将用户输入的内容翻译成中文，保持原文的意思和风格。"
        ),
        "代码助手": PromptDrivenAgent(
            "coder", 
            "代码助手", 
            "你是一个专业的程序员助手。请帮助用户编写、调试和优化代码。提供清晰的代码示例和解释。"
        ),
        "写作助手": PromptDrivenAgent(
            "writer", 
            "写作助手", 
            "你是一个专业的写作助手。请帮助用户改进写作，提供创意建议，并确保内容的逻辑性和可读性。"
        )
    }
    
    # 测试消息
    test_messages = {
        "翻译助手": "Hello, how are you today?",
        "代码助手": "请帮我写一个Python函数来计算斐波那契数列",
        "写作助手": "请帮我写一篇关于人工智能的文章开头"
    }
    
    for agent_name, agent in agents.items():
        print(f"\n--- {agent_name} ---")
        message = test_messages[agent_name]
        print(f"用户输入: {message}")
        
        try:
            response = await agent.process_message("demo_user", message)
            print(f"智能体回复: {response.content}")
        except Exception as e:
            print(f"错误: {str(e)}")

async def demo_tool_driven_agents():
    """演示工具驱动智能体"""
    print("\n=== 工具驱动智能体演示 ===")
    
    # 创建工具驱动智能体（绑定不同的工具）
    search_agent = ToolDrivenAgent(
        "search_assistant", 
        "搜索助手", 
        ["search", "news_search"]  # 绑定搜索相关工具
    )
    
    # 初始化工具信息（模拟）
    search_agent.tool_info = {
        "search": {
            "name": "search",
            "display_name": "网络搜索",
            "description": "在互联网上搜索信息",
            "input_schema": {
                "query": {"type": "string", "description": "搜索查询"},
                "max_results": {"type": "integer", "description": "最大结果数"}
            },
            "examples": [
                {"query": "Python教程", "max_results": 5},
                {"query": "人工智能最新发展", "max_results": 10}
            ]
        },
        "news_search": {
            "name": "news_search",
            "display_name": "新闻搜索",
            "description": "搜索最新新闻",
            "input_schema": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最大结果数"}
            },
            "examples": [
                {"query": "AI新闻", "max_results": 5},
                {"query": "科技动态", "max_results": 10}
            ]
        }
    }
    
    print("\n--- 搜索助手 ---")
    test_message = "请帮我搜索关于机器学习的信息"
    print(f"用户输入: {test_message}")
    
    try:
        # 生成系统提示词
        system_prompt = search_agent.generate_system_prompt()
        print(f"\n生成的系统提示词:\n{system_prompt}")
        
        # 模拟处理消息
        response = await search_agent.process_message("demo_user", test_message)
        print(f"\n智能体回复: {response.content}")
    except Exception as e:
        print(f"错误: {str(e)}")

async def demo_agent_comparison():
    """比较不同智能体类型的差异"""
    print("\n=== 智能体类型比较 ===")
    
    # 创建相同任务的智能体
    prompt_agent = PromptDrivenAgent(
        "prompt_math", 
        "数学助手", 
        "你是一个数学老师。请帮助用户解决数学问题，提供详细的解题步骤和解释。"
    )
    
    tool_agent = ToolDrivenAgent(
        "tool_math", 
        "数学工具助手", 
        ["calculator", "equation_solver"]  # 绑定数学工具
    )
    
    # 模拟工具信息
    tool_agent.tool_info = {
        "calculator": {
            "name": "calculator",
            "display_name": "计算器",
            "description": "执行基本数学计算",
            "input_schema": {
                "expression": {"type": "string", "description": "数学表达式"}
            }
        },
        "equation_solver": {
            "name": "equation_solver",
            "display_name": "方程求解器",
            "description": "求解数学方程",
            "input_schema": {
                "equation": {"type": "string", "description": "方程"}
            }
        }
    }
    
    test_message = "请帮我计算 15 * 23 + 7"
    print(f"测试消息: {test_message}")
    
    print("\n--- 提示词驱动智能体 ---")
    try:
        response1 = await prompt_agent.process_message("demo_user", test_message)
        print(f"回复: {response1.content}")
    except Exception as e:
        print(f"错误: {str(e)}")
    
    print("\n--- 工具驱动智能体 ---")
    try:
        response2 = await tool_agent.process_message("demo_user", test_message)
        print(f"回复: {response2.content}")
    except Exception as e:
        print(f"错误: {str(e)}")

async def main():
    """主函数"""
    print("新智能体类型演示")
    print("=" * 50)
    
    try:
        # 演示纯提示词驱动智能体
        await demo_prompt_driven_agents()
        
        # 演示纯工具驱动智能体
        await demo_tool_driven_agents()
        
        # 比较不同智能体类型
        await demo_agent_comparison()
        
        print("\n演示完成！")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {str(e)}")
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 