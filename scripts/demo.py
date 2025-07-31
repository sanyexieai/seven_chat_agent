#!/usr/bin/env python3
"""
AI Agent System 演示脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_backend.agents.chat_agent import ChatAgent
from agent_backend.agents.search_agent import SearchAgent
from agent_backend.agents.report_agent import ReportAgent
from agent_backend.tools.search_tools import WebSearchTool, DocumentSearchTool
from agent_backend.tools.report_tools import DataAnalysisTool, ReportGeneratorTool

async def demo_chat_agent():
    """演示聊天智能体"""
    print("🤖 演示聊天智能体")
    print("=" * 50)
    
    agent = ChatAgent("demo_chat_agent", "演示聊天智能体")
    
    messages = [
        "你好",
        "请介绍一下人工智能",
        "谢谢你的帮助",
        "再见"
    ]
    
    for message in messages:
        print(f"用户: {message}")
        response = await agent.process_message("demo_user", message)
        print(f"智能体: {response.content}")
        print("-" * 30)

async def demo_search_agent():
    """演示搜索智能体"""
    print("\n🔍 演示搜索智能体")
    print("=" * 50)
    
    agent = SearchAgent("demo_search_agent", "演示搜索智能体")
    
    queries = [
        "搜索Python编程教程",
        "查找机器学习资料",
        "搜索最新的AI技术发展"
    ]
    
    for query in queries:
        print(f"查询: {query}")
        response = await agent.process_message("demo_user", query)
        print(f"搜索结果: {response.content}")
        print("-" * 30)

async def demo_report_agent():
    """演示报告智能体"""
    print("\n📊 演示报告智能体")
    print("=" * 50)
    
    agent = ReportAgent("demo_report_agent", "演示报告智能体")
    
    requests = [
        "生成关于人工智能发展趋势的报告",
        "分析Python编程语言的优势",
        "总结机器学习的主要应用领域"
    ]
    
    for request in requests:
        print(f"请求: {request}")
        response = await agent.process_message("demo_user", request)
        print(f"报告: {response.content}")
        print("-" * 30)

async def demo_tools():
    """演示工具功能"""
    print("\n🛠️  演示工具功能")
    print("=" * 50)
    
    # 演示搜索工具
    web_search = WebSearchTool()
    doc_search = DocumentSearchTool()
    
    print("网络搜索工具:")
    result = await web_search.execute({
        "query": "人工智能发展",
        "keywords": ["AI", "发展"]
    })
    print(f"结果: {result}")
    print("-" * 30)
    
    print("文档搜索工具:")
    result = await doc_search.execute({
        "query": "Python编程",
        "keywords": ["Python", "编程"]
    })
    print(f"结果: {result}")
    print("-" * 30)
    
    # 演示报告工具
    data_analysis = DataAnalysisTool()
    report_generator = ReportGeneratorTool()
    
    print("数据分析工具:")
    result = await data_analysis.execute({
        "topic": "机器学习",
        "type": "general"
    })
    print(f"分析结果: {result}")
    print("-" * 30)
    
    print("报告生成工具:")
    requirements = {
        "topic": "深度学习",
        "type": "analysis",
        "sections": ["摘要", "背景", "内容", "结论"]
    }
    data = {"analysis_results": result}
    
    result = await report_generator.execute({
        "requirements": requirements,
        "data": data
    })
    print(f"生成的报告: {result}")

async def main():
    """主演示函数"""
    print("🎉 AI Agent System 演示")
    print("=" * 60)
    print("本演示将展示系统的各种功能")
    print("=" * 60)
    
    try:
        # 演示各种智能体
        await demo_chat_agent()
        await demo_search_agent()
        await demo_report_agent()
        
        # 演示工具功能
        await demo_tools()
        
        print("\n✅ 演示完成!")
        print("=" * 60)
        print("🎯 主要功能:")
        print("  • 多智能体协作")
        print("  • 智能体自动选择")
        print("  • 工具集成")
        print("  • 流式响应")
        print("  • 报告生成")
        print("  • 搜索功能")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 