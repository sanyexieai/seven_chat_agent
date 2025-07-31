#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from database.database import SessionLocal
from models.database_models import Message, UserSession, Agent

def check_database():
    db = SessionLocal()
    try:
        # 检查消息
        messages = db.query(Message).all()
        print(f"总消息数: {len(messages)}")
        
        for i, msg in enumerate(messages[:10]):  # 只显示前10条
            print(f"消息 {i+1}:")
            print(f"  ID: {msg.id}")
            print(f"  类型: {msg.type}")
            print(f"  会话ID: {msg.session_id}")
            print(f"  内容长度: {len(msg.content)}")
            print(f"  内容: {msg.content[:200]}...")
            print(f"  时间: {msg.timestamp}")
            print("---")
        
        # 检查会话
        sessions = db.query(UserSession).all()
        print(f"\n总会话数: {len(sessions)}")
        
        for session in sessions:
            print(f"会话ID: {session.id}, 名称: {session.name}, 智能体: {session.agent_id}")
        
        # 检查智能体
        agents = db.query(Agent).all()
        print(f"\n总智能体数: {len(agents)}")
        
        for agent in agents:
            print(f"智能体: {agent.name}, 显示名: {agent.display_name}, 激活: {agent.is_active}")
            
    finally:
        db.close()

if __name__ == "__main__":
    check_database() 