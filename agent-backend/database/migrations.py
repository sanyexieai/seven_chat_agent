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
        # 检查所有必需的表是否存在
        required_tables = ['agents']
        missing_tables = []
        
        for table in required_tables:
            if not check_table_exists(table):
                missing_tables.append(table)
        
        if missing_tables:
            logger.info(f"发现缺失的表: {missing_tables}")
            logger.info("创建所有缺失的表...")
            Base.metadata.create_all(bind=engine)
            logger.info("所有表创建完成")
            return
        
        # 检查agents表的新字段是否存在
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
                logger.info("agents表迁移完成")
        else:
            logger.info("agents表结构已是最新版本")
        
        # 运行MCP服务器表迁移
        run_mcp_migrations()
        
        # 运行流程图表迁移
        run_flow_migrations()
        
        # 运行智能体LLM配置迁移
        run_agent_llm_config_migration()
            
    except Exception as e:
        logger.error(f"数据库迁移失败: {str(e)}")
        raise

def run_mcp_migrations():
    """运行MCP相关的数据库迁移"""
    logger.info("开始检查MCP相关表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查mcp_servers表是否存在
            inspector = inspect(engine)
            if 'mcp_servers' not in inspector.get_table_names():
                logger.info("mcp_servers表不存在，创建所有MCP表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有MCP表创建完成")
                return
            
            # 检查config字段是否存在
            if not check_column_exists('mcp_servers', 'config'):
                logger.info("添加config字段到mcp_servers表...")
                conn.execute(text("""
                    ALTER TABLE mcp_servers 
                    ADD COLUMN config JSON;
                """))
                logger.info("成功添加config字段到mcp_servers表")
            else:
                logger.info("config字段已存在，跳过添加")
            
            # 检查其他可能缺失的字段
            missing_server_columns = []
            
            if not check_column_exists('mcp_servers', 'args'):
                missing_server_columns.append('args')
            
            if not check_column_exists('mcp_servers', 'env'):
                missing_server_columns.append('env')
            
            if missing_server_columns:
                logger.info(f"发现缺失字段: {missing_server_columns}")
                for column in missing_server_columns:
                    if column == 'args':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN args JSON;"))
                        logger.info("添加 args 字段")
                    elif column == 'env':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN env JSON;"))
                        logger.info("添加 env 字段")
                
                logger.info("MCP服务器表迁移完成")
            else:
                logger.info("MCP服务器表结构已是最新版本")
            
            # 检查mcp_tools表
            if 'mcp_tools' not in inspector.get_table_names():
                logger.info("mcp_tools表不存在，创建所有MCP表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有MCP表创建完成")
            else:
                # 检查mcp_tools表的字段
                missing_tool_columns = []
                
                if not check_column_exists('mcp_tools', 'tool_type'):
                    missing_tool_columns.append('tool_type')
                if not check_column_exists('mcp_tools', 'input_schema'):
                    missing_tool_columns.append('input_schema')
                if not check_column_exists('mcp_tools', 'output_schema'):
                    missing_tool_columns.append('output_schema')
                if not check_column_exists('mcp_tools', 'examples'):
                    missing_tool_columns.append('examples')
                if not check_column_exists('mcp_tools', 'tool_schema'):
                    missing_tool_columns.append('tool_schema')
                
                if missing_tool_columns:
                    logger.info(f"发现缺失字段: {missing_tool_columns}")
                    for column in missing_tool_columns:
                        if column == 'tool_type':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_type VARCHAR(50);"))
                            logger.info("添加 tool_type 字段")
                        elif column == 'input_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN input_schema JSON;"))
                            logger.info("添加 input_schema 字段")
                        elif column == 'output_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN output_schema JSON;"))
                            logger.info("添加 output_schema 字段")
                        elif column == 'examples':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN examples JSON;"))
                            logger.info("添加 examples 字段")
                        elif column == 'tool_schema':
                            conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN tool_schema JSON;"))
                            logger.info("添加 tool_schema 字段")
                    
                    logger.info("MCP工具表迁移完成")
                else:
                    logger.info("MCP工具表结构已是最新版本")
            
            conn.commit()
                
    except Exception as e:
        logger.error(f"MCP相关表迁移失败: {str(e)}")
        raise

def run_flow_migrations():
    """运行流程图相关的数据库迁移"""
    logger.info("开始检查流程图表迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查flows表是否存在
            inspector = inspect(engine)
            if 'flows' not in inspector.get_table_names():
                logger.info("flows表不存在，创建所有流程图表...")
                Base.metadata.create_all(bind=engine)
                logger.info("所有流程图表创建完成")
                return
            
            # 检查flow_config字段是否存在
            if not check_column_exists('flows', 'flow_config'):
                logger.info("添加flow_config字段到flows表...")
                conn.execute(text("""
                    ALTER TABLE flows 
                    ADD COLUMN flow_config JSON;
                """))
                logger.info("成功添加flow_config字段到flows表")
            else:
                logger.info("flow_config字段已存在，跳过添加")
            
            # 检查其他可能缺失的字段
            missing_flow_columns = []
            
            if not check_column_exists('flows', 'name'):
                missing_flow_columns.append('name')
            
            if not check_column_exists('flows', 'description'):
                missing_flow_columns.append('description')
            
            if not check_column_exists('flows', 'nodes'):
                missing_flow_columns.append('nodes')
            
            if not check_column_exists('flows', 'edges'):
                missing_flow_columns.append('edges')
            
            if not check_column_exists('flows', 'flow_schema'):
                missing_flow_columns.append('flow_schema')
            
            if missing_flow_columns:
                logger.info(f"发现缺失字段: {missing_flow_columns}")
                for column in missing_flow_columns:
                    if column == 'name':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN name VARCHAR(255);"))
                        logger.info("添加 name 字段")
                    elif column == 'description':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN description TEXT;"))
                        logger.info("添加 description 字段")
                    elif column == 'nodes':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN nodes JSON;"))
                        logger.info("添加 nodes 字段")
                    elif column == 'edges':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN edges JSON;"))
                        logger.info("添加 edges 字段")
                    elif column == 'flow_schema':
                        conn.execute(text("ALTER TABLE flows ADD COLUMN flow_schema JSON;"))
                        logger.info("添加 flow_schema 字段")
                
                logger.info("流程图表迁移完成")
            else:
                logger.info("流程图表结构已是最新版本")
            
            conn.commit()
                
    except Exception as e:
        logger.error(f"流程图表迁移失败: {str(e)}")
        raise

def run_agent_llm_config_migration():
    """运行智能体LLM配置迁移"""
    logger.info("开始检查智能体LLM配置迁移...")
    
    try:
        with engine.connect() as conn:
            # 检查llm_config_id字段是否存在
            if not check_column_exists('agents', 'llm_config_id'):
                logger.info("添加llm_config_id字段到agents表...")
                conn.execute(text("""
                    ALTER TABLE agents 
                    ADD COLUMN llm_config_id INTEGER REFERENCES llm_configs(id);
                """))
                logger.info("成功添加llm_config_id字段到agents表")
            else:
                logger.info("llm_config_id字段已存在，跳过添加")
            
            conn.commit()
            logger.info("智能体LLM配置迁移完成")
                
    except Exception as e:
        logger.error(f"智能体LLM配置迁移失败: {str(e)}")
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
                "name": "general_agent",
                "display_name": "通用智能体",
                "description": "可配置提示词、工具和LLM的通用智能体",
                "agent_type": "general",
                "system_prompt": "你是一个智能AI助手，能够帮助用户解答问题、进行对话交流。请用简洁、准确、友好的方式回应用户的问题。",
                "is_active": True
            },
            {
                "name": "flow_agent",
                "display_name": "流程图智能体",
                "description": "可配置各种节点的流程图智能体",
                "agent_type": "flow_driven",
                "flow_config": {},
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
    
    # 创建默认LLM配置
    from database.database import create_default_llm_configs
    create_default_llm_configs()
    
    logger.info("数据库初始化完成")

if __name__ == "__main__":
    init_database() 