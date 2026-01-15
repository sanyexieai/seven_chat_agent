#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新处理文档以提取知识图谱三元组
用于为已上传的文档补充知识图谱数据
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database.database import SessionLocal
from models.database_models import Document, DocumentChunk, KnowledgeTriple
from services.knowledge_base_service import KnowledgeBaseService
from utils.log_helper import get_logger

logger = get_logger("reprocess_documents_for_kg")


def reprocess_document(doc_id: int, db: Session):
    """重新处理单个文档，提取三元组"""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        logger.error(f"文档 {doc_id} 不存在")
        return False
    
    logger.info(f"开始重新处理文档: {doc.name} (ID: {doc_id})")
    
    # 检查是否已有三元组
    existing_triples = db.query(KnowledgeTriple).filter(
        KnowledgeTriple.document_id == doc_id
    ).count()
    
    if existing_triples > 0:
        logger.info(f"文档 {doc_id} 已有 {existing_triples} 个三元组，是否继续？(y/n)")
        # 这里可以添加交互逻辑，或者直接继续
    
    # 获取所有分块
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == doc_id
    ).order_by(DocumentChunk.chunk_index).all()
    
    if not chunks:
        logger.warning(f"文档 {doc_id} 没有分块，无法提取三元组")
        return False
    
    kb_service = KnowledgeBaseService()
    total_stored = 0
    
    for chunk in chunks:
        try:
            # 提取三元组
            triples_data = kb_service.kg_service.extract_entities_and_relations(
                text=chunk.content,
                kb_id=chunk.knowledge_base_id,
                doc_id=doc.id,
                chunk_id=chunk.id
            )
            
            if triples_data:
                # 存储三元组
                stored_count = kb_service.kg_service.store_triples(db, triples_data)
                total_stored += stored_count
                logger.info(f"分块 {chunk.chunk_index} (chunk_id={chunk.id}) 存储了 {stored_count} 个三元组")
        
        except Exception as e:
            logger.error(f"处理分块 {chunk.chunk_index} 失败: {str(e)}", exc_info=True)
            continue
    
    db.commit()
    logger.info(f"文档 {doc_id} 处理完成，共存储 {total_stored} 个三元组")
    return True


def reprocess_all_documents(kb_id: Optional[int] = None):
    """重新处理所有文档或指定知识库的文档"""
    db = SessionLocal()
    try:
        if kb_id:
            docs = db.query(Document).filter(
                Document.knowledge_base_id == kb_id,
                Document.status == "completed"
            ).all()
            logger.info(f"找到知识库 {kb_id} 的 {len(docs)} 个文档")
        else:
            docs = db.query(Document).filter(
                Document.status == "completed"
            ).all()
            logger.info(f"找到 {len(docs)} 个文档")
        
        for doc in docs:
            try:
                reprocess_document(doc.id, db)
            except Exception as e:
                logger.error(f"处理文档 {doc.id} 失败: {str(e)}", exc_info=True)
                continue
    
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="重新处理文档以提取知识图谱三元组")
    parser.add_argument("--doc-id", type=int, help="处理指定文档ID")
    parser.add_argument("--kb-id", type=int, help="处理指定知识库的所有文档")
    parser.add_argument("--all", action="store_true", help="处理所有文档")
    
    args = parser.parse_args()
    
    # 确保启用三元组提取
    os.environ["EXTRACT_TRIPLES_ENABLED"] = "true"
    os.environ["KG_EXTRACT_ENABLED"] = "true"
    
    if args.doc_id:
        db = SessionLocal()
        try:
            reprocess_document(args.doc_id, db)
        finally:
            db.close()
    elif args.kb_id:
        reprocess_all_documents(kb_id=args.kb_id)
    elif args.all:
        reprocess_all_documents()
    else:
        print("请指定 --doc-id, --kb-id 或 --all 参数")
        parser.print_help()
