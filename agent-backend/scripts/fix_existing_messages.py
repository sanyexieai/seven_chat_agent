"""
修复现有消息的content字段
将用户消息的内容从metadata中提取到content字段
"""

import os
import sys
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from models.database_models import Base

# 数据库连接配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_agent.db")

def fix_existing_messages():
    """修复现有消息的content字段"""
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            # 1. 检查content字段是否存在
            if 'sqlite' in DATABASE_URL:
                result = conn.execute(text("PRAGMA table_info(chat_messages)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'content' not in columns:
                    print("❌ content字段不存在，请先运行迁移脚本")
                    return False
            else:
                # 对于其他数据库，检查字段是否存在
                try:
                    conn.execute(text("SELECT content FROM chat_messages LIMIT 1"))
                except Exception as e:
                    if "column" in str(e).lower() and "does not exist" in str(e).lower():
                        print("❌ content字段不存在，请先运行迁移脚本")
                        return False
                    else:
                        raise e
            
            # 2. 查找没有content的用户消息
            print("🔍 查找没有content的用户消息...")
            result = conn.execute(text("""
                SELECT id, message_id, message_type, message_metadata 
                FROM chat_messages 
                WHERE (content IS NULL OR content = '') 
                AND message_type = 'user'
            """))
            
            user_messages = result.fetchall()
            print(f"找到 {len(user_messages)} 条没有content的用户消息")
            
            if len(user_messages) == 0:
                print("✅ 所有用户消息都有content字段")
                return True
            
            # 3. 尝试从metadata中提取content
            fixed_count = 0
            for msg in user_messages:
                msg_id, message_id, message_type, metadata = msg
                
                if metadata and isinstance(metadata, dict):
                    # 尝试从metadata中提取content
                    content = None
                    
                    # 常见的content字段名
                    for field in ['content', 'message', 'text', 'body']:
                        if field in metadata and metadata[field]:
                            content = str(metadata[field])
                            break
                    
                    if content:
                        # 更新content字段
                        conn.execute(text("""
                            UPDATE chat_messages 
                            SET content = :content 
                            WHERE id = :id
                        """), {
                            "content": content,
                            "id": msg_id
                        })
                        fixed_count += 1
                        print(f"✅ 修复消息 {message_id}: {content[:50]}...")
                    else:
                        print(f"⚠️ 消息 {message_id} 的metadata中没有找到content")
                else:
                    print(f"⚠️ 消息 {message_id} 的metadata为空或格式错误")
            
            # 4. 提交更改
            conn.commit()
            print(f"✅ 成功修复 {fixed_count} 条消息的content字段")
            
            # 5. 显示修复后的统计
            result = conn.execute(text("""
                SELECT 
                    message_type,
                    COUNT(*) as total,
                    COUNT(content) as with_content,
                    COUNT(*) - COUNT(content) as without_content
                FROM chat_messages 
                GROUP BY message_type
            """))
            
            print("\n📊 修复后的消息统计:")
            for row in result.fetchall():
                msg_type, total, with_content, without_content = row
                print(f"  {msg_type}: 总计 {total}, 有content {with_content}, 无content {without_content}")
            
            return True
            
        except Exception as e:
            print(f"❌ 修复消息失败: {e}")
            return False

def main():
    """主函数"""
    print("🚀 开始修复现有消息的content字段")
    print("=" * 50)
    
    success = fix_existing_messages()
    
    if success:
        print("\n✅ 修复完成！")
        print("\n📋 下一步:")
        print("1. 重启后端服务")
        print("2. 刷新前端页面")
        print("3. 检查用户消息是否正常显示")
    else:
        print("\n❌ 修复失败，请检查错误信息")

 