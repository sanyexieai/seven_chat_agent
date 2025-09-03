import os
import json
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.database_models import (
    KnowledgeBase, Document, DocumentChunk, KnowledgeBaseQuery,
    KnowledgeBaseCreate, KnowledgeBaseUpdate, DocumentCreate, DocumentUpdate
)
from utils.log_helper import get_logger
from utils.text_processor import TextProcessor
from utils.embedding_service import EmbeddingService
from utils.file_extractor import FileExtractor
from utils.reranker import rerank as rerank_results  # 新增

logger = get_logger("knowledge_base_service")

RERANKER_AFTER_TOP_N = int(os.getenv("RERANKER_AFTER_TOP_N", "20"))
RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K", "5"))
RERANKER_ENABLED_ENV = os.getenv("RERANKER_ENABLED", "true").lower() == "true"

class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self):
        self.text_processor = TextProcessor()
        self.embedding_service = EmbeddingService()
        self.file_extractor = FileExtractor()
    
    def create_knowledge_base(self, db: Session, kb_data: KnowledgeBaseCreate) -> KnowledgeBase:
        """创建知识库"""
        try:
            # 检查名称是否已存在
            existing_kb = db.query(KnowledgeBase).filter(
                KnowledgeBase.name == kb_data.name
            ).first()
            
            if existing_kb:
                raise ValueError(f"知识库名称 '{kb_data.name}' 已存在")
            
            kb = KnowledgeBase(**kb_data.model_dump())
            db.add(kb)
            db.commit()
            db.refresh(kb)
            
            logger.info(f"创建知识库成功: {kb.name}")
            return kb
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建知识库失败: {str(e)}")
            raise
    
    def get_knowledge_base(self, db: Session, kb_id: int) -> Optional[KnowledgeBase]:
        """获取知识库"""
        return db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    
    def get_knowledge_bases(self, db: Session, owner_id: Optional[str] = None, 
                           include_public: bool = True) -> List[KnowledgeBase]:
        """获取知识库列表"""
        query = db.query(KnowledgeBase).filter(KnowledgeBase.is_active == True)
        
        if owner_id:
            # 获取用户的知识库和公开的知识库
            if include_public:
                query = query.filter(
                    or_(
                        KnowledgeBase.owner_id == owner_id,
                        KnowledgeBase.is_public == True
                    )
                )
            else:
                query = query.filter(KnowledgeBase.owner_id == owner_id)
        elif not include_public:
            # 只获取公开的知识库
            query = query.filter(KnowledgeBase.is_public == True)
        
        return query.order_by(KnowledgeBase.created_at.desc()).all()
    
    def update_knowledge_base(self, db: Session, kb_id: int, 
                            update_data: KnowledgeBaseUpdate) -> Optional[KnowledgeBase]:
        """更新知识库"""
        try:
            kb = self.get_knowledge_base(db, kb_id)
            if not kb:
                return None
            
            update_dict = update_data.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(kb, field, value)
            
            kb.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(kb)
            
            logger.info(f"更新知识库成功: {kb.name}")
            return kb
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新知识库失败: {str(e)}")
            raise
    
    def delete_knowledge_base(self, db: Session, kb_id: int) -> bool:
        """删除知识库"""
        try:
            kb = self.get_knowledge_base(db, kb_id)
            if not kb:
                return False
            
            # 软删除
            kb.is_active = False
            db.commit()
            
            logger.info(f"删除知识库成功: {kb.name}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"删除知识库失败: {str(e)}")
            raise
    
    def create_document(self, db: Session, doc_data: DocumentCreate) -> Document:
        """创建文档"""
        try:
            # 检查知识库是否存在
            kb = self.get_knowledge_base(db, doc_data.knowledge_base_id)
            if not kb:
                raise ValueError("知识库不存在")
            
            # 生成文档ID
            doc_id = str(uuid.uuid4())
            
            # 保存文件到本地（如果有文件内容）
            if doc_data.content:
                self._save_document_file(doc_data)
            
            doc = Document(
                knowledge_base_id=doc_data.knowledge_base_id,
                name=doc_data.name,
                file_type=doc_data.file_type,
                content=doc_data.content,
                document_metadata=doc_data.document_metadata,
                status="pending"
            )
            
            db.add(doc)
            db.commit()
            db.refresh(doc)
            
            # 立即处理文档（同步处理，确保分块创建）
            self._process_document_sync(db, doc)
            
            logger.info(f"创建文档成功: {doc.name}")
            return doc
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建文档失败: {str(e)}")
            raise
    
    def get_document(self, db: Session, doc_id: int) -> Optional[Document]:
        """获取文档"""
        return db.query(Document).filter(Document.id == doc_id).first()
    
    def get_documents(self, db: Session, kb_id: int) -> List[Document]:
        """获取知识库的文档列表"""
        return db.query(Document).filter(
            Document.knowledge_base_id == kb_id,
            Document.is_active == True
        ).order_by(Document.created_at.desc()).all()
    
    def update_document(self, db: Session, doc_id: int, 
                       update_data: DocumentUpdate) -> Optional[Document]:
        """更新文档"""
        try:
            doc = self.get_document(db, doc_id)
            if not doc:
                return None
            
            update_dict = update_data.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                setattr(doc, field, value)
            
            doc.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(doc)
            
            logger.info(f"更新文档成功: {doc.name}")
            return doc
            
        except Exception as e:
            db.rollback()
            logger.error(f"更新文档失败: {str(e)}")
            raise
    
    def delete_document(self, db: Session, doc_id: int) -> bool:
        """删除文档"""
        try:
            doc = self.get_document(db, doc_id)
            if not doc:
                return False
            
            # 软删除
            doc.is_active = False
            db.commit()
            
            logger.info(f"删除文档成功: {doc.name}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"删除文档失败: {str(e)}")
            raise
    
    def query_knowledge_base(self, db: Session, kb_id: int, query: str, 
                           user_id: str, max_results: int = 5, **kwargs) -> Dict[str, Any]:
        """查询知识库
        兼容旧签名：允许通过 limit 传入最大结果数
        """
        # 兼容 general_agent 调用中的 limit 参数
        limit = kwargs.get("limit")
        effective_max = int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)
        
        try:
            # 获取知识库
            kb = self.get_knowledge_base(db, kb_id)
            if not kb:
                raise ValueError("知识库不存在")
            
            # 获取查询的向量嵌入
            query_embedding = self.embedding_service.get_embedding(query)
            
            # 获取知识库的所有分块
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.knowledge_base_id == kb_id
            ).all()
            
            if not chunks:
                return {
                    "query": query,
                    "response": "知识库中没有找到相关文档。",
                    "sources": [],
                    "metadata": {"total_chunks": 0}
                }
            
            # 计算相似度并排序
            similarities = []
            for chunk in chunks:
                if chunk.embedding:
                    # embedding字段已经是列表格式，不需要json.loads
                    chunk_embedding = chunk.embedding if isinstance(chunk.embedding, list) else json.loads(chunk.embedding)
                    similarity = self.embedding_service.calculate_similarity(
                        query_embedding, chunk_embedding
                    )
                    similarities.append((similarity, chunk))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[0], reverse=True)
            logger.info(f"KB[{kb_id}] 初筛候选数: {len(similarities)}，将取前N用于重排: {max(RERANKER_AFTER_TOP_N, effective_max)}，目标返回: {effective_max}")
            
            # 先取前N做重排序候选（避免对全量做CrossEncoder）
            initial_top_n = similarities[:max(RERANKER_AFTER_TOP_N, effective_max)]
            logger.info(f"KB[{kb_id}] 重排候选数: {len(initial_top_n)}, 重排启用: {RERANKER_ENABLED_ENV}")
            
            # 组装候选用于重排序
            candidates: List[Dict[str, Any]] = []
            for sim, chunk in initial_top_n:
                candidates.append({
                    "similarity": float(sim),
                    "content": chunk.content or "",
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "knowledge_base_id": chunk.knowledge_base_id,
                })
            
            # 执行重排序（若未启用则保持原顺序）
            reranked = rerank_results(query, candidates, content_key="content", top_k=RERANKER_TOP_K)
            logger.info(f"KB[{kb_id}] 重排完成，返回前K: {min(len(reranked), RERANKER_TOP_K)}")
            
            # 选取最终top结果（同时兼顾effective_max）
            final_sources = reranked[:effective_max]
            
            # 构建响应
            sources = []
            context_parts = []
            
            for item in final_sources:
                content = item.get("content", "")
                sources.append({
                    "content": content,
                    "similarity": item.get("similarity", 0.0),
                    "rerank_score": item.get("rerank_score", None),
                    "chunk_id": item.get("chunk_id"),
                    "document_id": item.get("document_id"),
                })
                context_parts.append(content)
            
            context = "\n\n".join(context_parts)
            response = self._generate_response(query, context)
            
            return {
                "query": query,
                "response": response,
                "sources": sources,
                "metadata": {
                    "total_chunks": len(chunks),
                    "initial_considered": len(initial_top_n),
                    "final_selected": len(final_sources),
                    "reranker_enabled": RERANKER_ENABLED_ENV,
                    "reranker_after_top_n": RERANKER_AFTER_TOP_N,
                    "reranker_top_k": RERANKER_TOP_K,
                }
            }
        except Exception as e:
            logger.error(f"查询知识库失败: {str(e)}")
            raise
    
    def _save_document_file(self, doc_data: DocumentCreate) -> str:
        """保存文档文件到本地"""
        # 创建上传目录
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成文件路径
        file_path = os.path.join(upload_dir, f"{doc_data.name}")
        
        # 保存文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(doc_data.content)
        
        return file_path
    
    def _process_document_sync(self, db: Session, doc: Document):
        """同步处理文档（立即分块和生成嵌入）"""
        try:
            logger.info(f"开始处理文档: {doc.name}")
            
            # 更新状态为处理中
            doc.status = "processing"
            db.commit()
            
            # 检查内容是否为空
            if not doc.content or not doc.content.strip():
                logger.warning(f"文档内容为空: {doc.name}")
                doc.status = "failed"
                doc.document_metadata = doc.document_metadata or {}
                doc.document_metadata["error"] = "文档内容为空"
                db.commit()
                return
            
            # 分块处理
            logger.info(f"开始分块处理: {doc.name}")
            chunks = self.text_processor.split_text(doc.content)
            logger.info(f"分块完成: {doc.name}, 分块数: {len(chunks)}")
            
            if not chunks:
                logger.warning(f"分块结果为空: {doc.name}")
                doc.status = "failed"
                doc.document_metadata = doc.document_metadata or {}
                doc.document_metadata["error"] = "分块结果为空"
                db.commit()
                return
            
            # 创建分块记录
            logger.info(f"开始创建分块记录: {doc.name}")
            for i, chunk_content in enumerate(chunks):
                try:
                    # 生成向量嵌入
                    logger.info(f"生成第{i+1}个分块的嵌入向量...")
                    embedding = self.embedding_service.get_embedding(chunk_content)
                    
                    chunk = DocumentChunk(
                        knowledge_base_id=doc.knowledge_base_id,
                        document_id=doc.id,
                        chunk_index=i,
                        content=chunk_content,
                        embedding=embedding,
                        chunk_metadata={"chunk_size": len(chunk_content)}
                    )
                    db.add(chunk)
                    logger.info(f"第{i+1}个分块创建成功")
                    
                except Exception as e:
                    logger.error(f"创建第{i+1}个分块失败: {str(e)}")
                    continue
            
            # 提交所有分块
            db.commit()
            
            # 更新文档状态
            doc.status = "completed"
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["chunk_count"] = len(chunks)
            doc.document_metadata["processing_time"] = datetime.utcnow().isoformat()
            db.commit()
            
            logger.info(f"文档处理完成: {doc.name}, 分块数: {len(chunks)}")
            
        except Exception as e:
            logger.error(f"文档处理失败: {doc.name}, 错误: {str(e)}")
            doc.status = "failed"
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["error"] = str(e)
            db.commit()
    
    def _generate_response(self, query: str, context: str) -> str:
        """生成响应"""
        # 这里可以集成LLM来生成更好的响应
        # 暂时返回简单的上下文摘要
        if len(context) > 1000:
            context = context[:1000] + "..."
        
        return f"基于知识库内容，为您提供以下信息：\n\n{context}\n\n如果您需要更详细的信息，请提供更具体的查询。"
