#!/usr/bin/env python3
"""
测试聊天功能
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent_backend.agents.agent_manager import AgentManager
from agent_backend.models.chat_models import ChatRequest

async def test_chat():
    """测试聊天功能"""
    print("🧪 测试聊天功能...")
    
    try:
        # 创建智能体管理器
        agent_manager = AgentManager()
        await agent_manager.initialize()
        
        # 创建测试请求
        request = ChatRequest(
            user_id="test_user_123",
            message="你好",
            context={},
            agent_type="chat"
        )
        
        # 处理消息
        response = await agent_manager.process_message(
            user_id=request.user_id,
            message=request.message,
            context=request.context
        )
        
        print(f"✅ 测试成功!")
        print(f"📝 用户消息: {request.message}")
        print(f"🤖 AI回复: {response.content}")
        print(f"⏰ 时间戳: {response.timestamp}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False

async def main():
    """主函数"""
    print("🚀 开始测试聊天功能")
    print("=" * 50)
    
    success = await test_chat()
    
    if success:
        print("\n🎉 所有测试通过!")
        print("✅ 聊天功能正常工作")
    else:
        print("\n❌ 测试失败")
        print("请检查错误信息并修复问题")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 