#!/usr/bin/env python3
"""
创建测试智能体数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal
from models.database_models import Agent
from utils.log_helper import get_logger

logger = get_logger("create_test_agents")

def create_test_agents():
    """创建测试智能体"""
    db = SessionLocal()
    try:
        # 检查是否已有智能体
        existing_count = db.query(Agent).count()
        if existing_count > 0:
            print(f"数据库中已有 {existing_count} 个智能体，跳过创建")
            return
        
        # 创建测试智能体
        test_agents = [
            {
                "name": "translator_agent",
                "display_name": "翻译助手",
                "description": "专业的翻译助手，支持中英文翻译",
                "agent_type": "prompt_driven",
                "system_prompt": "你是一个专业的翻译助手。请将用户输入的内容翻译成中文，保持原文的意思和风格。如果用户输入的是中文，请翻译成英文。",
                "is_active": True
            },
            {
                "name": "coder_agent", 
                "display_name": "代码助手",
                "description": "专业的程序员助手，帮助编写和调试代码",
                "agent_type": "prompt_driven",
                "system_prompt": "你是一个专业的程序员助手。请帮助用户编写、调试和优化代码。提供清晰的代码示例和解释。支持多种编程语言。",
                "is_active": True
            },
            {
                "name": "writer_agent",
                "display_name": "写作助手", 
                "description": "专业的写作助手，帮助改进写作和提供创意",
                "agent_type": "prompt_driven",
                "system_prompt": "你是一个专业的写作助手。请帮助用户改进写作，提供创意建议，并确保内容的逻辑性和可读性。",
                "is_active": True
            },
            {
                "name": "search_agent",
                "display_name": "搜索助手",
                "description": "搜索和信息检索助手",
                "agent_type": "tool_driven",
                "bound_tools": ["search", "news_search"],
                "is_active": True
            }
        ]
        
        for agent_data in test_agents:
            agent = Agent(**agent_data)
            db.add(agent)
            print(f"创建智能体: {agent_data['name']} - {agent_data['display_name']}")
        
        db.commit()
        print(f"成功创建 {len(test_agents)} 个测试智能体")
        
    except Exception as e:
        print(f"创建测试智能体失败: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_agents() 