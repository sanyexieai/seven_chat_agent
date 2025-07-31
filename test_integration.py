#!/usr/bin/env python3
"""
集成测试脚本
"""

import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from agent_backend.agents.agent_manager import AgentManager
    from agent_backend.models.chat_models import ChatRequest
    from agent_backend.utils.logger import logger
except ImportError:
    # 尝试直接导入
    sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent-backend'))
    from agents.agent_manager import AgentManager
    from models.chat_models import ChatRequest
    from agent_backend.utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("test_integration")

async def test_integration():
    """集成测试"""
    print("🧪 开始集成测试...")
    
    try:
        # 1. 测试日志系统
        print("\n1. 测试日志系统...")
        logger.info("测试日志系统 - INFO级别")
        logger.warning("测试日志系统 - WARNING级别")
        logger.error("测试日志系统 - ERROR级别")
        print("✅ 日志系统正常")
        
        # 2. 测试智能体管理器
        print("\n2. 测试智能体管理器...")
        agent_manager = AgentManager()
        await agent_manager.initialize()
        print(f"✅ 智能体管理器初始化成功，共 {len(agent_manager.agents)} 个智能体")
        
        # 3. 测试聊天智能体
        print("\n3. 测试聊天智能体...")
        chat_request = ChatRequest(
            user_id="test_user_123",
            message="你好，请介绍一下你自己",
            context={},
            agent_type="chat"
        )
        
        response = await agent_manager.process_message(
            user_id=chat_request.user_id,
            message=chat_request.message,
            context=chat_request.context
        )
        
        print(f"✅ 聊天智能体测试成功")
        print(f"📝 用户消息: {chat_request.message}")
        print(f"🤖 AI回复: {response.content[:100]}...")
        
        # 4. 测试搜索智能体
        print("\n4. 测试搜索智能体...")
        search_request = ChatRequest(
            user_id="test_user_123",
            message="搜索人工智能的最新发展",
            context={},
            agent_type="search"
        )
        
        search_response = await agent_manager.process_message(
            user_id=search_request.user_id,
            message=search_request.message,
            context=search_request.context
        )
        
        print(f"✅ 搜索智能体测试成功")
        print(f"📝 用户消息: {search_request.message}")
        print(f"🔍 搜索回复: {search_response.content[:100]}...")
        
        # 5. 测试工具系统
        print("\n5. 测试工具系统...")
        available_tools = agent_manager.get_available_agents()
        print(f"✅ 工具系统正常，可用工具: {len(available_tools)} 个")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {str(e)}")
        logger.error(f"集成测试失败: {str(e)}")
        return False

async def main():
    """主函数"""
    print("🚀 AI Agent System 集成测试")
    print("=" * 50)
    
    success = await test_integration()
    
    if success:
        print("\n🎉 所有集成测试通过!")
        print("✅ 系统功能正常")
        print("📝 下一步:")
        print("  1. 启动后端: python agent-backend/main.py")
        print("  2. 启动前端: cd agent-ui && npm start")
        print("  3. 访问应用: http://localhost:3000")
    else:
        print("\n❌ 集成测试失败")
        print("请检查错误信息并修复问题")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 