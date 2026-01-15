# -*- coding: utf-8 -*-
"""
知识图谱三元组抽取后台工作器
使用线程池异步处理文档的三元组抽取任务
"""
import os
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Optional
from sqlalchemy.orm import Session

from database.database import SessionLocal
from models.database_models import Document, DocumentChunk
from services.knowledge_graph_service import KnowledgeGraphService
from utils.log_helper import get_logger

logger = get_logger("kg_extraction_worker")

# 配置
KG_EXTRACTION_WORKERS = int(os.getenv("KG_EXTRACTION_WORKERS", "2"))
EXTRACT_TRIPLES_ENABLED = os.getenv("EXTRACT_TRIPLES_ENABLED", "true").lower() == "true"


class KGExtractionWorker:
    """知识图谱三元组抽取后台工作器"""
    
    def __init__(self, max_workers: int = KG_EXTRACTION_WORKERS):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="kg_extractor")
        self.running_tasks: Dict[int, Future] = {}  # doc_id -> Future
        self.kg_service = KnowledgeGraphService()
        self._lock = threading.Lock()
    
    def submit_document_extraction(self, doc_id: int):
        """提交文档的三元组抽取任务"""
        with self._lock:
            if doc_id in self.running_tasks:
                logger.warning(f"文档 {doc_id} 的三元组抽取任务已在运行中")
                return False
        
        future = self.executor.submit(self._extract_triples_for_document, doc_id)
        
        with self._lock:
            self.running_tasks[doc_id] = future
        
        # 任务完成时清理
        def cleanup(fut):
            with self._lock:
                if doc_id in self.running_tasks:
                    del self.running_tasks[doc_id]
        future.add_done_callback(cleanup)
        
        logger.info(f"已提交文档 {doc_id} 的三元组抽取任务")
        return True
    
    def _extract_triples_for_document(self, doc_id: int):
        """为文档的所有分块抽取三元组"""
        db: Optional[Session] = None
        try:
            db = SessionLocal()
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                logger.error(f"文档 {doc_id} 不存在")
                return
            
            # 检查是否启用三元组抽取
            if not EXTRACT_TRIPLES_ENABLED:
                logger.info(f"三元组抽取未启用，跳过文档 {doc_id}")
                doc.kg_extraction_status = "skipped"
                db.commit()
                return
            
            # 更新文档状态
            doc.kg_extraction_status = "processing"
            doc.kg_extraction_started_at = datetime.utcnow()
            db.commit()
            
            # 获取所有待处理的分块（排除摘要分块）
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.kg_extraction_status == "pending",
                DocumentChunk.is_summary == False  # 排除摘要分块
            ).order_by(DocumentChunk.chunk_index).all()
            
            if not chunks:
                logger.info(f"文档 {doc_id} 没有待处理的分块")
                doc.kg_extraction_status = "skipped"
                db.commit()
                return
            
            total_chunks = len(chunks)
            processed = 0
            failed = 0
            
            # 初始化进度
            doc.kg_extraction_progress = {
                "total_chunks": total_chunks,
                "processed": 0,
                "failed": 0
            }
            db.commit()
            
            logger.info(f"开始为文档 {doc_id} 的 {total_chunks} 个分块抽取三元组")
            
            # 预先分析和生成规则（文档级别，仅一次）
            # 合并所有分块内容作为文档文本用于分析
            document_text = "\n".join([chunk.content for chunk in chunks[:10]])  # 使用前10个分块作为样本
            if len(chunks) > 10:
                document_text += "\n" + chunks[-1].content  # 加上最后一个分块
            
            logger.info(f"文档 {doc_id} 准备进行文本分析和规则生成（使用 {min(10, len(chunks))} 个分块样本）")
            
            # 逐个处理分块
            for chunk in chunks:
                try:
                    # 更新分块状态
                    chunk.kg_extraction_status = "processing"
                    db.commit()
                    
                    # 使用知识图谱服务抽取三元组
                    # 第一个分块时传入完整文档文本用于分析和规则生成，后续分块复用
                    triples_data = self.kg_service.extract_entities_and_relations(
                        text=chunk.content,
                        kb_id=doc.knowledge_base_id,
                        doc_id=doc.id,
                        chunk_id=chunk.id,
                        document_text=document_text if chunk.chunk_index == 0 else None  # 只在第一个分块时传入
                    )
                    
                    if triples_data:
                        # 存储三元组
                        stored_count = self.kg_service.store_triples(db, triples_data)
                        chunk.kg_triples_count = stored_count
                        chunk.kg_extraction_status = "completed"
                        logger.info(f"分块 {chunk.id} (索引 {chunk.chunk_index}) 成功抽取 {stored_count} 个三元组")
                    else:
                        chunk.kg_extraction_status = "completed"  # 没有三元组也算完成
                        chunk.kg_triples_count = 0
                        logger.debug(f"分块 {chunk.id} (索引 {chunk.chunk_index}) 未抽取到三元组")
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"分块 {chunk.id} (索引 {chunk.chunk_index}) 三元组抽取失败: {str(e)}", exc_info=True)
                    chunk.kg_extraction_status = "failed"
                    chunk.kg_extraction_error = str(e)[:500]  # 限制错误信息长度
                    failed += 1
                
                # 更新进度（每处理一个分块就更新一次）
                doc.kg_extraction_progress = {
                    "total_chunks": total_chunks,
                    "processed": processed,
                    "failed": failed
                }
                db.commit()
            
            # 更新文档最终状态
            if failed == 0:
                doc.kg_extraction_status = "completed"
            elif processed > 0:
                doc.kg_extraction_status = "completed"  # 部分成功也算完成
            else:
                doc.kg_extraction_status = "failed"
            
            doc.kg_extraction_completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"文档 {doc_id} 三元组抽取完成: 成功 {processed}, 失败 {failed}")
            
        except Exception as e:
            logger.error(f"文档 {doc_id} 三元组抽取任务失败: {str(e)}", exc_info=True)
            if db:
                try:
                    doc = db.query(Document).filter(Document.id == doc_id).first()
                    if doc:
                        doc.kg_extraction_status = "failed"
                        if doc.kg_extraction_progress:
                            doc.kg_extraction_progress["error"] = str(e)[:500]
                        db.commit()
                except Exception as inner_e:
                    logger.error(f"更新文档失败状态时出错: {str(inner_e)}")
        finally:
            if db:
                db.close()
    
    def is_document_processing(self, doc_id: int) -> bool:
        """检查文档是否正在处理中"""
        with self._lock:
            return doc_id in self.running_tasks
    
    def shutdown(self, wait: bool = True):
        """关闭工作器"""
        logger.info("正在关闭KG抽取工作器...")
        self.executor.shutdown(wait=wait)
        logger.info("KG抽取工作器已关闭")


# 全局单例
_kg_worker: Optional[KGExtractionWorker] = None
_worker_lock = threading.Lock()


def get_kg_worker() -> KGExtractionWorker:
    """获取全局KG抽取工作器"""
    global _kg_worker
    if _kg_worker is None:
        with _worker_lock:
            if _kg_worker is None:
                max_workers = int(os.getenv("KG_EXTRACTION_WORKERS", "2"))
                _kg_worker = KGExtractionWorker(max_workers=max_workers)
                logger.info(f"初始化KG抽取工作器，最大工作线程数: {max_workers}")
    return _kg_worker
