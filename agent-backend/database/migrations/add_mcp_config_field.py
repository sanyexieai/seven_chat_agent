"""
数据库迁移脚本：为MCPServer表添加config字段
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text, inspect
from database.database import engine
from utils.log_helper import get_logger

logger = get_logger("mcp_migration")

def check_column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return False
    columns = inspector.get_columns(table_name)
    return any(col['name'] == column_name for col in columns)

def upgrade():
    """升级数据库结构"""
    logger.info("开始检查MCP服务器表结构...")
    
    try:
        with engine.connect() as conn:
            # 检查mcp_servers表是否存在
            inspector = inspect(engine)
            if 'mcp_servers' not in inspector.get_table_names():
                logger.info("mcp_servers表不存在，创建表...")
                from models.database_models import Base
                Base.metadata.create_all(bind=engine)
                logger.info("mcp_servers表创建完成")
                return
            
            # 检查config字段是否存在
            if not check_column_exists('mcp_servers', 'config'):
                logger.info("添加config字段到mcp_servers表...")
                conn.execute(text("""
                    ALTER TABLE mcp_servers 
                    ADD COLUMN config JSON;
                """))
                conn.commit()
                logger.info("成功添加config字段到mcp_servers表")
            else:
                logger.info("config字段已存在，跳过添加")
            
            # 检查其他可能缺失的字段
            missing_columns = []
            
            if not check_column_exists('mcp_servers', 'args'):
                missing_columns.append('args')
            
            if not check_column_exists('mcp_servers', 'env'):
                missing_columns.append('env')
            
            if missing_columns:
                logger.info(f"发现缺失字段: {missing_columns}")
                for column in missing_columns:
                    if column == 'args':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN args JSON;"))
                        logger.info("添加 args 字段")
                    elif column == 'env':
                        conn.execute(text("ALTER TABLE mcp_servers ADD COLUMN env JSON;"))
                        logger.info("添加 env 字段")
                
                conn.commit()
                logger.info("MCP服务器表迁移完成")
            else:
                logger.info("MCP服务器表结构已是最新版本")
                
    except Exception as e:
        logger.error(f"MCP服务器表迁移失败: {str(e)}")
        raise

def downgrade():
    """回滚数据库结构"""
    logger.info("开始回滚MCP服务器表结构...")
    
    try:
        with engine.connect() as conn:
            # 删除config字段
            if check_column_exists('mcp_servers', 'config'):
                conn.execute(text("ALTER TABLE mcp_servers DROP COLUMN config;"))
                logger.info("删除config字段")
            
            # 删除其他可能添加的字段
            if check_column_exists('mcp_servers', 'args'):
                conn.execute(text("ALTER TABLE mcp_servers DROP COLUMN args;"))
                logger.info("删除args字段")
            
            if check_column_exists('mcp_servers', 'env'):
                conn.execute(text("ALTER TABLE mcp_servers DROP COLUMN env;"))
                logger.info("删除env字段")
            
            conn.commit()
            logger.info("MCP服务器表回滚完成")
            
    except Exception as e:
        logger.error(f"MCP服务器表回滚失败: {str(e)}")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade() 