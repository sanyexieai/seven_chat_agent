# 知识图谱三元组抽取 - 分步异步处理方案设计

## 一、设计目标

1. **分步处理**：先完成文档分块和向量化（快速返回），三元组抽取在后台异步进行
2. **状态追踪**：前端可以实时查看处理进度（分块完成、三元组抽取进度）
3. **模型集成**：使用组合1（RoBERTa-CLUE NER + CasRel RE）替代LLM抽取，提升速度和稳定性
4. **用户体验**：文档上传后立即显示分块完成，后台显示三元组抽取进度

## 二、架构设计

### 2.1 处理流程

```
文档上传
  ↓
[同步阶段] 分块 + 向量化
  ├─ 更新文档状态: processing → chunking → chunked
  ├─ 创建所有 DocumentChunk 记录
  └─ 生成并存储向量嵌入
  ↓
[异步阶段] 三元组抽取（后台线程）
  ├─ 使用 NER + RE 模型抽取三元组
  ├─ 更新每个分块的 kg_extraction_status
  └─ 更新文档的 kg_extraction_status
```

### 2.2 状态定义

#### Document 状态扩展
- `status`: `pending` → `processing` → `chunking` → `chunked` → `completed`
- `kg_extraction_status`: `pending` | `processing` | `completed` | `failed` | `skipped`
- `kg_extraction_progress`: `{"total_chunks": 10, "processed": 5, "failed": 0}`

#### DocumentChunk 状态
- `kg_extraction_status`: `pending` | `processing` | `completed` | `failed` | `skipped`
- `kg_triples_count`: 该分块抽取到的三元组数量

## 三、数据库模型修改

### 3.1 Document 表新增字段

```python
# agent-backend/models/database_models.py

class Document(Base):
    # ... 现有字段 ...
    
    # 新增：知识图谱抽取状态
    kg_extraction_status = Column(String(50), default="pending")  # pending, processing, completed, failed, skipped
    kg_extraction_progress = Column(JSON, nullable=True)  # {"total_chunks": 10, "processed": 5, "failed": 0}
    kg_extraction_started_at = Column(DateTime, nullable=True)
    kg_extraction_completed_at = Column(DateTime, nullable=True)
```

### 3.2 DocumentChunk 表新增字段

```python
# agent-backend/models/database_models.py

class DocumentChunk(Base):
    # ... 现有字段 ...
    
    # 新增：知识图谱抽取状态
    kg_extraction_status = Column(String(50), default="pending")  # pending, processing, completed, failed, skipped
    kg_triples_count = Column(Integer, default=0)  # 该分块抽取到的三元组数量
    kg_extraction_error = Column(Text, nullable=True)  # 抽取失败时的错误信息
```

## 四、后台任务处理

### 4.1 任务队列设计

使用 `concurrent.futures.ThreadPoolExecutor` 创建后台任务池：

```python
# agent-backend/services/kg_extraction_worker.py (新建)

import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Optional
from sqlalchemy.orm import Session
from database.database import get_db_session
from models.database_models import Document, DocumentChunk
from services.knowledge_graph_service import KnowledgeGraphService
from utils.log_helper import get_logger

logger = get_logger("kg_extraction_worker")

class KGExtractionWorker:
    """知识图谱三元组抽取后台工作器"""
    
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="kg_extractor")
        self.running_tasks: Dict[int, Future] = {}  # doc_id -> Future
        self.kg_service = KnowledgeGraphService()
    
    def submit_document_extraction(self, doc_id: int):
        """提交文档的三元组抽取任务"""
        if doc_id in self.running_tasks:
            logger.warning(f"文档 {doc_id} 的三元组抽取任务已在运行中")
            return
        
        future = self.executor.submit(self._extract_triples_for_document, doc_id)
        self.running_tasks[doc_id] = future
        
        # 任务完成时清理
        def cleanup(fut):
            if doc_id in self.running_tasks:
                del self.running_tasks[doc_id]
        future.add_done_callback(cleanup)
        
        logger.info(f"已提交文档 {doc_id} 的三元组抽取任务")
    
    def _extract_triples_for_document(self, doc_id: int):
        """为文档的所有分块抽取三元组"""
        db: Optional[Session] = None
        try:
            db = get_db_session()
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                logger.error(f"文档 {doc_id} 不存在")
                return
            
            # 更新文档状态
            doc.kg_extraction_status = "processing"
            doc.kg_extraction_started_at = datetime.utcnow()
            db.commit()
            
            # 获取所有待处理的分块
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc_id,
                DocumentChunk.kg_extraction_status == "pending"
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
            
            # 逐个处理分块
            for chunk in chunks:
                try:
                    # 更新分块状态
                    chunk.kg_extraction_status = "processing"
                    db.commit()
                    
                    # 使用知识图谱服务抽取三元组
                    triples_data = self.kg_service.extract_entities_and_relations(
                        text=chunk.content,
                        kb_id=doc.knowledge_base_id,
                        doc_id=doc.id,
                        chunk_id=chunk.id
                    )
                    
                    if triples_data:
                        # 存储三元组
                        stored_count = self.kg_service.store_triples(db, triples_data)
                        chunk.kg_triples_count = stored_count
                        chunk.kg_extraction_status = "completed"
                        logger.info(f"分块 {chunk.id} 成功抽取 {stored_count} 个三元组")
                    else:
                        chunk.kg_extraction_status = "completed"  # 没有三元组也算完成
                        chunk.kg_triples_count = 0
                        logger.debug(f"分块 {chunk.id} 未抽取到三元组")
                    
                    processed += 1
                    
                except Exception as e:
                    logger.error(f"分块 {chunk.id} 三元组抽取失败: {str(e)}", exc_info=True)
                    chunk.kg_extraction_status = "failed"
                    chunk.kg_extraction_error = str(e)
                    failed += 1
                
                # 更新进度
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
                        db.commit()
                except:
                    pass
        finally:
            if db:
                db.close()
    
    def is_document_processing(self, doc_id: int) -> bool:
        """检查文档是否正在处理中"""
        return doc_id in self.running_tasks
    
    def shutdown(self, wait: bool = True):
        """关闭工作器"""
        self.executor.shutdown(wait=wait)

# 全局单例
_kg_worker: Optional[KGExtractionWorker] = None

def get_kg_worker() -> KGExtractionWorker:
    """获取全局KG抽取工作器"""
    global _kg_worker
    if _kg_worker is None:
        max_workers = int(os.getenv("KG_EXTRACTION_WORKERS", "2"))
        _kg_worker = KGExtractionWorker(max_workers=max_workers)
    return _kg_worker
```

### 4.2 集成到知识库服务

修改 `knowledge_base_service.py` 的 `_process_document_sync` 方法：

```python
# agent-backend/services/knowledge_base_service.py

def _process_document_sync(self, db: Session, doc: Document):
    """同步处理文档（分块和向量化，三元组抽取异步进行）"""
    try:
        logger.info(f"开始处理文档: {doc.name}")
        
        # 更新状态为处理中
        doc.status = "processing"
        doc.kg_extraction_status = "pending"  # 初始化KG抽取状态
        db.commit()
        
        # ... 分块处理逻辑（保持不变） ...
        
        # 创建分块记录（移除三元组抽取逻辑）
        created_chunks: List[DocumentChunk] = []
        for i, (chunk_content, embedding, metadata) in enumerate(zip(chunk_contents, embeddings, chunk_metadata_list)):
            chunk = DocumentChunk(
                knowledge_base_id=doc.knowledge_base_id,
                document_id=doc.id,
                chunk_index=i,
                content=chunk_content,
                embedding=embedding,
                chunk_metadata=metadata,
                chunk_strategy=CHUNK_STRATEGY,
                strategy_variant=strategy_variant,
                kg_extraction_status="pending"  # 初始状态
            )
            db.add(chunk)
            created_chunks.append(chunk)
        
        db.commit()
        
        # 更新文档状态为分块完成
        doc.status = "chunked"  # 新增状态：分块完成但三元组未抽取
        doc.document_metadata = doc.document_metadata or {}
        doc.document_metadata["chunk_count"] = len(chunks)
        doc.document_metadata["processing_time"] = datetime.utcnow().isoformat()
        db.commit()
        
        # 提交后台任务：异步抽取三元组
        if EXTRACT_TRIPLES_ENABLED:
            from services.kg_extraction_worker import get_kg_worker
            kg_worker = get_kg_worker()
            kg_worker.submit_document_extraction(doc.id)
            logger.info(f"已提交文档 {doc.id} 的三元组抽取后台任务")
        
        # ... 其他处理逻辑（领域识别、摘要生成等） ...
        
    except Exception as e:
        logger.error(f"处理文档失败: {str(e)}", exc_info=True)
        doc.status = "failed"
        db.commit()
```

## 五、API 接口设计

### 5.1 查询文档处理状态

```python
# agent-backend/api/knowledge_base.py

@router.get("/{kb_id}/documents/{doc_id}/status")
async def get_document_status(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档处理状态（包括分块和三元组抽取进度）"""
    try:
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
        
        return {
            "document_id": doc.id,
            "status": doc.status,  # pending, processing, chunking, chunked, completed, failed
            "kg_extraction_status": doc.kg_extraction_status,  # pending, processing, completed, failed, skipped
            "kg_extraction_progress": doc.kg_extraction_progress or {},
            "chunk_stats": chunk_stats,
            "total_triples": sum(c.kg_triples_count or 0 for c in chunks),
            "kg_extraction_started_at": doc.kg_extraction_started_at.isoformat() if doc.kg_extraction_started_at else None,
            "kg_extraction_completed_at": doc.kg_extraction_completed_at.isoformat() if doc.kg_extraction_completed_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail="获取文档状态失败")
```

### 5.2 查询知识图谱统计

```python
@router.get("/{kb_id}/documents/{doc_id}/kg/stats")
async def get_document_kg_stats(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档的知识图谱统计信息"""
    try:
        from services.knowledge_graph_service import KnowledgeGraphService
        kg_service = KnowledgeGraphService()
        
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
```

## 六、前端显示设计

### 6.1 文档列表显示

在 `KnowledgeBasePage.tsx` 中增强文档状态显示：

```typescript
// agent-ui/src/pages/KnowledgeBasePage.tsx

interface Document {
  // ... 现有字段 ...
  status: string;
  kg_extraction_status?: string;
  kg_extraction_progress?: {
    total_chunks: number;
    processed: number;
    failed: number;
  };
}

// 在文档卡片中显示状态
{doc.status === 'chunked' && doc.kg_extraction_status === 'processing' && (
  <div style={{ marginTop: '8px', padding: '8px', backgroundColor: '#fff7e6', border: '1px solid #ffd591', borderRadius: '4px' }}>
    <p style={{ color: '#d46b08', margin: 0, fontSize: '12px', fontWeight: 'bold' }}>
      📊 分块完成，正在抽取知识图谱...
    </p>
    {doc.kg_extraction_progress && (
      <Progress 
        percent={Math.round((doc.kg_extraction_progress.processed / doc.kg_extraction_progress.total_chunks) * 100)}
        size="small"
        status="active"
        style={{ marginTop: '4px' }}
      />
    )}
    <p style={{ color: '#d46b08', margin: '4px 0 0 0', fontSize: '11px' }}>
      已处理: {doc.kg_extraction_progress?.processed || 0} / {doc.kg_extraction_progress?.total_chunks || 0}
    </p>
  </div>
)}

{doc.status === 'chunked' && doc.kg_extraction_status === 'completed' && (
  <div style={{ marginTop: '8px', padding: '8px', backgroundColor: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: '4px' }}>
    <p style={{ color: '#52c41a', margin: 0, fontSize: '12px' }}>
      ✅ 知识图谱抽取完成
    </p>
  </div>
)}
```

### 6.2 轮询更新状态

```typescript
// 在文档列表页面添加轮询逻辑
useEffect(() => {
  const interval = setInterval(async () => {
    // 只轮询正在处理中的文档
    const processingDocs = documents.filter(
      d => d.status === 'processing' || 
           d.status === 'chunked' && d.kg_extraction_status === 'processing'
    );
    
    if (processingDocs.length > 0) {
      // 批量查询状态
      for (const doc of processingDocs) {
        try {
          const response = await fetch(`${API_BASE}/api/knowledge-base/${selectedKb?.id}/documents/${doc.id}/status`);
          if (response.ok) {
            const status = await response.json();
            // 更新文档状态
            setDocuments(prev => prev.map(d => 
              d.id === doc.id ? { ...d, ...status } : d
            ));
          }
        } catch (error) {
          console.error(`查询文档 ${doc.id} 状态失败:`, error);
        }
      }
    }
  }, 3000); // 每3秒轮询一次
  
  return () => clearInterval(interval);
}, [documents, selectedKb]);
```

## 七、模型集成（组合1）

### 7.1 创建 NER + RE 服务

```python
# agent-backend/services/ie_model_service.py (新建)

from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from typing import List, Tuple, Dict, Any
import torch

class IEModelService:
    """信息抽取模型服务（NER + RE）"""
    
    def __init__(self):
        self.ner_model = None
        self.re_model = None
        self.ner_tokenizer = None
        self.re_tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._load_models()
    
    def _load_models(self):
        """加载NER和RE模型"""
        try:
            # NER模型：RoBERTa-CLUE
            ner_model_name = "uer/roberta-base-finetuned-cluener2020-chinese"
            logger.info(f"加载NER模型: {ner_model_name}")
            self.ner_tokenizer = AutoTokenizer.from_pretrained(ner_model_name)
            self.ner_model = AutoModelForTokenClassification.from_pretrained(ner_model_name)
            self.ner_model.to(self.device)
            self.ner_model.eval()
            
            # RE模型：CasRel（需要根据实际可用的模型调整）
            # 注意：需要找到合适的中文CasRel权重，或使用其他RE模型
            re_model_name = "yubowen-ph/CasRel-bert-base-chinese"  # 示例，需要验证
            logger.info(f"加载RE模型: {re_model_name}")
            # ... 加载RE模型 ...
            
            logger.info("信息抽取模型加载完成")
        except Exception as e:
            logger.error(f"加载信息抽取模型失败: {str(e)}")
            raise
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """提取实体"""
        # 使用NER模型提取实体
        # ...
        pass
    
    def extract_relations(self, text: str, entities: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
        """提取关系（三元组）"""
        # 使用RE模型提取关系
        # ...
        pass
```

### 7.2 集成到知识图谱服务

修改 `knowledge_graph_service.py`，添加模型抽取模式：

```python
# agent-backend/services/knowledge_graph_service.py

KG_EXTRACT_MODE = os.getenv("KG_EXTRACT_MODE", "hybrid").lower()  # llm / rule / hybrid / model

class KnowledgeGraphService:
    def __init__(self):
        # ... 现有初始化 ...
        self.ie_model_service = None
        if KG_EXTRACT_MODE == "model":
            try:
                from services.ie_model_service import IEModelService
                self.ie_model_service = IEModelService()
            except Exception as e:
                logger.warning(f"无法加载IE模型，将回退到规则/LLM模式: {str(e)}")
    
    def extract_entities_and_relations(self, ...):
        """提取实体和关系"""
        if KG_EXTRACT_MODE == "model" and self.ie_model_service:
            # 使用专用模型抽取
            entities = self.ie_model_service.extract_entities(text)
            triples = self.ie_model_service.extract_relations(text, entities)
            # 转换为标准格式
            # ...
        else:
            # 使用现有逻辑（规则/LLM/混合）
            # ...
```

## 八、实施步骤

1. **数据库迁移**：添加新字段到 `Document` 和 `DocumentChunk` 表
2. **后台工作器**：创建 `kg_extraction_worker.py`
3. **服务修改**：修改 `knowledge_base_service.py` 的 `_process_document_sync`
4. **API接口**：添加状态查询接口
5. **前端显示**：更新文档列表和状态显示
6. **模型集成**：创建 `ie_model_service.py` 并集成到知识图谱服务
7. **测试验证**：测试完整流程

## 九、配置项

```bash
# .env 文件新增配置

# 知识图谱抽取模式：llm / rule / hybrid / model
KG_EXTRACT_MODE=model

# 后台工作器线程数
KG_EXTRACTION_WORKERS=2

# 是否启用三元组抽取
EXTRACT_TRIPLES_ENABLED=true
```

## 十、注意事项

1. **线程安全**：确保数据库会话在后台线程中正确创建和关闭
2. **错误处理**：单个分块失败不应影响整体任务
3. **资源管理**：模型加载后应保持常驻，避免重复加载
4. **进度更新**：定期提交数据库更新，避免长时间事务
5. **前端轮询**：合理设置轮询间隔，避免过度请求
