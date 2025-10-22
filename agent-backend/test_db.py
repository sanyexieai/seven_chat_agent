#!/usr/bin/env python3
import sys
sys.path.append('.')

from database.database import SessionLocal
from models.database_models import KnowledgeBase
from sqlalchemy import text

def test_database():
    """测试数据库连接和数据"""
    db = SessionLocal()
    try:
        # 检查表是否存在
        result = db.execute(text('SELECT name FROM sqlite_master WHERE type="table" AND name="knowledge_bases"'))
        tables = result.fetchall()
        print('数据库表:', [t[0] for t in tables])
        
        # 检查知识库表结构
        result = db.execute(text('PRAGMA table_info(knowledge_bases)'))
        columns = result.fetchall()
        print('knowledge_bases表结构:')
        for col in columns:
            print(f'  {col[1]} {col[2]} {"NOT NULL" if col[3] else "NULL"} {"PRIMARY KEY" if col[5] else ""}')
        
        # 查询知识库数据
        kbs = db.query(KnowledgeBase).all()
        print(f'知识库数量: {len(kbs)}')
        for kb in kbs:
            print(f'  ID: {kb.id}, Name: {kb.name}, Display: {kb.display_name}, Active: {kb.is_active}')
            
        # 测试过滤查询
        active_kbs = db.query(KnowledgeBase).filter(KnowledgeBase.is_active == True).all()
        print(f'激活的知识库数量: {len(active_kbs)}')
        
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_database()
