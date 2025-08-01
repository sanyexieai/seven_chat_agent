"""
数据库迁移脚本：为Agent表添加新字段
用于支持新的智能体类型（prompt_driven, tool_driven, flow_driven）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from database.database import engine

def upgrade():
    """升级数据库结构"""
    with engine.connect() as conn:
        # 添加新字段
        conn.execute(text("""
            ALTER TABLE agents 
            ADD COLUMN system_prompt TEXT;
        """))
        
        conn.execute(text("""
            ALTER TABLE agents 
            ADD COLUMN bound_tools JSON;
        """))
        
        conn.execute(text("""
            ALTER TABLE agents 
            ADD COLUMN flow_config JSON;
        """))
        
        conn.commit()
        print("成功添加新字段到agents表")

def downgrade():
    """回滚数据库结构"""
    with engine.connect() as conn:
        # 删除新字段
        conn.execute(text("""
            ALTER TABLE agents 
            DROP COLUMN system_prompt;
        """))
        
        conn.execute(text("""
            ALTER TABLE agents 
            DROP COLUMN bound_tools;
        """))
        
        conn.execute(text("""
            ALTER TABLE agents 
            DROP COLUMN flow_config;
        """))
        
        conn.commit()
        print("成功删除新字段从agents表")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade() 