from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from models.database_models import MCPTool, TemporaryTool
from utils.embedding_service import EmbeddingService
from utils.vector_store import create_vector_store
from utils.log_helper import get_logger

logger = get_logger("tool_rag_service")


class ToolRAGService:
    """工具向量检索服务

    职责：
    - 为 MCP 工具 / 临时工具生成向量嵌入
    - 基于描述 / 元数据做相似度检索，为工具选择 / planner 提供 RAG 能力
    """

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = create_vector_store(
            store_type="simple",
            embedding_dim=self.embedding_service.embedding_dim
        )

    def _build_tool_text(self, tool: Any) -> str:
        """把工具的描述、元数据等拼接成适合做嵌入的文本"""
        parts: List[str] = []
        try:
            name = getattr(tool, "name", "") or ""
            display_name = getattr(tool, "display_name", "") or ""
            description = getattr(tool, "description", "") or ""
            tool_type = getattr(tool, "tool_type", "") or ""
            metadata = getattr(tool, "tool_metadata", None) or {}

            parts.append(f"name: {name}")
            if display_name and display_name != name:
                parts.append(f"display_name: {display_name}")
            if description:
                parts.append(f"description: {description}")
            if tool_type:
                parts.append(f"type: {tool_type}")
            if metadata:
                parts.append(f"metadata: {metadata}")
        except Exception:
            pass
        return "\n".join(parts)

    def refresh_tool_embedding(self, db: Session, tool_id: int, is_temporary: bool = False) -> None:
        """为指定工具生成 / 刷新向量嵌入"""
        try:
            model = TemporaryTool if is_temporary else MCPTool
            tool = db.query(model).filter(model.id == tool_id).first()
            if not tool:
                return

            text = self._build_tool_text(tool)
            if not text:
                return

            embedding = self.embedding_service.get_embedding(text)
            tool.embedding = embedding
            db.commit()

            # 重建索引以包含新的嵌入
            self.rebuild_index(db)
        except Exception as e:
            db.rollback()
            logger.error(f"刷新工具嵌入失败: {e}")
            raise

    def rebuild_index(self, db: Session, include_temporary: bool = True):
        """重建工具向量索引"""
        try:
            tools: List[Any] = (
                db.query(MCPTool).filter(MCPTool.is_active == True, MCPTool.embedding.isnot(None)).all()
            )
            if include_temporary:
                tools += (
                    db.query(TemporaryTool)
                    .filter(TemporaryTool.is_active == True, TemporaryTool.embedding.isnot(None))
                    .all()
                )

            if not tools:
                logger.warning("没有工具需要索引")
                return

            vectors = []
            metadata = []
            for t in tools:
                if not getattr(t, "embedding", None):
                    continue
                vectors.append(t.embedding)
                metadata.append({
                    "id": t.id,
                    "name": getattr(t, "name", ""),
                    "display_name": getattr(t, "display_name", ""),
                    "description": getattr(t, "description", ""),
                    "tool_type": getattr(t, "tool_type", None) if hasattr(t, "tool_type") else "temporary",
                    "server_id": getattr(t, "server_id", None),
                    "is_temporary": isinstance(t, TemporaryTool),
                })

            self.vector_store.add_vectors(vectors, metadata)
            logger.info(f"成功索引 {len(vectors)} 个工具")
        except Exception as e:
            logger.error(f"重建工具索引失败: {e}")
            raise

    def search_tools(
        self,
        db: Session,
        query: str,
        include_temporary: bool = True,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """基于向量相似度在工具集合中做RAG检索"""
        if not query:
            return []

        try:
            query_vec = self.embedding_service.get_embedding(query)
            results = self.vector_store.search(query_vec, top_k=top_k)

            if not include_temporary:
                results = [r for r in results if not r.get("is_temporary", False)]

            return results[:top_k]
        except Exception as e:
            logger.error(f"工具 RAG 检索失败: {e}")
            raise


