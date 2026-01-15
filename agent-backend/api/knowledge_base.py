from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from database.database import get_db
from models.database_models import (
    KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse,
    DocumentCreate, DocumentUpdate, DocumentResponse, DocumentChunkResponse,
    QueryRequest, QueryResponse
)
from services.knowledge_base_service import KnowledgeBaseService
from utils.file_extractor import FileExtractor
from utils.log_helper import get_logger

logger = get_logger("knowledge_base_api")

router = APIRouter(prefix="/api/knowledge-base", tags=["知识库"])

# 创建服务实例
kb_service = KnowledgeBaseService()

@router.post("", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    kb_data: KnowledgeBaseCreate,
    db: Session = Depends(get_db)
):
    """创建知识库"""
    try:
        kb = kb_service.create_knowledge_base(db, kb_data)
        return KnowledgeBaseResponse.model_validate(kb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建知识库失败")

@router.get("", response_model=List[KnowledgeBaseResponse])
async def get_knowledge_bases_no_slash(
    owner_id: Optional[str] = None,
    include_public: bool = True,
    db: Session = Depends(get_db)
):
    """获取知识库列表（不带斜杠）"""
    return await get_knowledge_bases(owner_id, include_public, db)

@router.get("/", response_model=List[KnowledgeBaseResponse])
async def get_knowledge_bases(
    owner_id: Optional[str] = None,
    include_public: bool = True,
    db: Session = Depends(get_db)
):
    """获取知识库列表"""
    try:
        kbs = kb_service.get_knowledge_bases(db, owner_id, include_public)
        return [KnowledgeBaseResponse.model_validate(kb) for kb in kbs]
    except Exception as e:
        logger.error(f"获取知识库列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取知识库列表失败")

@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库详情"""
    try:
        kb = kb_service.get_knowledge_base(db, kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return KnowledgeBaseResponse.model_validate(kb)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取知识库详情失败")

@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int,
    update_data: KnowledgeBaseUpdate,
    db: Session = Depends(get_db)
):
    """更新知识库"""
    try:
        kb = kb_service.update_knowledge_base(db, kb_id, update_data)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return KnowledgeBaseResponse.model_validate(kb)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新知识库失败")

@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """删除知识库"""
    try:
        success = kb_service.delete_knowledge_base(db, kb_id)
        if not success:
            raise HTTPException(status_code=404, detail="知识库不存在")
        return {"message": "知识库删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除知识库失败")

@router.post("/{kb_id}/documents", response_model=DocumentResponse)
async def create_document(
    kb_id: int,
    name: str = Form(...),
    file_type: str = Form(...),
    content: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """创建文档"""
    try:
        # 解析元数据
        doc_metadata = None
        if metadata:
            try:
                doc_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="元数据格式错误")
        
        doc_data = DocumentCreate(
            knowledge_base_id=kb_id,
            name=name,
            file_type=file_type,
            content=content,
            doc_metadata=doc_metadata
        )
        
        doc = kb_service.create_document(db, doc_data)
        return DocumentResponse.model_validate(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建文档失败")

@router.post("/{kb_id}/documents/upload", response_model=DocumentResponse)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """上传文档文件"""
    try:
        # 读取文件内容
        content = await file.read()
        
        # 解析元数据
        doc_metadata = None
        if metadata:
            try:
                doc_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="元数据格式错误")
        
        # 添加文件信息到元数据
        if doc_metadata is None:
            doc_metadata = {}
        doc_metadata.update({
            "original_filename": file.filename,
            "file_size": len(content),
            "content_type": file.content_type
        })
        
        # 使用文件提取器处理内容
        file_extractor = FileExtractor()
        file_type = file.filename.split('.')[-1].lower() if file.filename and '.' in file.filename else "txt"
        
        try:
            # 提取文件文本内容
            content_str, extraction_metadata = file_extractor.extract_text(
                content, file_type, file.filename
            )
            
            # 合并提取元数据
            doc_metadata.update(extraction_metadata)
            
            logger.info(f"文件内容提取成功: {file.filename}, 方法: {extraction_metadata.get('extraction_method', 'unknown')}")
            
        except Exception as e:
            logger.error(f"文件内容提取失败: {file.filename}, 错误: {str(e)}")
            # 如果提取失败，使用base64编码作为备选
            import base64
            content_str = base64.b64encode(content).decode('utf-8')
            doc_metadata.update({
                "encoding": "base64",
                "extraction_method": "base64_fallback",
                "extraction_error": str(e)
            })
        
        doc_data = DocumentCreate(
            knowledge_base_id=kb_id,
            name=file.filename or "uploaded_document",
            file_type=file_type,
            content=content_str,
            doc_metadata=doc_metadata
        )
        
        doc = kb_service.create_document(db, doc_data)
        return DocumentResponse.model_validate(doc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail="上传文档失败")

@router.get("/{kb_id}/documents", response_model=List[DocumentResponse])
async def get_documents(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库的文档列表"""
    try:
        docs = kb_service.get_documents(db, kb_id)
        return [DocumentResponse.model_validate(doc) for doc in docs]
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文档列表失败")

@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档详情"""
    try:
        doc = kb_service.get_document(db, doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocumentResponse.model_validate(doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文档详情失败")

@router.get("/{kb_id}/documents/{doc_id}/status")
async def get_document_status(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档处理状态（包括分块和三元组抽取进度）"""
    try:
        from models.database_models import Document, DocumentChunk
        from services.kg_extraction_worker import get_kg_worker
        
        doc = db.query(Document).filter(
            Document.id == doc_id,
            Document.knowledge_base_id == kb_id
        ).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        # 统计分块的三元组抽取状态
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == doc_id
        ).all()
        
        chunk_stats = {
            "total": len(chunks),
            "pending": sum(1 for c in chunks if c.kg_extraction_status == "pending"),
            "processing": sum(1 for c in chunks if c.kg_extraction_status == "processing"),
            "completed": sum(1 for c in chunks if c.kg_extraction_status == "completed"),
            "failed": sum(1 for c in chunks if c.kg_extraction_status == "failed"),
        }
        
        # 检查是否正在后台处理
        kg_worker = get_kg_worker()
        is_processing = kg_worker.is_document_processing(doc_id)
        
        return {
            "document_id": doc.id,
            "status": doc.status,  # pending, processing, chunking, chunked, completed, failed
            "kg_extraction_status": doc.kg_extraction_status or "pending",  # pending, processing, completed, failed, skipped
            "kg_extraction_progress": doc.kg_extraction_progress or {},
            "chunk_stats": chunk_stats,
            "total_triples": sum(c.kg_triples_count or 0 for c in chunks),
            "is_processing": is_processing,
            "kg_extraction_started_at": doc.kg_extraction_started_at.isoformat() if doc.kg_extraction_started_at else None,
            "kg_extraction_completed_at": doc.kg_extraction_completed_at.isoformat() if doc.kg_extraction_completed_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文档状态失败")

@router.get("/{kb_id}/documents/{doc_id}/kg/stats")
async def get_document_kg_stats(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档的知识图谱统计信息"""
    try:
        from models.database_models import KnowledgeTriple
        
        # 查询该文档的所有三元组
        triples = db.query(KnowledgeTriple).filter(
            KnowledgeTriple.document_id == doc_id,
            KnowledgeTriple.knowledge_base_id == kb_id
        ).all()
        
        # 统计实体和关系
        entities = set()
        relations = {}
        for triple in triples:
            entities.add(triple.subject)
            entities.add(triple.object)
            rel = triple.predicate
            relations[rel] = relations.get(rel, 0) + 1
        
        return {
            "total_triples": len(triples),
            "unique_entities": len(entities),
            "unique_relations": len(relations),
            "top_relations": sorted(relations.items(), key=lambda x: x[1], reverse=True)[:10]
        }
    except Exception as e:
        logger.error(f"获取知识图谱统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取知识图谱统计失败")

@router.get("/{kb_id}/documents/{doc_id}/kg/triples")
async def get_document_kg_triples(
    kb_id: int,
    doc_id: int,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """获取文档的实际三元组列表（用于调试和查看）"""
    try:
        from models.database_models import KnowledgeTriple
        
        # 查询该文档的所有三元组
        triples = db.query(KnowledgeTriple).filter(
            KnowledgeTriple.document_id == doc_id,
            KnowledgeTriple.knowledge_base_id == kb_id
        ).order_by(KnowledgeTriple.confidence.desc()).limit(limit).all()
        
        result = []
        for triple in triples:
            result.append({
                "id": triple.id,
                "subject": triple.subject,
                "predicate": triple.predicate,
                "object": triple.object,
                "confidence": triple.confidence,
                "source_text": triple.source_text[:100] if triple.source_text else "",
                "chunk_id": triple.chunk_id,
                "created_at": triple.created_at.isoformat() if triple.created_at else None
            })
        
        return {
            "total": len(result),
            "triples": result
        }
    except Exception as e:
        logger.error(f"获取三元组列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取三元组列表失败")

@router.put("/documents/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    update_data: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """更新文档"""
    try:
        doc = kb_service.update_document(db, doc_id, update_data)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return DocumentResponse.model_validate(doc)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail="更新文档失败")

@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """删除文档"""
    try:
        success = kb_service.delete_document(db, doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="文档不存在")
        return {"message": "文档删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail="删除文档失败")

@router.post("/{kb_id}/query")
async def query_knowledge_base(
    kb_id: int,
    query_request: QueryRequest,
    db: Session = Depends(get_db)
):
    """查询知识库"""
    try:
        logger.info(f"知识库查询: kb_id={kb_id}, user_id={query_request.user_id}, max_results={query_request.max_results}, top_k={query_request.top_k}, threshold={query_request.similarity_threshold}")
        result = kb_service.query_knowledge_base(
            db, kb_id, query_request.query, 
            query_request.user_id, query_request.max_results,
            top_k=query_request.top_k,
            similarity_threshold=query_request.similarity_threshold
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询知识库失败: {str(e)}")
        raise HTTPException(status_code=500, detail="查询知识库失败")

@router.get("/{kb_id}/chunks", response_model=List[DocumentChunkResponse])
async def get_document_chunks(
    kb_id: int,
    document_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取文档分块"""
    try:
        from sqlalchemy.orm import Session
        from models.database_models import DocumentChunk
        
        query = db.query(DocumentChunk).filter(DocumentChunk.knowledge_base_id == kb_id)
        if document_id:
            query = query.filter(DocumentChunk.document_id == document_id)
        
        chunks = query.order_by(DocumentChunk.chunk_index).all()
        return [DocumentChunkResponse.model_validate(chunk) for chunk in chunks]
    except Exception as e:
        logger.error(f"获取文档分块失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文档分块失败")

@router.get("/{kb_id}/graph/stats")
async def get_knowledge_graph_stats(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识图谱统计信息"""
    try:
        from services.knowledge_graph_service import KnowledgeGraphService
        kg_service = KnowledgeGraphService()
        stats = kg_service.get_entity_statistics(db, kb_id)
        return stats
    except Exception as e:
        logger.error(f"获取知识图谱统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取知识图谱统计失败")

@router.get("/{kb_id}/graph/entities/{entity_name}")
async def query_entity(
    kb_id: int,
    entity_name: str,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """查询实体相关的三元组"""
    try:
        from services.knowledge_graph_service import KnowledgeGraphService
        kg_service = KnowledgeGraphService()
        results = kg_service.query_entities(db, kb_id, entity_name, limit)
        return {"entity": entity_name, "triples": results, "count": len(results)}
    except Exception as e:
        logger.error(f"查询实体失败: {str(e)}")
        raise HTTPException(status_code=500, detail="查询实体失败")

@router.get("/{kb_id}/graph/path")
async def query_relation_path(
    kb_id: int,
    start_entity: str,
    end_entity: str,
    max_hops: int = 3,
    db: Session = Depends(get_db)
):
    """查询两个实体之间的关系路径"""
    try:
        from services.knowledge_graph_service import KnowledgeGraphService
        kg_service = KnowledgeGraphService()
        paths = kg_service.query_relation_path(db, kb_id, start_entity, end_entity, max_hops)
        return {
            "start_entity": start_entity,
            "end_entity": end_entity,
            "paths": paths,
            "path_count": len(paths)
        }
    except Exception as e:
        logger.error(f"查询关系路径失败: {str(e)}")
        raise HTTPException(status_code=500, detail="查询关系路径失败") 