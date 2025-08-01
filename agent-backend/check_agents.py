#!/usr/bin/env python3
"""
检查当前加载的智能体
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal
from models.database_models import Agent
from utils.log_helper import get_logger

logger = get_logger("check_agents")

def check_db_agents():
    """检查数据库中的智能体"""
    db = SessionLocal()
    try:
        agents = db.query(Agent).all()
        print(f"数据库中共有 {len(agents)} 个智能体:")
        
        for agent in agents:
            print(f"\n智能体: {agent.name}")
            print(f"  显示名称: {agent.display_name}")
            print(f"  类型: {agent.agent_type}")
            print(f"  是否激活: {agent.is_active}")
            print(f"  系统提示词: {agent.system_prompt}")
            print(f"  绑定工具: {agent.bound_tools}")
            print(f"  流程图配置: {agent.flow_config}")
            
    except Exception as e:
        print(f"检查数据库失败: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    check_db_agents() 