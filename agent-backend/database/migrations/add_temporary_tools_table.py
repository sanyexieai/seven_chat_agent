# -*- coding: utf-8 -*-
"""
添加临时工具表的迁移
"""
from sqlalchemy import text
from database.database import engine
from utils.log_helper import get_logger

logger = get_logger("migration_temporary_tools")


def upgrade():
    """创建临时工具表"""
    logger.info("开始创建临时工具表...")
    
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS temporary_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE,
        display_name VARCHAR(200) NOT NULL,
        description TEXT,
        code TEXT NOT NULL,
        input_schema JSON,
        output_schema JSON,
        examples JSON,
        is_active BOOLEAN DEFAULT 1,
        is_temporary BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    create_index_sql = """
    CREATE INDEX IF NOT EXISTS idx_temporary_tools_name ON temporary_tools(name);
    CREATE INDEX IF NOT EXISTS idx_temporary_tools_active ON temporary_tools(is_active);
    """
    
    try:
        with engine.connect() as conn:
            conn.execute(text(create_table_sql))
            conn.execute(text(create_index_sql))
            conn.commit()
        logger.info("临时工具表创建成功")
    except Exception as e:
        logger.error(f"创建临时工具表失败: {e}")
        raise


def downgrade():
    """删除临时工具表"""
    logger.info("开始删除临时工具表...")
    
    drop_table_sql = "DROP TABLE IF EXISTS temporary_tools;"
    
    try:
        with engine.connect() as conn:
            conn.execute(text(drop_table_sql))
            conn.commit()
        logger.info("临时工具表删除成功")
    except Exception as e:
        logger.error(f"删除临时工具表失败: {e}")
        raise


if __name__ == "__main__":
    upgrade()

