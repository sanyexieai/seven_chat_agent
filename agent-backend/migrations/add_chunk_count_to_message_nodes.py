"""
为message_nodes表添加chunk_count字段的迁移脚本
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database_models import Base, get_database_url

def upgrade():
    """执行升级"""
    engine = create_engine(get_database_url())
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'message_nodes' 
            AND column_name = 'chunk_count'
        """))
        
        if result.fetchone():
            print("✅ chunk_count字段已存在，跳过迁移")
            return
        
        # 添加chunk_count字段
        conn.execute(text("""
            ALTER TABLE message_nodes 
            ADD COLUMN chunk_count INTEGER DEFAULT 0
        """))
        
        # 更新现有记录的chunk_count为0
        conn.execute(text("""
            UPDATE message_nodes 
            SET chunk_count = 0 
            WHERE chunk_count IS NULL
        """))
        
        conn.commit()
        print("✅ 成功添加chunk_count字段到message_nodes表")

def downgrade():
    """执行回滚"""
    engine = create_engine(get_database_url())
    
    with engine.connect() as conn:
        # 检查字段是否存在
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'message_nodes' 
            AND column_name = 'chunk_count'
        """))
        
        if not result.fetchone():
            print("❌ chunk_count字段不存在，无需回滚")
            return
        
        # 删除chunk_count字段
        conn.execute(text("""
            ALTER TABLE message_nodes 
            DROP COLUMN chunk_count
        """))
        
        conn.commit()
        print("✅ 成功删除chunk_count字段")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移脚本")
    parser.add_argument("--action", choices=["upgrade", "downgrade"], default="upgrade", 
                       help="执行操作: upgrade(升级) 或 downgrade(回滚)")
    
    args = parser.parse_args()
    
    if args.action == "upgrade":
        upgrade()
    else:
        downgrade() 