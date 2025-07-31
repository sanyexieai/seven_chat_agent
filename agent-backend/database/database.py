from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from typing import Generator
import os
from config.env import DATABASE_URL

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 使用database_models中的Base
from models.database_models import Base

def get_db() -> Generator[Session, None, None]:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """初始化数据库"""
    import os
    
    # 确保数据目录存在
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    # 导入所有模型以确保表被创建
    from models.database_models import Agent, UserSession, Message
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 创建默认智能体
    create_default_agents()

def create_default_agents():
    """创建默认智能体"""
    from models.database_models import Agent
    
    db = SessionLocal()
    try:
        # 检查是否已有智能体
        existing_agents = db.query(Agent).count()
        if existing_agents > 0:
            return
        
        # 创建默认智能体
        default_agents = [
            {
                "name": "chat_agent",
                "display_name": "通用聊天",
                "description": "通用聊天智能体，可以进行日常对话和问答",
                "agent_type": "chat",
                "config": {
                    "model": "qwen3:32b",
                    "temperature": 0.7,
                    "max_tokens": 2048
                }
            },
            {
                "name": "search_agent",
                "display_name": "搜索助手",
                "description": "搜索和信息检索智能体，可以搜索网络信息",
                "agent_type": "search",
                "config": {
                    "model": "qwen3:32b",
                    "temperature": 0.5,
                    "max_tokens": 2048,
                    "enable_web_search": True
                }
            },
            {
                "name": "report_agent",
                "display_name": "报告生成",
                "description": "报告生成智能体，可以生成各种类型的报告",
                "agent_type": "report",
                "config": {
                    "model": "qwen3:32b",
                    "temperature": 0.3,
                    "max_tokens": 4096,
                    "enable_analysis": True
                }
            }
        ]
        
        for agent_data in default_agents:
            agent = Agent(**agent_data)
            db.add(agent)
        
        db.commit()
        print("默认智能体创建完成")
        
    except Exception as e:
        db.rollback()
        print(f"创建默认智能体失败: {e}")
    finally:
        db.close() 