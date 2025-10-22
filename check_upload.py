#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append('agent-backend')

from database.database import SessionLocal
from models.database_models import Document, DocumentChunk

def check_upload():
    """检查上传状态"""
    db = SessionLocal()
    try:
        docs = db.query(Document).all()
        print(f'文档数量: {len(docs)}')
        
        for d in docs:
            print(f'文档 {d.id}: {d.name}, 状态: {d.status}')
            if d.document_metadata:
                print(f'  元数据: {d.document_metadata}')
        
        chunks = db.query(DocumentChunk).all()
        print(f'分块数量: {len(chunks)}')
        
        if chunks:
            for c in chunks[:3]:
                print(f'分块 {c.id}: KB={c.knowledge_base_id}, 维度={len(c.embedding) if c.embedding else 0}')
                
    except Exception as e:
        print(f'检查失败: {str(e)}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_upload()
