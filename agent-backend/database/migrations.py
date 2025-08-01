"""
数据库迁移管理器
自动检查和执行数据库迁移
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from database.database import engine, SessionLocal
from models.database_models import Base
from utils.log_helper import get_logger

logger = get_logger("migrations")

def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def check_column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)

def run_migrations():
    """运行所有数据库迁移"""
    logger.info("开始检查数据库迁移...")
    
    try:
        # 检查agents表是否存在
        if not check_table_exists('agents'):
            logger.info("agents表不存在，创建表...")
            Base.metadata.create_all(bind=engine)
            logger.info("agents表创建完成")
            return
        
        # 检查新字段是否存在
        missing_columns = []
        
        if not check_column_exists('agents', 'system_prompt'):
            missing_columns.append('system_prompt')
        
        if not check_column_exists('agents', 'bound_tools'):
            missing_columns.append('bound_tools')
        
        if not check_column_exists('agents', 'flow_config'):
            missing_columns.append('flow_config')
        
        if missing_columns:
            logger.info(f"发现缺失字段: {missing_columns}")
            
            with engine.connect() as conn:
                # 添加缺失的字段
                for column in missing_columns:
                    if column == 'system_prompt':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN system_prompt TEXT;"))
                        logger.info("添加 system_prompt 字段")
                    elif column == 'bound_tools':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN bound_tools JSON;"))
                        logger.info("添加 bound_tools 字段")
                    elif column == 'flow_config':
                        conn.execute(text("ALTER TABLE agents ADD COLUMN flow_config JSON;"))
                        logger.info("添加 flow_config 字段")
                
                conn.commit()
                logger.info("数据库迁移完成")
        else:
            logger.info("数据库结构已是最新版本")
            
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}")
        raise

def create_default_agents():
    """创建默认智能体"""
    logger.info("检查默认智能体...")
    
    db = SessionLocal()
    try:
        from models.database_models import Agent
        
        # 检查是否已有智能体
        existing_agents = db.query(Agent).count()
        if existing_agents > 0:
            logger.info(f"数据库中已有 {existing_agents} 个智能体，跳过创建默认智能体")
            return
        
        # 创建默认智能体
        default_agents = [
            {
                "name": "chat_agent",
                "display_name": "通用聊天智能体",
                "description": "基础的聊天对话智能体",
                "agent_type": "chat",
                "is_active": True
            },
            {
                "name": "search_agent", 
                "display_name": "搜索智能体",
                "description": "搜索和信息检索智能体",
                "agent_type": "search",
                "is_active": True
            },
            {
                "name": "report_agent",
                "display_name": "报告智能体", 
                "description": "报告生成智能体",
                "agent_type": "report",
                "is_active": True
            },
            {
                "name": "prompt_agent",
                "display_name": "提示词驱动智能体",
                "description": "纯提示词驱动的智能体",
                "agent_type": "prompt_driven",
                "system_prompt": "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。请用简洁、准确、友好的方式回应用户的问题。",
                "is_active": True
            },
            {
                "name": "tool_agent",
                "display_name": "工具驱动智能体",
                "description": "纯工具驱动的智能体",
                "agent_type": "tool_driven",
                "bound_tools": ["search", "news_search"],
                "is_active": True
            }
        ]
        
        for agent_data in default_agents:
            agent = Agent(**agent_data)
            db.add(agent)
        
        db.commit()
        logger.info(f"创建了 {len(default_agents)} 个默认智能体")
        
    except Exception as e:
        logger.error(f"创建默认智能体失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def init_database():
    """初始化数据库"""
    logger.info("开始初始化数据库...")
    
    # 运行迁移
    run_migrations()
    
    # 创建默认智能体
    create_default_agents()
    
    logger.info("数据库初始化完成")

if __name__ == "__main__":
    init_database() 