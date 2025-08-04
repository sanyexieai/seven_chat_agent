import os
import json
import uuid
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

logger = get_logger("knowledge_base_service")

class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self):
        self.text_processor = TextProcessor()
        self.embedding_service = EmbeddingService()
    
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
            file_path = None
            if doc_data.content:
                file_path = self._save_document_file(doc_data)
            
            doc = Document(
                knowledge_base_id=doc_data.knowledge_base_id,
                name=doc_data.name,
                file_path=file_path,
                file_type=doc_data.file_type,
                content=doc_data.content,
                doc_metadata=doc_data.doc_metadata,
                status="pending"
            )
            
            db.add(doc)
            db.commit()
            db.refresh(doc)
            
            # 异步处理文档
            self._process_document_async(db, doc)
            
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
            
            # 删除文件
            if doc.file_path and os.path.exists(doc.file_path):
                os.remove(doc.file_path)
            
            # 删除分块
            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
            
            # 软删除文档
            doc.is_active = False
            db.commit()
            
            logger.info(f"删除文档成功: {doc.name}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"删除文档失败: {str(e)}")
            raise
    
    def query_knowledge_base(self, db: Session, kb_id: int, query: str, 
                           user_id: str, max_results: int = 5) -> Dict[str, Any]:
        """查询知识库"""
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
                    chunk_embedding = json.loads(chunk.embedding)
                    similarity = self.embedding_service.calculate_similarity(
                        query_embedding, chunk_embedding
                    )
                    similarities.append((similarity, chunk))
            
            # 按相似度排序
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            # 获取最相关的分块
            top_chunks = similarities[:max_results]
            
            # 构建响应
            sources = []
            context_parts = []
            
            for similarity, chunk in top_chunks:
                sources.append({
                    "document_id": chunk.document_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
                    "similarity": similarity
                })
                context_parts.append(chunk.content)
            
            # 生成响应
            context = "\n\n".join(context_parts)
            response = self._generate_response(query, context)
            
            # 记录查询
            query_record = KnowledgeBaseQuery(
                knowledge_base_id=kb_id,
                user_id=user_id,
                query=query,
                response=response,
                sources=sources,
                query_metadata={"total_chunks": len(chunks), "max_results": max_results}
            )
            db.add(query_record)
            db.commit()
            
            return {
                "query": query,
                "response": response,
                "sources": sources,
                "metadata": {"total_chunks": len(chunks), "max_results": max_results}
            }
            
        except Exception as e:
            logger.error(f"查询知识库失败: {str(e)}")
            raise
    
    def _save_document_file(self, doc_data: DocumentCreate) -> str:
        """保存文档文件"""
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "documents")
        os.makedirs(data_dir, exist_ok=True)
        
        filename = f"{uuid.uuid4()}.{doc_data.file_type}"
        file_path = os.path.join(data_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(doc_data.content)
        
        return file_path
    
    def _process_document_async(self, db: Session, doc: Document):
        """异步处理文档"""
        try:
            # 更新状态为处理中
            doc.status = "processing"
            db.commit()
            
            # 分块处理
            chunks = self.text_processor.split_text(doc.content or "")
            
            # 创建分块记录
            for i, chunk_content in enumerate(chunks):
                # 生成向量嵌入
                embedding = self.embedding_service.get_embedding(chunk_content)
                
                chunk = DocumentChunk(
                    knowledge_base_id=doc.knowledge_base_id,
                    document_id=doc.id,
                    chunk_index=i,
                    content=chunk_content,
                    embedding=json.dumps(embedding),
                    chunk_metadata={"chunk_size": len(chunk_content)}
                )
                db.add(chunk)
            
            # 更新文档状态
            doc.status = "completed"
            db.commit()
            
            logger.info(f"文档处理完成: {doc.name}, 分块数: {len(chunks)}")
            
        except Exception as e:
            doc.status = "failed"
            db.commit()
            logger.error(f"文档处理失败: {doc.name}, 错误: {str(e)}")
    
    def _generate_response(self, query: str, context: str) -> str:
        """生成响应"""
        # 这里可以集成LLM来生成更好的响应
        # 暂时返回简单的上下文摘要
        if len(context) > 1000:
            context = context[:1000] + "..."
        
        return f"基于知识库内容，为您提供以下信息：\n\n{context}\n\n如果您需要更详细的信息，请提供更具体的查询。" 