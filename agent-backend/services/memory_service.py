from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models.database_models import MemoryRecord, MemoryRecordCreate
from utils.embedding_service import EmbeddingService
from utils.log_helper import get_logger

logger = get_logger("memory_service")


class MemoryService:
    """通用记忆服务
    
    职责：
    - 将来自 Pipeline / Agent 的记忆落地到 memories 表
    - 为记忆生成向量嵌入（使用 EmbeddingService）
    - 提供简单的基于余弦相似度的 RAG 检索接口
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()

    def create_memory(
        self,
        db: Session,
        data: MemoryRecordCreate,
        auto_embed: bool = True,
    ) -> MemoryRecord:
        """创建一条记忆记录，并可选生成向量嵌入"""
        try:
            payload = data.model_dump()
            content: str = payload.get("content", "") or ""

            embedding = None
            if auto_embed and content:
                embedding = self.embedding_service.get_embedding(content)

            record = MemoryRecord(
                user_id=payload.get("user_id"),
                agent_name=payload.get("agent_name"),
                session_id=payload.get("session_id"),
                memory_type=payload.get("memory_type"),
                category=payload.get("category"),
                source=payload.get("source"),
                content=content,
                memory_metadata=payload.get("metadata") or {},
                embedding=embedding,
                score=None,
                is_active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
        except Exception as e:
            db.rollback()
            logger.error(f"创建记忆失败: {e}")
            raise

    def search_memories(
        self,
        db: Session,
        query: str,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        memory_types: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """基于向量相似度在 memories 表中做简单 RAG 检索"""
        if not query:
            return []

        try:
            query_vec = self.embedding_service.get_embedding(query)

            q = db.query(MemoryRecord).filter(MemoryRecord.is_active == True)
            if user_id:
                q = q.filter(MemoryRecord.user_id == user_id)
            if agent_name:
                q = q.filter(MemoryRecord.agent_name == agent_name)
            if session_id:
                q = q.filter(MemoryRecord.session_id == session_id)
            if memory_types:
                q = q.filter(MemoryRecord.memory_type.in_(memory_types))

            records: List[MemoryRecord] = q.filter(MemoryRecord.embedding.isnot(None)).all()
            if not records:
                return []

            scored: List[Dict[str, Any]] = []
            for r in records:
                if not r.embedding:
                    continue
                score = self.embedding_service.calculate_similarity(query_vec, r.embedding)
                scored.append(
                    {
                        "id": r.id,
                        "user_id": r.user_id,
                        "agent_name": r.agent_name,
                        "session_id": r.session_id,
                        "memory_type": r.memory_type,
                        "category": r.category,
                        "source": r.source,
                        "content": r.content,
                        "metadata": r.memory_metadata or {},
                        "similarity": score,
                        "created_at": r.created_at,
                    }
                )

            scored.sort(key=lambda x: x["similarity"], reverse=True)
            return scored[:top_k]
        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []


