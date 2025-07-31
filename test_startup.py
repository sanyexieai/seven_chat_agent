#!/usr/bin/env python3
"""
测试项目启动
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """测试导入"""
    try:
        print("🔍 测试导入...")
        
        # 测试基础模块导入
        from agent_backend.models.chat_models import ChatRequest, ChatResponse
        print("✅ 数据模型导入成功")
        
        from agent_backend.utils.logger import logger
        print("✅ 日志模块导入成功")
        
        from agent_backend.agents.base_agent import BaseAgent
        print("✅ 基础智能体导入成功")
        
        from agent_backend.tools.base_tool import BaseTool
        print("✅ 基础工具导入成功")
        
        from agent_backend.agents.chat_agent import ChatAgent
        print("✅ 聊天智能体导入成功")
        
        from agent_backend.agents.search_agent import SearchAgent
        print("✅ 搜索智能体导入成功")
        
        from agent_backend.agents.report_agent import ReportAgent
        print("✅ 报告智能体导入成功")
        
        from agent_backend.tools.search_tools import WebSearchTool, DocumentSearchTool
        print("✅ 搜索工具导入成功")
        
        from agent_backend.tools.report_tools import DataAnalysisTool, ReportGeneratorTool
        print("✅ 报告工具导入成功")
        
        from agent_backend.tools.file_tools import FileReaderTool, FileWriterTool
        print("✅ 文件工具导入成功")
        
        from agent_backend.agents.agent_manager import AgentManager
        print("✅ 智能体管理器导入成功")
        
        from agent_backend.tools.tool_manager import ToolManager
        print("✅ 工具管理器导入成功")
        
        print("\n🎉 所有模块导入成功!")
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_agent_creation():
    """测试智能体创建"""
    try:
        print("\n🤖 测试智能体创建...")
        
        from agent_backend.agents.chat_agent import ChatAgent
        from agent_backend.agents.search_agent import SearchAgent
        from agent_backend.agents.report_agent import ReportAgent
        
        # 创建智能体实例
        chat_agent = ChatAgent("test_chat", "测试聊天智能体")
        search_agent = SearchAgent("test_search", "测试搜索智能体")
        report_agent = ReportAgent("test_report", "测试报告智能体")
        
        print("✅ 智能体创建成功")
        return True
        
    except Exception as e:
        print(f"❌ 智能体创建失败: {e}")
        return False

def test_tool_creation():
    """测试工具创建"""
    try:
        print("\n🛠️ 测试工具创建...")
        
        from agent_backend.tools.search_tools import WebSearchTool, DocumentSearchTool
        from agent_backend.tools.report_tools import DataAnalysisTool, ReportGeneratorTool
        from agent_backend.tools.file_tools import FileReaderTool, FileWriterTool
        
        # 创建工具实例
        web_search = WebSearchTool()
        doc_search = DocumentSearchTool()
        data_analysis = DataAnalysisTool()
        report_generator = ReportGeneratorTool()
        file_reader = FileReaderTool()
        file_writer = FileWriterTool()
        
        print("✅ 工具创建成功")
        return True
        
    except Exception as e:
        print(f"❌ 工具创建失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 AI Agent System 启动测试")
    print("=" * 50)
    
    # 测试导入
    if not test_imports():
        return False
    
    # 测试智能体创建
    if not test_agent_creation():
        return False
    
    # 测试工具创建
    if not test_tool_creation():
        return False
    
    print("\n🎉 所有测试通过!")
    print("=" * 50)
    print("✅ 项目可以正常启动")
    print("📝 下一步:")
    print("  1. 运行: python agent-backend/main.py")
    print("  2. 或使用: ./scripts/start.sh")
    print("  3. 或使用: docker-compose up -d")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 