"""
示例脚本：插入测试消息数据
演示新的消息数据结构
"""

import os
import sys
from datetime import datetime
import uuid

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from models.database_models import Base, ChatMessage, MessageNode, MessageChunk

# 数据库连接配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./chat_agent.db")

def insert_test_data():
    """插入测试数据"""
    engine = create_engine(DATABASE_URL)
    
    # 创建表（如果不存在）
    Base.metadata.create_all(engine)
    
    with engine.connect() as conn:
        # 1. 创建测试会话
        session_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO user_sessions (session_id, user_id, session_name, created_at, updated_at)
            VALUES (:session_id, :user_id, :session_name, :created_at, :updated_at)
        """), {
            "session_id": session_id,
            "user_id": "test_user",
            "session_name": "测试对话",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        })
        
        # 2. 创建测试消息
        message_id = f"agent_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}"
        conn.execute(text("""
            INSERT INTO chat_messages (message_id, session_id, user_id, message_type, agent_name, created_at)
            VALUES (:message_id, :session_id, :user_id, :message_type, :agent_name, :created_at)
        """), {
            "message_id": message_id,
            "session_id": session_id,
            "user_id": "test_user",
            "message_type": "agent",
            "agent_name": "test_agent",
            "created_at": datetime.utcnow()
        })
        
        # 3. 创建测试节点（直接内容格式）
        node1 = conn.execute(text("""
            INSERT INTO message_nodes (node_id, message_id, node_type, node_name, node_label, content, created_at)
            VALUES (:node_id, :message_id, :node_type, :node_name, :node_label, :content, :created_at)
        """), {
            "node_id": "start_llm",
            "message_id": message_id,
            "node_type": "llm",
            "node_name": "开始判断",
            "node_label": "开始判断",
            "content": "这是一个直接内容的节点示例",
            "created_at": datetime.utcnow()
        }).lastrowid
        
        # 4. 创建测试节点（片段列表格式）
        node2 = conn.execute(text("""
            INSERT INTO message_nodes (node_id, message_id, node_type, node_name, node_label, created_at)
            VALUES (:node_id, :message_id, :node_type, :node_name, :node_label, :created_at)
        """), {
            "node_id": "router_1",
            "message_id": message_id,
            "node_type": "router",
            "node_name": "路由判断",
            "node_label": "路由判断",
            "created_at": datetime.utcnow()
        }).lastrowid
        
        # 5. 为第二个节点添加片段
        chunks = [
            ("路由决策: can_direct_answer=False -> false", "content"),
            ("✅ 路由判断 节点执行完成", "node_complete")
        ]
        
        for content, chunk_type in chunks:
            conn.execute(text("""
                INSERT INTO message_chunks (chunk_id, node_id, content, chunk_type, created_at)
                VALUES (:chunk_id, :node_id, :content, :chunk_type, :created_at)
            """), {
                "chunk_id": str(uuid.uuid4()),
                "node_id": node2,
                "content": content,
                "chunk_type": chunk_type,
                "created_at": datetime.utcnow()
            })
        
        # 6. 创建第三个节点（混合格式）
        node3 = conn.execute(text("""
            INSERT INTO message_nodes (node_id, message_id, node_type, node_name, node_label, content, created_at)
            VALUES (:node_id, :message_id, :node_type, :node_name, :node_label, :content, :created_at)
        """), {
            "node_id": "tool_required",
            "message_id": message_id,
            "node_type": "llm",
            "node_name": "需要工具",
            "node_label": "需要工具",
            "content": "您好！很高兴与您交谈。",
            "created_at": datetime.utcnow()
        }).lastrowid
        
        # 为第三个节点也添加一些片段
        conn.execute(text("""
            INSERT INTO message_chunks (chunk_id, node_id, content, chunk_type, created_at)
            VALUES (:chunk_id, :node_id, :content, :chunk_type, :created_at)
        """), {
            "chunk_id": str(uuid.uuid4()),
            "node_id": node3,
            "content": "为了提供有效的帮助，能否提供更多信息？",
            "chunk_type": "content",
            "created_at": datetime.utcnow()
        })
        
        # 提交事务
        conn.commit()
        
        print(f"✅ 成功插入测试数据")
        print(f"会话ID: {session_id}")
        print(f"消息ID: {message_id}")
        print(f"节点数量: 3")
        print(f"片段数量: 4")

if __name__ == "__main__":
    insert_test_data() 