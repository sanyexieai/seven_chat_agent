"""
数据库迁移脚本：为chat_messages表添加content字段
"""

from sqlalchemy import create_engine, text
import os

# 数据库连接配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_agent.db")

def upgrade():
    """升级数据库结构"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 检查字段是否已存在
        try:
            # 对于SQLite，使用PRAGMA检查表结构
            if 'sqlite' in DATABASE_URL:
                result = conn.execute(text("PRAGMA table_info(chat_messages)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'content' not in columns:
                    # 添加content字段
                    conn.execute(text("""
                        ALTER TABLE chat_messages 
                        ADD COLUMN content TEXT
                    """))
                    print("✅ 成功为chat_messages表添加content字段")
                else:
                    print("ℹ️ content字段已存在，无需添加")
            else:
                # 对于其他数据库（如PostgreSQL），使用不同的语法
                try:
                    conn.execute(text("""
                        ALTER TABLE chat_messages 
                        ADD COLUMN content TEXT
                    """))
                    print("✅ 成功为chat_messages表添加content字段")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                        print("ℹ️ content字段已存在，无需添加")
                    else:
                        raise e
                        
        except Exception as e:
            print(f"❌ 添加content字段失败: {e}")
            return False
        
        # 提交事务
        conn.commit()
        return True

def downgrade():
    """回滚数据库结构"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # 对于SQLite，不支持DROP COLUMN，需要重建表
            if 'sqlite' in DATABASE_URL:
                print("⚠️ SQLite不支持DROP COLUMN，需要手动重建表")
                print("建议：备份数据，删除表，重新创建")
            else:
                # 对于其他数据库
                conn.execute(text("""
                    ALTER TABLE chat_messages 
                    DROP COLUMN content
                """))
                print("✅ 成功删除chat_messages表的content字段")
            
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 删除content字段失败: {e}")
            return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "down":
        downgrade()
    else:
        upgrade() 