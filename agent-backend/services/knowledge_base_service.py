import os
import json
import uuid
import asyncio
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models.database_models import (
    KnowledgeBase, Document, DocumentChunk, KnowledgeBaseQuery,
    KnowledgeBaseCreate, KnowledgeBaseUpdate, DocumentCreate, DocumentUpdate,
    KnowledgeTriple, KnowledgeTripleCreate
)
from utils.log_helper import get_logger
from utils.text_processor import TextProcessor
from utils.embedding_service import EmbeddingService
from utils.file_extractor import FileExtractor
# 移除向量存储文件依赖，改为纯数据库存储
from utils.query_processor import QueryProcessor
from utils.performance_optimizer import cached, timed, retry
from utils.reranker import rerank as rerank_results  # 新增
from utils.llm_helper import get_llm_helper
from services.knowledge_graph_service import KnowledgeGraphService  # 新增知识图谱服务

logger = get_logger("knowledge_base_service")

RERANKER_AFTER_TOP_N = int(os.getenv("RERANKER_AFTER_TOP_N", "20"))
RERANKER_TOP_K = int(os.getenv("RERANKER_TOP_K", "5"))
RERANKER_ENABLED_ENV = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
EXTRACT_TRIPLES_ENABLED = os.getenv("EXTRACT_TRIPLES_ENABLED", "true").lower() == "true"  # 默认启用
KNOWLEDGE_GRAPH_ENABLED = os.getenv("KNOWLEDGE_GRAPH_ENABLED", "true").lower() == "true"  # 默认启用知识图谱
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.0"))  # 相似度阈值，默认0.0（不过滤），让重排序处理
SIMILARITY_THRESHOLD_MIN = float(os.getenv("SIMILARITY_THRESHOLD_MIN", "0.1"))  # 最低相似度阈值（用于最终过滤）
LLM_QUERY_DECOMPOSE_ENABLED = os.getenv("LLM_QUERY_DECOMPOSE_ENABLED", "true").lower() == "true"  # 默认启用LLM拆解
CHUNK_STRATEGY = os.getenv("CHUNK_STRATEGY", "hierarchical")  # hierarchical, semantic, sentence, fixed
USE_LLM_MERGE = os.getenv("USE_LLM_MERGE", "false").lower() == "true"
MULTI_HOP_MAX_HOPS = int(os.getenv("MULTI_HOP_MAX_HOPS", "2"))  # 多跳查询最大跳数
DOMAIN_CLASSIFY_ENABLED = os.getenv("DOMAIN_CLASSIFY_ENABLED", "true").lower() == "true"
SUMMARY_CHUNKS_ENABLED = os.getenv("SUMMARY_CHUNKS_ENABLED", "true").lower() == "true"
MULTI_ROUTE_RECALL_ENABLED = os.getenv("MULTI_ROUTE_RECALL_ENABLED", "true").lower() == "true"  # 多路召回：向量+关键词并行

class KnowledgeBaseService:
    """知识库服务"""
    
    def __init__(self, vector_store_type: str = "auto"):
        self.text_processor = TextProcessor(
            chunk_size=500,      # 目标分块大小
            overlap=50,          # 重叠长度
            chunk_strategy=CHUNK_STRATEGY,  # 使用配置的分割策略
            min_chunk_size=100,  # 最小分块大小
            max_chunk_size=800,  # 最大分块大小
            use_llm_merge=False  # 默认关闭LLM优化分块（避免频繁调用，改为按需启用）
        )
        self.embedding_service = EmbeddingService()
        self.file_extractor = FileExtractor()
        self.query_processor = QueryProcessor()
        self.kg_service = KnowledgeGraphService()  # 知识图谱服务
        # 移除文件向量存储，改为纯数据库存储
    
    def _search_chunks_from_db(self, db: Session, kb_id: int, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """从数据库搜索相似分块（优化版：先计算所有相似度，再动态调整阈值）"""
        try:
            # 获取所有分块的嵌入向量
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.knowledge_base_id == kb_id,
                DocumentChunk.embedding.isnot(None)
            ).all()
            
            if not chunks:
                logger.warning(f"知识库 {kb_id} 没有找到分块")
                return []
            
            logger.debug(f"开始计算 {len(chunks)} 个分块的相似度")
            
            # 计算所有分块的相似度（不过滤，先全部计算）
            similarities = []
            for chunk in chunks:
                if chunk.embedding:
                    try:
                        similarity = self.embedding_service.calculate_similarity(query_vector, chunk.embedding)
                        # 记录所有相似度，不过滤
                        similarities.append((similarity, chunk))
                    except Exception as e:
                        logger.warning(f"计算分块 {chunk.id} 相似度失败: {str(e)}")
                        continue
            
            if not similarities:
                logger.warning(f"没有计算出任何相似度结果")
                return []
            
            # 排序（按相似度降序）
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            # 动态调整阈值：如果结果不够，降低阈值
            effective_threshold = SIMILARITY_THRESHOLD
            filtered_similarities = [(s, c) for s, c in similarities if s >= effective_threshold]
            
            # 如果过滤后结果不够，动态降低阈值
            if len(filtered_similarities) < top_k:
                # 尝试使用最低阈值
                filtered_similarities = [(s, c) for s, c in similarities if s >= SIMILARITY_THRESHOLD_MIN]
                if len(filtered_similarities) < top_k:
                    # 如果还是不够，使用所有结果（但记录警告）
                    filtered_similarities = similarities[:top_k * 2]  # 取前2倍，让重排序处理
                    logger.warning(f"相似度阈值过滤后结果不足，使用前 {len(filtered_similarities)} 个结果（最低相似度: {filtered_similarities[-1][0]:.4f}）")
                else:
                    logger.info(f"使用最低阈值 {SIMILARITY_THRESHOLD_MIN}，找到 {len(filtered_similarities)} 个结果")
            
            # 取前top_k（或更多，用于重排序）
            results = []
            for similarity, chunk in filtered_similarities[:top_k]:
                result = {
                    'content': chunk.content,
                    'similarity': similarity,
                    'chunk_id': chunk.id,
                    'document_id': chunk.document_id,
                    'knowledge_base_id': chunk.knowledge_base_id,
                    'chunk_index': chunk.chunk_index,
                    'chunk_metadata': chunk.chunk_metadata or {}
                }
                results.append(result)
            
            # 记录统计信息
            if results:
                max_sim = results[0]['similarity']
                min_sim = results[-1]['similarity']
                logger.info(f"向量搜索完成: 返回 {len(results)} 个结果，相似度范围: {min_sim:.4f} - {max_sim:.4f}")
            else:
                logger.warning(f"向量搜索未返回任何结果")
            
            return results
            
        except Exception as e:
            logger.error(f"数据库向量搜索失败: {str(e)}", exc_info=True)
            return []
    
    def _search_by_keywords(self, db: Session, kb_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """基于关键词的文本搜索（作为向量搜索的补充）"""
        try:
            # 提取查询中的关键词（去除停用词）
            import re
            # 简单的中文停用词
            stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
            
            # 提取关键词（2-10个字符的连续中文字符）
            keywords = re.findall(r'[\u4e00-\u9fa5]{2,10}', query)
            keywords = [kw for kw in keywords if kw not in stopwords and len(kw) >= 2]
            
            if not keywords:
                return []
            
            logger.debug(f"关键词搜索: {keywords}")
            
            # 在分块内容中搜索关键词
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.knowledge_base_id == kb_id,
                DocumentChunk.content.isnot(None)
            ).all()
            
            if not chunks:
                return []
            
            # 计算每个分块的关键词匹配分数
            scored_chunks = []
            for chunk in chunks:
                if not chunk.content:
                    continue
                
                content_lower = chunk.content.lower()
                score = 0
                matched_keywords = []
                
                for keyword in keywords:
                    # 计算关键词出现次数和位置权重
                    count = content_lower.count(keyword.lower())
                    if count > 0:
                        # 位置权重：出现在前面的权重更高
                        first_pos = content_lower.find(keyword.lower())
                        position_weight = 1.0 - (first_pos / max(len(content_lower), 1)) * 0.5
                        keyword_score = count * (1 + position_weight)
                        score += keyword_score
                        matched_keywords.append(keyword)
                
                if score > 0:
                    scored_chunks.append({
                        'content': chunk.content,
                        'similarity': min(0.9, score / len(keywords)),  # 归一化到0-0.9
                        'chunk_id': chunk.id,
                        'document_id': chunk.document_id,
                        'knowledge_base_id': chunk.knowledge_base_id,
                        'chunk_index': chunk.chunk_index,
                        'chunk_metadata': chunk.chunk_metadata or {},
                        'matched_keywords': matched_keywords,
                        'keyword_score': score
                    })
            
            # 按分数排序
            scored_chunks.sort(key=lambda x: x['keyword_score'], reverse=True)
            
            logger.debug(f"关键词搜索找到 {len(scored_chunks)} 个匹配分块")
            return scored_chunks[:top_k]
            
        except Exception as e:
            logger.error(f"关键词搜索失败: {str(e)}")
            return []
    
    def create_knowledge_base(self, db: Session, kb_data: KnowledgeBaseCreate) -> KnowledgeBase:
        """创建知识库"""
        try:
            # 检查名称是否已存在（只检查未删除的知识库）
            existing_kb = db.query(KnowledgeBase).filter(
                KnowledgeBase.name == kb_data.name,
                KnowledgeBase.is_active == True
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
    
    @cached(ttl_seconds=300)  # 缓存5分钟
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
    
    @timed
    @retry(max_retries=2)
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
            
            # 处理查询
            processed_query_info = self.query_processor.process_query(query, user_id)
            final_query = processed_query_info["rewritten_query"]
            
            # 多路召回策略：向量搜索 + 关键词搜索并行
            search_results = []
            
            # 1. 查询拆解（如果启用）
            decomposed_terms: List[str] = []
            if LLM_QUERY_DECOMPOSE_ENABLED:
                try:
                    decomposed_terms = self._decompose_query_terms(final_query)
                    logger.info(f"查询拆解结果: {decomposed_terms}")
                except Exception as e:
                    logger.warning(f"查询拆解失败: {str(e)}")
            
            # 2. 并行执行多路召回
            import concurrent.futures
            
            def vector_search_main():
                """主查询向量搜索"""
                query_embedding = self.embedding_service.get_embedding(final_query, is_query=True)
                return self._search_chunks_from_db(db, kb_id, query_embedding, top_k=max(RERANKER_AFTER_TOP_N, effective_max * 2))
            
            def keyword_search_main():
                """主查询关键词搜索"""
                if MULTI_ROUTE_RECALL_ENABLED:
                    return self._search_by_keywords(db, kb_id, final_query, top_k=effective_max * 2)
                return []
            
            def vector_search_sub(term):
                """子查询向量搜索"""
                try:
                    emb = self.embedding_service.get_embedding(term, is_query=True)
                    return self._search_chunks_from_db(db, kb_id, emb, top_k=RERANKER_AFTER_TOP_N)
                except Exception as e:
                    logger.warning(f"子查询向量检索失败: {str(e)}")
                    return []
            
            # 并行执行主查询的向量搜索和关键词搜索
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_vector = executor.submit(vector_search_main)
                future_keyword = executor.submit(keyword_search_main)
                
                vector_results = future_vector.result()
                keyword_results = future_keyword.result()
                
                logger.info(f"主查询向量搜索结果: {len(vector_results)} 个")
                logger.info(f"主查询关键词搜索结果: {len(keyword_results)} 个")
            
            # 合并主查询结果（改进版：加权融合）
            all_results = {}
            
            # 1. 先添加向量搜索结果（权重1.0）
            for result in vector_results:
                cid = result.get('chunk_id')
                if cid:
                    result['source'] = 'vector'
                    result['weighted_score'] = result.get('similarity', 0.0) * 1.0
                    if cid not in all_results:
                        all_results[cid] = result
                    else:
                        # 保留最高分
                        if result.get('similarity', 0.0) > all_results[cid].get('similarity', 0.0):
                            all_results[cid] = result
            
            # 2. 添加关键词搜索结果（权重0.8，但精确匹配时提升权重）
            for result in keyword_results:
                cid = result.get('chunk_id')
                if cid:
                    result['source'] = 'keyword'
                    kw_score = result.get('similarity', 0.0)
                    # 检查是否是精确匹配（所有关键词都出现）
                    matched_keywords = result.get('matched_keywords', [])
                    keyword_count = len(matched_keywords)
                    if keyword_count >= 2:  # 多个关键词匹配，提升权重
                        kw_score *= 1.2  # 提升20%
                    result['weighted_score'] = kw_score * 0.8  # 关键词搜索基础权重0.8
                    
                    if cid not in all_results:
                        all_results[cid] = result
                    else:
                        # 融合策略：如果关键词匹配度足够高，提升总分
                        existing = all_results[cid]
                        vec_score = existing.get('similarity', 0.0) * 1.0
                        # 如果关键词匹配度超过向量相似度的70%，进行加权融合
                        if kw_score > vec_score * 0.7:
                            # 加权融合：向量0.6 + 关键词0.4
                            fused_score = vec_score * 0.6 + kw_score * 0.4
                            existing['similarity'] = min(1.0, fused_score)
                            existing['weighted_score'] = fused_score
                            existing['source'] = 'hybrid'  # 标记为混合来源
                            existing['keyword_boost'] = True
                        # 如果关键词匹配度特别高（>0.8），直接使用关键词结果
                        elif kw_score > 0.8:
                            all_results[cid] = result
            
            # 3. 子查询向量搜索（如果拆解成功）
            if decomposed_terms:
                logger.info(f"开始子查询向量搜索，共 {len(decomposed_terms[:3])} 个子查询")
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                    sub_futures = [executor.submit(vector_search_sub, term) for term in decomposed_terms[:3]]
                    for future in concurrent.futures.as_completed(sub_futures):
                        sub_results = future.result()
                        for result in sub_results:
                            cid = result.get('chunk_id')
                            if cid:
                                # 子查询结果的权重稍低（乘以0.9）
                                result['similarity'] = result.get('similarity', 0.0) * 0.9
                                if cid not in all_results or result.get('similarity', 0.0) > all_results[cid].get('similarity', 0.0):
                                    all_results[cid] = result
                        logger.info(f"子查询完成，当前总结果数: {len(all_results)}")
            
            # 转换为列表并按加权分数排序（优先使用weighted_score，如果没有则使用similarity）
            search_results = list(all_results.values())
            search_results.sort(key=lambda x: x.get('weighted_score', x.get('similarity', 0.0)), reverse=True)
            
            logger.info(f"多路召回完成，总结果数: {len(search_results)} (向量: {len(vector_results)}, 关键词: {len(keyword_results)}, 子查询: {len(decomposed_terms[:3]) if decomposed_terms else 0})")
            
            # 如果启用了知识图谱，同时搜索相关三元组并增强搜索结果
            graph_results = []
            graph_enhanced_chunks = []
            if KNOWLEDGE_GRAPH_ENABLED:
                try:
                    # 使用多跳查询获取更丰富的关系信息
                    graph_results = self._multi_hop_triple_search(db, kb_id, query, max_hops=MULTI_HOP_MAX_HOPS)
                    logger.info(f"KB[{kb_id}] 多跳图谱搜索结果: {len(graph_results)} 个三元组")
                    
                    # 从图谱结果中提取相关分块ID，提升这些分块的排序
                    if graph_results:
                        # 提取图谱中涉及的分块ID
                        graph_chunk_ids = set()
                        for triple in graph_results:
                            # 从三元组中查找相关的分块
                            related_chunks = db.query(KnowledgeTriple).filter(
                                KnowledgeTriple.knowledge_base_id == kb_id
                            ).filter(
                                or_(
                                    KnowledgeTriple.subject == triple.get('subject', ''),
                                    KnowledgeTriple.object == triple.get('object', '')
                                )
                            ).all()
                            for chunk_rel in related_chunks:
                                if chunk_rel.chunk_id:
                                    graph_chunk_ids.add(chunk_rel.chunk_id)
                        
                        # 提升图谱相关分块的相似度
                        for result in search_results:
                            if result.get('chunk_id') in graph_chunk_ids:
                                # 提升相似度（增加0.1，但不超过1.0）
                                result['similarity'] = min(1.0, result.get('similarity', 0.0) + 0.1)
                                result['graph_boosted'] = True
                                graph_enhanced_chunks.append(result.get('chunk_id'))
                        
                        logger.info(f"KB[{kb_id}] 图谱增强了 {len(graph_enhanced_chunks)} 个分块的排序")
                except Exception as e:
                    logger.warning(f"知识图谱搜索失败: {str(e)}")
                    graph_results = []
            
            if not search_results:
                return {
                    "query": query,
                    "response": "知识库中没有找到相关文档。",
                    "sources": [],
                    "metadata": {"total_chunks": 0}
                }
            
            logger.info(f"KB[{kb_id}] 向量搜索候选数: {len(search_results)}，将取前N用于重排: {max(RERANKER_AFTER_TOP_N, effective_max)}，目标返回: {effective_max}")
            
            # 先取前N做重排序候选
            initial_top_n = search_results[:max(RERANKER_AFTER_TOP_N, effective_max)]
            logger.info(f"KB[{kb_id}] 重排候选数: {len(initial_top_n)}, 重排启用: {RERANKER_ENABLED_ENV}")
            
            # 组装候选用于重排序
            candidates: List[Dict[str, Any]] = []
            for result in initial_top_n:
                candidates.append({
                    "similarity": result.get("similarity", 0.0),
                    "content": result.get("content", ""),
                    "chunk_id": result.get("chunk_id"),
                    "document_id": result.get("document_id"),
                    "knowledge_base_id": kb_id,
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
            
            # 使用知识图谱服务增强上下文
            kg_enhancement = self.kg_service.enhance_rag_context(
                db=db,
                kb_id=kb_id,
                query=query,
                vector_results=search_results,
                max_triples=10
            )
            
            # 构建图谱上下文
            graph_context = kg_enhancement.get('graph_context', '')
            if not graph_context and graph_results:
                # 回退到旧的方法
                graph_context = "相关实体关系：\n"
                for triple in graph_results[:10]:  # 取前10个三元组
                    hop_info = f" (跳数: {triple.get('hop', 0)})" if 'hop' in triple else ""
                    graph_context += f"- {triple['subject']} {triple['predicate']} {triple['object']}{hop_info}\n"
            
            # 合并知识图谱增强的上下文
            if kg_enhancement.get('enhanced', False):
                graph_context = kg_enhancement['graph_context']
            
            response = self._generate_response(query, context, graph_context)
            
            return {
                "query": query,
                "response": response,
                "sources": sources,
                "query_processing": processed_query_info,
                "metadata": {
                    "total_chunks": len(search_results),
                    "initial_considered": len(initial_top_n),
                    "final_selected": len(final_sources),
                    "decomposed_terms": decomposed_terms,
                    "reranker_enabled": RERANKER_ENABLED_ENV,
                    "reranker_after_top_n": RERANKER_AFTER_TOP_N,
                    "reranker_top_k": RERANKER_TOP_K,
                    "vector_store_type": "database",
                    "knowledge_graph_enabled": KNOWLEDGE_GRAPH_ENABLED,
                    "graph_results_count": len(graph_results) if KNOWLEDGE_GRAPH_ENABLED else 0
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
            doc.kg_extraction_status = "pending"  # 初始化KG抽取状态
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
            
            # 创建分块记录和向量存储
            logger.info(f"开始创建分块记录: {doc.name}")
            
            # 准备批量处理数据
            chunk_contents = []
            chunk_metadata_list = []
            strategy_variant = f"cs_{self.text_processor.chunk_size}_ov_{self.text_processor.overlap}"
            
            for i, chunk_content in enumerate(chunks):
                chunk_metadata = {
                    "chunk_index": i,
                    "chunk_size": len(chunk_content),
                    "document_id": doc.id,
                    "knowledge_base_id": doc.knowledge_base_id,
                    "content": chunk_content
                }
                # 三元组抽取将在后台异步进行，这里不再同步处理
                chunk_contents.append(chunk_content)
                chunk_metadata_list.append(chunk_metadata)
            
            # 批量生成嵌入向量
            logger.info(f"批量生成 {len(chunk_contents)} 个分块的嵌入向量...")
            embeddings = self.embedding_service.batch_get_embeddings(chunk_contents)
            
            # 向量数据直接存储在数据库中，不需要额外的向量存储
            
            # 创建数据库记录
            created_chunks: List[DocumentChunk] = []
            for i, (chunk_content, embedding, metadata) in enumerate(zip(chunk_contents, embeddings, chunk_metadata_list)):
                try:
                    chunk = DocumentChunk(
                        knowledge_base_id=doc.knowledge_base_id,
                        document_id=doc.id,
                        chunk_index=i,
                        content=chunk_content,
                        embedding=embedding,
                        chunk_metadata=metadata,
                        chunk_strategy=CHUNK_STRATEGY,
                        strategy_variant=strategy_variant,
                        kg_extraction_status="pending"  # 初始状态，等待后台处理
                    )
                    db.add(chunk)
                    db.flush()  # 获取chunk.id
                    created_chunks.append(chunk)
                    
                    logger.info(f"第{i+1}个分块创建成功")
                    
                except Exception as e:
                    logger.error(f"创建第{i+1}个分块失败: {str(e)}")
                    continue
            
            # 提交所有分块
            db.commit()
            
            # 更新文档状态为分块完成（三元组抽取将在后台异步进行）
            doc.status = "chunked"  # 新增状态：分块完成但三元组未抽取
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["chunk_count"] = len(chunks)
            doc.document_metadata["processing_time"] = datetime.utcnow().isoformat()
            db.commit()
            
            # 提交后台任务：异步抽取三元组
            if EXTRACT_TRIPLES_ENABLED:
                try:
                    from services.kg_extraction_worker import get_kg_worker
                    kg_worker = get_kg_worker()
                    kg_worker.submit_document_extraction(doc.id)
                    logger.info(f"已提交文档 {doc.id} 的三元组抽取后台任务")
                except Exception as e:
                    logger.error(f"提交三元组抽取任务失败: {str(e)}", exc_info=True)
                    # 即使提交失败，也不影响分块完成状态

            # 文档级别领域识别（随机抽样分片）
            if DOMAIN_CLASSIFY_ENABLED and created_chunks:
                try:
                    sample_size = min(5, len(created_chunks))
                    import random
                    samples = random.sample(created_chunks, sample_size)
                    sample_text = "\n\n".join([c.content[:500] for c in samples])
                    domain_label, domain_conf = self._classify_domain_via_llm(sample_text)
                    # 写回所有分片的领域信息
                    for c in created_chunks:
                        c.domain = domain_label
                        c.domain_confidence = domain_conf
                    db.commit()
                    logger.info(f"领域识别: {domain_label}({domain_conf:.2f}) 应用于 {len(created_chunks)} 个分片")
                except Exception as e:
                    logger.warning(f"领域识别失败: {str(e)}")

            # 为可识别章节/长内容生成摘要分片（批量处理，减少LLM调用）
            if SUMMARY_CHUNKS_ENABLED and created_chunks:
                try:
                    # 收集需要生成摘要的分块（使用规则筛选，避免每个都调用LLM）
                    chunks_to_summarize = []
                    for c in created_chunks:
                        # 启发式规则：只对明显的长章节或重要内容生成摘要
                        is_long_chunk = len(c.content) >= max(1000, self.text_processor.chunk_size * 2)  # 至少是目标大小的2倍
                        has_chapter_marker = re.search(r"^第[一二三四五六七八九十\d]+[章节回]", c.content.strip())
                        # 只对满足条件的分块生成摘要
                        if is_long_chunk or has_chapter_marker:
                            chunks_to_summarize.append(c)
                    
                    # 批量生成摘要（每批处理多个，减少LLM调用次数）
                    if chunks_to_summarize:
                        logger.info(f"准备为 {len(chunks_to_summarize)} 个分块生成摘要（批量处理）")
                        # 限制最大摘要数量，避免过多LLM调用
                        max_summaries = min(10, len(chunks_to_summarize))  # 最多生成10个摘要
                        chunks_to_summarize = chunks_to_summarize[:max_summaries]
                        
                        for c in chunks_to_summarize:
                            try:
                                # 使用简化的摘要方法（提取关键句子，而不是完整LLM生成）
                                summary = self._generate_chunk_summary_simple(c.content)
                                if summary and len(summary) > 30:
                                    summary_chunk = DocumentChunk(
                                        knowledge_base_id=doc.knowledge_base_id,
                                        document_id=doc.id,
                                        chunk_index=c.chunk_index,
                                        content=summary,
                                        embedding=None,
                                        chunk_metadata={"summary_of": c.id, "method": "rule_based"},
                                        chunk_strategy=CHUNK_STRATEGY,
                                        strategy_variant=strategy_variant,
                                        is_summary=True,
                                        summary_parent_chunk_id=c.id
                                    )
                                    db.add(summary_chunk)
                            except Exception as e:
                                logger.warning(f"为分块 {c.id} 生成摘要失败: {str(e)}")
                                continue
                        
                        db.commit()
                        logger.info(f"成功生成 {len(chunks_to_summarize)} 个摘要分片")
                except Exception as e:
                    logger.warning(f"摘要分片生成失败: {str(e)}")
            
            db.commit()
            
            logger.info(f"文档处理完成: {doc.name}, 分块数: {len(chunks)}")
            
        except Exception as e:
            logger.error(f"文档处理失败: {doc.name}, 错误: {str(e)}")
            doc.status = "failed"
            doc.document_metadata = doc.document_metadata or {}
            doc.document_metadata["error"] = str(e)
            db.commit()
    
    def _classify_domain_via_llm(self, text: str) -> tuple[str, float]:
        """使用LLM对文本进行领域分类，返回(领域, 置信度0-1)。"""
        try:
            from utils.llm_helper import get_llm_helper
            import asyncio
            import concurrent.futures
            import re
            
            # 更具体的领域分类
            categories = [
                "技术/计算机", "小说/文学", "财经/商业", "法律/政策", "医学/健康", "教育/学术",
                "历史/文化", "新闻/时政", "旅游/地理", "体育/运动", "艺术/娱乐", "其他"
            ]
            
            # 改进的提示词
            prompt = f"""请分析以下文本内容，判断其主要属于哪个领域。

文本内容：
{text[:1500]}

可选领域：{', '.join(categories)}

请按以下格式回答：
领域：具体领域名称
置信度：0.0-1.0之间的数字

分析要点：
- 技术/计算机：编程、软件、硬件、AI、算法等
- 小说/文学：故事、小说、诗歌、文学创作等
- 财经/商业：经济、金融、商业、投资等
- 法律/政策：法律法规、政策文件、法律案例等
- 医学/健康：医疗、健康、疾病、药物等
- 教育/学术：教学、研究、学术论文、教育等
- 历史/文化：历史事件、文化传统、考古等
- 新闻/时政：新闻报道、时事政治、社会事件等
- 旅游/地理：旅游、地理、风景、城市等
- 体育/运动：体育赛事、运动、健身等
- 艺术/娱乐：音乐、绘画、电影、娱乐等"""

            def run_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    llm = get_llm_helper()
                    messages = [
                        {"role": "system", "content": "你是一个专业的文本领域分类专家，能够准确识别文本内容的主要领域。"},
                        {"role": "user", "content": prompt}
                    ]
                    return loop.run_until_complete(llm.call(messages, max_tokens=200, temperature=0.1))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as ex:
                result = ex.submit(run_async).result()
            
            # 改进的解析逻辑
            result_text = str(result).strip()
            logger.info(f"LLM分类结果: {result_text}")
            
            # 提取领域
            domain_match = re.search(r'领域[：:]\s*([^\n\r]+)', result_text)
            if domain_match:
                domain = domain_match.group(1).strip()
                # 验证领域是否在预定义列表中
                if domain not in categories:
                    # 尝试模糊匹配
                    for cat in categories:
                        if cat in domain or domain in cat:
                            domain = cat
                            break
                    else:
                        domain = "其他"
            else:
                domain = "其他"
            
            # 提取置信度
            conf_match = re.search(r'置信度[：:]\s*([0-9.]+)', result_text)
            if conf_match:
                try:
                    conf = float(conf_match.group(1))
                except ValueError:
                    conf = 0.6
            else:
                conf = 0.6
            
            # 确保置信度在合理范围内
            conf = max(0.0, min(conf, 1.0))
            
            logger.info(f"解析结果: 领域={domain}, 置信度={conf}")
            return domain, conf
            
        except Exception as e:
            logger.warning(f"LLM领域分类失败: {str(e)}，使用关键词分类")
            return self._classify_domain_by_keywords(text)
    
    def _classify_domain_by_keywords(self, text: str) -> tuple[str, float]:
        """基于关键词的领域分类（LLM不可用时的备用方案）"""
        import re
        
        # 扩展的关键词映射，包含更多常见词汇
        keyword_mapping = {
            "技术/计算机": [
                "人工智能", "AI", "机器学习", "深度学习", "算法", "编程", "软件", "硬件", 
                "计算机", "网络", "数据", "代码", "程序", "系统", "技术", "开发", "工程师",
                "神经网络", "CNN", "RNN", "Python", "Java", "C++", "数据库", "API", "智能",
                "自动化", "数字化", "云计算", "大数据", "物联网", "区块链", "虚拟现实", "VR",
                "增强现实", "AR", "机器人", "芯片", "处理器", "内存", "存储", "服务器", "客户端"
            ],
            "小说/文学": [
                "第一章", "第二章", "第三章", "第四章", "第五章", "故事", "小说", "诗歌", "文学", 
                "主人公", "情节", "角色", "作者", "作品", "创作", "文学", "艺术", "想象", "虚构", 
                "人物", "主角", "配角", "情节", "故事", "章节", "段落", "描写", "叙述", "对话",
                "情感", "爱情", "友情", "亲情", "冒险", "悬疑", "科幻", "奇幻", "历史", "传记"
            ],
            "财经/商业": [
                "公司", "企业", "收入", "利润", "投资", "股票", "市场", "经济", "金融", "商业",
                "财务", "资金", "成本", "收益", "增长", "业绩", "财报", "股价", "市值", "银行",
                "贷款", "信贷", "保险", "基金", "债券", "期货", "外汇", "汇率", "通胀", "通缩",
                "GDP", "CPI", "PPI", "就业", "失业", "工资", "薪酬", "福利", "税收", "财政"
            ],
            "法律/政策": [
                "法律", "法规", "政策", "条例", "规定", "条款", "法院", "判决", "律师", "案件",
                "违法", "合法", "权利", "义务", "责任", "政府", "部门", "管理", "宪法", "刑法",
                "民法", "商法", "劳动法", "合同法", "知识产权", "专利", "商标", "版权", "诉讼",
                "仲裁", "调解", "审判", "执行", "监管", "执法", "立法", "司法", "行政"
            ],
            "医学/健康": [
                "疾病", "健康", "医疗", "医生", "患者", "治疗", "药物", "症状", "诊断", "医院",
                "血压", "血糖", "手术", "康复", "预防", "保健", "医学", "临床", "病理", "生理",
                "心理", "精神", "神经", "心血管", "呼吸", "消化", "泌尿", "生殖", "内分泌",
                "免疫", "感染", "病毒", "细菌", "炎症", "肿瘤", "癌症", "化疗", "放疗", "手术"
            ],
            "教育/学术": [
                "研究", "学术", "教育", "学习", "教学", "学生", "老师", "学校", "大学", "论文",
                "实验", "数据", "分析", "方法", "理论", "知识", "课程", "考试", "教材", "课本",
                "课堂", "讲座", "研讨会", "会议", "期刊", "发表", "引用", "参考文献", "学位",
                "硕士", "博士", "教授", "副教授", "讲师", "助教", "导师", "指导", "培养"
            ],
            "历史/文化": [
                "历史", "古代", "传统", "文化", "文明", "朝代", "皇帝", "战争", "事件", "考古",
                "文物", "古迹", "传说", "神话", "民俗", "节日", "春节", "中秋", "端午", "清明",
                "重阳", "元宵", "七夕", "腊八", "习俗", "礼仪", "道德", "伦理", "哲学", "思想",
                "宗教", "佛教", "道教", "基督教", "伊斯兰教", "寺庙", "教堂", "清真寺", "信仰"
            ],
            "新闻/时政": [
                "新闻", "报道", "事件", "政治", "政府", "会议", "政策", "社会", "发展", "改革",
                "领导人", "国家", "国际", "外交", "安全", "民生", "选举", "投票", "民主", "自由",
                "平等", "公正", "法治", "人权", "环保", "可持续发展", "全球化", "区域合作",
                "贸易", "投资", "合作", "竞争", "冲突", "和平", "稳定", "繁荣", "进步"
            ],
            "旅游/地理": [
                "旅游", "景点", "风景", "城市", "地理", "地方", "旅行", "度假", "酒店", "交通",
                "气候", "环境", "自然", "山水", "建筑", "文化", "名胜", "古迹", "公园", "博物馆",
                "展览", "演出", "表演", "美食", "特产", "购物", "娱乐", "休闲", "度假村", "民宿",
                "导游", "旅行社", "机票", "火车", "汽车", "轮船", "飞机", "高铁", "地铁"
            ],
            "体育/运动": [
                "体育", "运动", "比赛", "运动员", "训练", "健身", "足球", "篮球", "游泳", "跑步",
                "奥运会", "冠军", "记录", "竞技", "团队", "个人", "集体", "技巧", "力量", "速度",
                "耐力", "柔韧", "协调", "平衡", "反应", "战术", "策略", "教练", "裁判", "观众",
                "球迷", "粉丝", "支持", "鼓励", "加油", "胜利", "失败", "成功", "挑战", "突破"
            ],
            "艺术/娱乐": [
                "艺术", "音乐", "绘画", "电影", "娱乐", "表演", "创作", "作品", "艺术家", "文化",
                "娱乐", "游戏", "节目", "演出", "展览", "音乐会", "演唱会", "戏剧", "话剧", "歌剧",
                "芭蕾", "舞蹈", "雕塑", "摄影", "设计", "时尚", "服装", "美容", "化妆", "发型",
                "美食", "烹饪", "料理", "餐厅", "咖啡", "茶", "酒", "饮料", "甜点", "零食"
            ]
        }
        
        text_lower = text.lower()
        scores = {}
        matched_details = {}
        
        for domain, keywords in keyword_mapping.items():
            score = 0
            matched_keywords = []
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    score += 1
                    matched_keywords.append(keyword)
            scores[domain] = score
            matched_details[domain] = matched_keywords
        
        # 找到得分最高的领域
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                best_domain = max(scores, key=scores.get)
                # 改进置信度计算：基于匹配关键词数量和文本长度
                confidence = min(0.9, max(0.3, max_score / max(3.0, len(text) / 100)))
                logger.info(f"关键词分类: {best_domain}, 匹配关键词: {matched_details[best_domain]}, 置信度: {confidence:.2f}")
                return best_domain, confidence
        
        logger.info(f"关键词分类: 其他, 文本长度: {len(text)}")
        return "其他", 0.3

    def _generate_chunk_summary_simple(self, text: str) -> str:
        """使用基于规则的方法生成摘要（不调用LLM，快速且低成本）"""
        try:
            # 方法1：提取前几句和后几句，以及包含关键词的句子
            sentences = re.split(r'[。！？\n]', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            
            if len(sentences) <= 3:
                return text[:300]  # 如果句子很少，直接返回前300字符
            
            # 提取前2句和后1句
            summary_parts = []
            if len(sentences) >= 2:
                summary_parts.extend(sentences[:2])
            if len(sentences) >= 3:
                summary_parts.append(sentences[-1])
            
            # 查找包含重要关键词的句子（如：总结、结论、因此、所以等）
            important_keywords = ['总结', '结论', '因此', '所以', '总之', '综上所述', '关键', '重要', '主要']
            for sentence in sentences[2:-1] if len(sentences) > 3 else []:
                if any(keyword in sentence for keyword in important_keywords):
                    if sentence not in summary_parts:
                        summary_parts.insert(-1, sentence)  # 插入到倒数第二位置
                        if len(summary_parts) >= 5:  # 最多5句
                            break
            
            summary = '。'.join(summary_parts) + '。'
            
            # 限制长度
            if len(summary) > 300:
                summary = summary[:300] + '...'
            
            return summary
        except Exception as e:
            logger.warning(f"生成摘要失败: {str(e)}")
            # 降级：简单截取
            return text[:300] + '...' if len(text) > 300 else text
    
    def _summarize_chunk_via_llm(self, text: str) -> str:
        """使用LLM对长分片/章节生成摘要（仅在必要时调用，已弃用，改用 _generate_chunk_summary_simple）"""
        # 保留此方法以向后兼容，但默认不再使用
        logger.warning("_summarize_chunk_via_llm 已弃用，请使用 _generate_chunk_summary_simple")
        return self._generate_chunk_summary_simple(text)

    def _decompose_query_terms(self, query: str) -> List[str]:
        """使用LLM将查询拆解为3-5个关键词或子问题，返回词列表。"""
        try:
            from utils.llm_helper import get_llm_helper
            import asyncio
            import concurrent.futures
            import re
            
            prompt = (
                "请将以下问题拆解为3-5个中文关键词或子问题，每行一个，不要编号，直接输出关键词：\n\n" + query
            )

            def run_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    llm = get_llm_helper()
                    messages = [
                        {"role": "system", "content": "你是检索优化助手，负责将查询拆解为关键词或子问题以提升召回。只输出关键词，每行一个，不要编号、不要解释。"},
                        {"role": "user", "content": prompt}
                    ]
                    return loop.run_until_complete(llm.call(messages, max_tokens=128, temperature=0.0))
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as ex:
                result = ex.submit(run_async).result(timeout=10)
            
            result_str = str(result).strip()
            # 提取中文关键词（2-20个字符）
            lines = re.findall(r'[\u4e00-\u9fa5]{2,20}', result_str)
            
            # 如果LLM返回的是列表格式，也尝试解析
            if not lines:
                # 尝试按行分割
                lines = [l.strip('- ').strip().strip('1234567890.）)').strip() 
                        for l in result_str.splitlines() if l.strip()]
                # 过滤过短内容和只保留中文
                lines = [l for l in lines if len(l) >= 2 and re.match(r'^[\u4e00-\u9fa5]+$', l)]
            
            # 如果还是没有结果，使用简单的关键词提取作为后备
            if not lines:
                # 提取查询中的关键词（去除停用词）
                stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '什么', '怎么', '如何', '为什么'}
                keywords = re.findall(r'[\u4e00-\u9fa5]{2,10}', query)
                lines = [kw for kw in keywords if kw not in stopwords and len(kw) >= 2][:5]
            
            logger.info(f"查询拆解成功: {lines[:5]}")
            return lines[:5]
        except Exception as e:
            logger.warning(f"LLM查询拆解失败: {str(e)}，使用简单关键词提取")
            # 后备方案：简单关键词提取
            import re
            stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '什么', '怎么', '如何', '为什么'}
            keywords = re.findall(r'[\u4e00-\u9fa5]{2,10}', query)
            return [kw for kw in keywords if kw not in stopwords and len(kw) >= 2][:5]

    def _extract_triples_sync(self, text: str) -> List[List[str]]:
        """使用LLM从文本中抽取(主语, 关系, 宾语)三元组，返回列表。
        同步封装，内部以异步方式调用模型。
        """
        prompt = (
            "请从以下文本中提取所有可能的实体和关系，以三元组的形式输出（主语，关系，宾语）。\n"
            "要求：\n"
            "1. 提取所有可能的三元组，不要遗漏\n"
            "2. 每个三元组一行，格式：主语，关系，宾语\n"
            "3. 只输出三元组，不要其他解释\n"
            "4. 如果文本中没有明确的关系，可以推断隐含关系\n"
            "5. 实体可以是人名、地名、机构名、概念等\n"
            "6. 关系可以是动作、属性、位置、时间等\n\n"
            "文本：\n" + text
        )

        async def _run() -> str:
            llm = get_llm_helper()
            messages = [
                {"role": "system", "content": "你是一个专业的实体关系抽取专家，能够从文本中准确识别和提取所有可能的实体关系三元组。你擅长识别各种类型的实体（人名、地名、机构、概念、时间等）和关系（动作、属性、位置、时间、因果等）。"},
                {"role": "user", "content": prompt}
            ]
            return await llm.call(messages, max_tokens=1024, temperature=0.0)

        # 在同步环境中执行异步调用
        result = asyncio.run(_run())
        return self._parse_triples(result)

    def _parse_triples(self, text: str) -> List[List[str]]:
        """解析LLM返回的三元组文本，每行一个三元组，支持多种格式。"""
        triples: List[List[str]] = []
        if not text:
            return triples
        
        lines = [l.strip() for l in str(text).splitlines() if l.strip()]
        
        for line in lines:
            # 跳过非三元组行（如序号、标题等）
            if re.match(r'^\d+[\.\)]', line) or line.startswith('-') or line.startswith('*'):
                line = re.sub(r'^\d+[\.\)]\s*', '', line)  # 去掉序号
                line = re.sub(r'^[-*]\s*', '', line)  # 去掉列表符号
            
            # 去掉可能的括号和全角符号
            cleaned = line.strip().strip("()（）[]【】")
            
            # 跳过空行或太短的行
            if len(cleaned) < 5:
                continue
            
            # 尝试多种分隔符模式
            patterns = [
                r"[，,、]\s*",  # 逗号分隔
                r"\s+",         # 空格分隔
                r"\t+",         # 制表符分隔
                r"\s*-\s*",     # 破折号分隔
                r"\s*→\s*",     # 箭头分隔
                r"\s*->\s*",    # 箭头分隔
            ]
            
            parts = []
            for pattern in patterns:
                parts = [p.strip().strip("\"'""") for p in re.split(pattern, cleaned) if p.strip()]
                if len(parts) >= 3:
                    break
            
            # 如果还是不够3个部分，尝试按长度分割
            if len(parts) < 3 and len(cleaned) > 10:
                # 尝试找到关系词（动词、介词等）
                relation_words = ['是', '有', '在', '属于', '包含', '位于', '来自', '去', '到', '与', '和', '的', '为', '做', '进行', '实现', '完成']
                for word in relation_words:
                    if word in cleaned:
                        parts = cleaned.split(word, 1)
                        if len(parts) == 2:
                            # 进一步分割主语和宾语
                            subject = parts[0].strip()
                            obj_part = parts[1].strip()
                            # 尝试分割宾语
                            obj_parts = re.split(r'[，,、\s]+', obj_part, 1)
                            if len(obj_parts) >= 2:
                                relation = word
                                obj = obj_parts[0].strip()
                                parts = [subject, relation, obj]
                                break
            
            if len(parts) >= 3:
                # 清理和验证三元组
                subject = parts[0].strip()
                relation = parts[1].strip()
                obj = parts[2].strip()
                
                # 基本验证：不能为空，不能太短
                if (len(subject) > 0 and len(relation) > 0 and len(obj) > 0 and
                    len(subject) < 100 and len(relation) < 50 and len(obj) < 100):
                    triples.append([subject, relation, obj])
        
        logger.info(f"解析得到 {len(triples)} 个三元组")
        return triples
    
    def _store_triples_to_db(self, db: Session, kb_id: int, doc_id: int, chunk_index: int, 
                            triples: List[List[str]], source_text: str):
        """将三元组存储到数据库"""
        try:
            for triple in triples:
                if len(triple) >= 3:
                    triple_data = KnowledgeTripleCreate(
                        knowledge_base_id=kb_id,
                        document_id=doc_id,
                        chunk_id=None,  # 稍后更新
                        subject=triple[0].strip(),
                        predicate=triple[1].strip(),
                        object=triple[2].strip(),
                        confidence=1.0,
                        source_text=source_text[:200]  # 截取前200字符作为来源
                    )
                    
                    triple_record = KnowledgeTriple(**triple_data.model_dump())
                    db.add(triple_record)
            
            logger.info(f"成功存储 {len(triples)} 个三元组到数据库")
            
        except Exception as e:
            logger.error(f"存储三元组到数据库失败: {str(e)}")
    
    def _update_triple_chunk_ids(self, db: Session, doc_id: int):
        """更新三元组的chunk_id关联"""
        try:
            # 获取该文档的所有分块
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc_id
            ).order_by(DocumentChunk.chunk_index).all()
            
            # 获取该文档的所有三元组
            triples = db.query(KnowledgeTriple).filter(
                KnowledgeTriple.document_id == doc_id,
                KnowledgeTriple.chunk_id.is_(None)
            ).all()
            
            # 为每个三元组分配对应的chunk_id
            for triple in triples:
                if triple.chunk_index is not None and triple.chunk_index < len(chunks):
                    triple.chunk_id = chunks[triple.chunk_index].id
            
            db.commit()
            logger.info(f"更新了 {len(triples)} 个三元组的chunk_id关联")
            
        except Exception as e:
            logger.error(f"更新三元组chunk_id失败: {str(e)}")
    
    def _search_triples_from_db(self, db: Session, kb_id: int, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """从数据库搜索相关三元组（改进版：支持事件查询和实体提取）"""
        try:
            import re
            
            # 1. 检查是否是事件参与者查询（"X的是谁"模式）
            event_query_pattern = r"(.+?)的是谁"
            event_match = re.search(event_query_pattern, query)
            if event_match:
                event_name = event_match.group(1).strip()
                logger.info(f"检测到事件参与者查询: {event_name}")
                
                # 使用知识图谱服务查询事件参与者
                event_participants = self.kg_service.query_event_participants(db, kb_id, event_name, limit=limit)
                if event_participants:
                    # 转换为标准格式
                    results = []
                    for participant_info in event_participants:
                        results.append({
                            'subject': participant_info['participant'],
                            'predicate': participant_info['relation'],
                            'object': participant_info['event'],
                            'confidence': participant_info['confidence'],
                            'source_text': participant_info.get('source_text', ''),
                            'chunk_id': participant_info.get('chunk_id'),
                            'document_id': participant_info.get('document_id'),
                            'relevance_score': participant_info['confidence'] + 0.3  # 事件查询结果权重更高
                        })
                    logger.info(f"通过事件查询找到 {len(results)} 个参与者")
                    return results
            
            # 2. 普通实体查询（原有逻辑）
            # 从查询中提取实体（2-10个字符的中文词）
            query_entities = re.findall(r'[\u4e00-\u9fa5]{2,10}', query)
            query_entities = [e for e in query_entities if len(e) >= 2][:5]  # 最多5个实体
            
            if not query_entities:
                # 如果没有提取到实体，使用原始查询
                query_entities = [query]
            
            logger.debug(f"从查询中提取的实体: {query_entities}")
            
            # 使用OR条件匹配多个实体
            conditions = []
            for entity in query_entities:
                conditions.append(KnowledgeTriple.subject.contains(entity))
                conditions.append(KnowledgeTriple.predicate.contains(entity))
                conditions.append(KnowledgeTriple.object.contains(entity))
            
            if conditions:
                triples = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == kb_id,
                    or_(*conditions)
                ).order_by(KnowledgeTriple.confidence.desc()).limit(limit * 2).all()  # 获取更多候选
            else:
                return []
            
            # 计算每个三元组的相关性分数
            scored_triples = []
            for triple in triples:
                score = triple.confidence or 0.5
                # 如果实体在subject或object中，分数更高
                for entity in query_entities:
                    if entity in triple.subject or entity in triple.object:
                        score += 0.2
                    elif entity in triple.predicate:
                        score += 0.1
                
                scored_triples.append({
                    'subject': triple.subject,
                    'predicate': triple.predicate,
                    'object': triple.object,
                    'confidence': min(1.0, score),
                    'source_text': triple.source_text,
                    'chunk_id': triple.chunk_id,
                    'document_id': triple.document_id,
                    'relevance_score': score
                })
            
            # 按相关性排序并返回top_k
            scored_triples.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            results = scored_triples[:limit]
            logger.debug(f"找到 {len(results)} 个相关三元组")
            return results
            
        except Exception as e:
            logger.error(f"数据库三元组搜索失败: {str(e)}")
            return []
    
    def _multi_hop_triple_search(self, db: Session, kb_id: int, query: str, max_hops: int = 2) -> List[Dict[str, Any]]:
        """多跳关系查询"""
        try:
            # 第一步：找到与查询直接相关的三元组
            direct_triples = self._search_triples_from_db(db, kb_id, query, limit=20)
            
            if not direct_triples:
                return []
            
            all_triples = direct_triples.copy()
            visited_entities = set()
            
            # 收集所有相关实体
            for triple in direct_triples:
                visited_entities.add(triple['subject'])
                visited_entities.add(triple['object'])
            
            # 多跳搜索
            for hop in range(1, max_hops + 1):
                new_triples = []
                current_entities = list(visited_entities)
                
                for entity in current_entities:
                    # 搜索包含该实体的其他三元组
                    entity_triples = db.query(KnowledgeTriple).filter(
                        KnowledgeTriple.knowledge_base_id == kb_id
                    ).filter(
                        or_(
                            KnowledgeTriple.subject == entity,
                            KnowledgeTriple.object == entity
                        )
                    ).limit(10).all()
                    
                    for triple in entity_triples:
                        triple_dict = {
                            'subject': triple.subject,
                            'predicate': triple.predicate,
                            'object': triple.object,
                            'confidence': triple.confidence,
                            'source_text': triple.source_text,
                            'chunk_id': triple.chunk_id,
                            'document_id': triple.document_id,
                            'hop': hop
                        }
                        
                        # 避免重复
                        if not any(t['subject'] == triple.subject and 
                                 t['predicate'] == triple.predicate and 
                                 t['object'] == triple.object for t in all_triples):
                            new_triples.append(triple_dict)
                            all_triples.append(triple_dict)
                            
                            # 添加新发现的实体
                            visited_entities.add(triple.subject)
                            visited_entities.add(triple.object)
                
                if not new_triples:
                    break
            
            # 按置信度和跳数排序
            all_triples.sort(key=lambda x: (x.get('hop', 0), -x['confidence']))
            
            logger.info(f"多跳查询完成: {len(all_triples)} 个三元组, {len(visited_entities)} 个实体")
            return all_triples[:50]  # 限制返回数量
            
        except Exception as e:
            logger.error(f"多跳关系查询失败: {str(e)}")
            return direct_triples  # 回退到直接搜索
    
    def _find_related_entities(self, db: Session, kb_id: int, entity: str, max_hops: int = 2) -> List[Dict[str, Any]]:
        """查找与指定实体相关的其他实体（多跳查询）"""
        try:
            related_entities = set()
            visited = set()
            current_entities = {entity}
            
            for hop in range(max_hops):
                if not current_entities:
                    break
                    
                next_entities = set()
                
                for current_entity in current_entities:
                    if current_entity in visited:
                        continue
                    visited.add(current_entity)
                    
                    # 查找包含当前实体的三元组
                    triples = db.query(KnowledgeTriple).filter(
                        KnowledgeTriple.knowledge_base_id == kb_id,
                        or_(
                            KnowledgeTriple.subject == current_entity,
                            KnowledgeTriple.object == current_entity
                        )
                    ).all()
                    
                    for triple in triples:
                        related_entities.add(triple.subject)
                        related_entities.add(triple.object)
                        
                        if hop < max_hops - 1:
                            if triple.subject != current_entity:
                                next_entities.add(triple.subject)
                            if triple.object != current_entity:
                                next_entities.add(triple.object)
                
                current_entities = next_entities
            
            # 移除原始实体
            related_entities.discard(entity)
            
            return list(related_entities)
            
        except Exception as e:
            logger.error(f"多跳实体查询失败: {str(e)}")
            return []
    
    def _generate_response(self, query: str, context: str, graph_context: str = "") -> str:
        """生成响应"""
        try:
            # 尝试使用LLM生成响应
            from utils.llm_helper import get_llm_helper
            llm_helper = get_llm_helper()
            
            # 构建提示词
            # 先构建关系图谱部分（避免在 f-string 表达式中使用反斜杠）
            graph_section = ""
            if graph_context:
                graph_section = f"关系图谱信息：\n{graph_context}\n"
            
            # 构建第6条要求（如果需要）
            requirement_6 = ""
            if graph_context:
                requirement_6 = "\n6. 可以利用关系图谱信息进行推理和关联分析"
            
            prompt = f"""基于以下知识库内容回答用户问题：

用户问题：{query}

知识库内容：
{context}

{graph_section}请基于知识库内容提供准确、详细的回答。如果知识库内容不足以回答问题，请说明并建议用户提供更多信息。

回答要求：
1. 基于知识库内容，不要编造信息
2. 回答要准确、详细、有条理
3. 如果涉及多个要点，请分点说明
4. 如果知识库内容不足，请诚实说明
5. 使用中文回答{requirement_6}

回答："""
            
            # 生成响应
            import asyncio
            import threading
            import concurrent.futures
            
            def run_async_in_thread():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(llm_helper.call(prompt))
                finally:
                    new_loop.close()
            
            # 使用线程池执行异步调用
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async_in_thread)
                response = future.result()
            
            if response and len(response.strip()) > 10:
                return response.strip()
            else:
                # LLM生成失败，使用简单摘要
                return self._generate_simple_response(query, context)
                
        except Exception as e:
            logger.error(f"LLM生成响应失败: {str(e)}")
            # 回退到简单摘要
            return self._generate_simple_response(query, context)
    
    def _generate_simple_response(self, query: str, context: str) -> str:
        """生成简单响应（回退方案）"""
        if len(context) > 1000:
            context = context[:1000] + "..."
        
        return f"基于知识库内容，为您提供以下信息：\n\n{context}\n\n如果您需要更详细的信息，请提供更具体的查询。"
