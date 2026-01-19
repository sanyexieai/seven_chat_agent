# -*- coding: utf-8 -*-
"""
知识图谱服务 - 支持RAG的知识图谱构建和查询
"""
import os
import re
import asyncio
import concurrent.futures
import random
import json
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from models.database_models import KnowledgeTriple, DocumentChunk, KnowledgeBase, HighFrequencyEntity
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper
from utils.embedding_service import EmbeddingService

logger = get_logger("knowledge_graph_service")

# 配置
KG_EXTRACT_ENABLED = os.getenv("KG_EXTRACT_ENABLED", "true").lower() == "true"
KG_ENTITY_LINKING_ENABLED = os.getenv("KG_ENTITY_LINKING_ENABLED", "true").lower() == "true"
KG_MAX_HOPS = int(os.getenv("KG_MAX_HOPS", "3"))
KG_TOP_ENTITIES = int(os.getenv("KG_TOP_ENTITIES", "10"))
# 抽取模式：llm / rule / hybrid / model / ner_rule（默认模型：使用NER+RE小模型）
# hybrid: 规则优先，规则结果不足时才可选调用LLM（默认关闭LLM回退以保证速度）
KG_EXTRACT_MODE = os.getenv("KG_EXTRACT_MODE", "hybrid").lower()
# 是否允许在hybrid模式下使用LLM做三元组补充（默认关闭，避免拖慢知识库处理）
KG_LLM_FALLBACK_ENABLED = os.getenv("KG_LLM_FALLBACK_ENABLED", "false").lower() == "true"
# 动态规则生成配置
KG_DYNAMIC_RULES_ENABLED = os.getenv("KG_DYNAMIC_RULES_ENABLED", "true").lower() == "true"  # 是否启用动态规则生成
KG_SAMPLE_TEXT_LENGTH = int(os.getenv("KG_SAMPLE_TEXT_LENGTH", "2000"))  # 采样文本长度
KG_SAMPLE_METHOD = os.getenv("KG_SAMPLE_METHOD", "mixed").lower()  # 采样方法：fixed（固定开头）、random（随机）、mixed（混合）
KG_DYNAMIC_RULES_RETRY_COUNT = int(os.getenv("KG_DYNAMIC_RULES_RETRY_COUNT", "3"))  # 动态规则生成重试次数
KG_DYNAMIC_RULES_RETRY_DELAY = float(os.getenv("KG_DYNAMIC_RULES_RETRY_DELAY", "1.0"))  # 重试延迟（秒）


class KnowledgeGraphService:
    """知识图谱服务 - 提供实体提取、关系抽取、图谱查询等功能"""
    
    # 全局线程池（避免在解释器关闭时创建新线程池）
    _executor = None
    _executor_lock = threading.Lock()
    
    # 文档级别的分析和规则缓存（doc_id -> {analysis, dynamic_rules}）
    _document_cache: Dict[int, Dict[str, Any]] = {}
    _cache_lock = threading.Lock()
    
    @classmethod
    def _get_executor(cls):
        """获取或创建全局线程池"""
        # 检查现有线程池是否可用
        if cls._executor is not None:
            # 检查线程池是否已关闭
            if cls._executor._shutdown:
                logger.warning("线程池已关闭，重新创建")
                cls._executor = None
        
        if cls._executor is None:
            with cls._executor_lock:
                # 双重检查
                if cls._executor is None or (cls._executor is not None and cls._executor._shutdown):
                    try:
                        cls._executor = concurrent.futures.ThreadPoolExecutor(
                            max_workers=2, 
                            thread_name_prefix="kg_llm"
                        )
                        logger.debug("创建新的全局线程池用于LLM调用")
                    except RuntimeError as e:
                        # 解释器正在关闭，返回None
                        logger.warning(f"无法创建线程池: {str(e)}")
                        return None
        return cls._executor
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.entity_cache = {}  # 实体缓存：实体名 -> 规范化实体名
        self.ie_model_service = None
        
        # 高频实体缓存：kb_id -> {chapter_entities: {}, global_entities: {}}
        self._hf_entity_cache: Dict[int, Dict[str, Any]] = {}
        self._hf_cache_lock = threading.Lock()
        
        # 预初始化线程池（如果还没有创建）
        try:
            self._get_executor()
        except Exception as e:
            logger.debug(f"预初始化线程池失败（这是正常的）: {str(e)}")
        
        # 如果使用模型模式或ner_rule模式，尝试加载IE模型
        if KG_EXTRACT_MODE in ["model", "ner_rule"]:
            try:
                from services.ie_model_service import get_ie_model_service
                self.ie_model_service = get_ie_model_service()
                if self.ie_model_service.is_available():
                    logger.info("IE模型服务已加载，将使用NER模型进行实体识别")
                else:
                    logger.warning("IE模型服务未启用或加载失败，将回退到规则/LLM模式")
                    self.ie_model_service = None
            except Exception as e:
                logger.warning(f"加载IE模型服务失败: {str(e)}，将回退到规则/LLM模式")
                self.ie_model_service = None
        self.relation_types = {
            # 常见关系类型
            '属性关系': ['是', '有', '属于', '包含', '具有'],
            '动作关系': ['做', '进行', '实现', '完成', '执行', '创建', '开发'],
            '位置关系': ['在', '位于', '来自', '去', '到'],
            '时间关系': ['在', '于', '之前', '之后', '期间'],
            '因果关系': ['导致', '引起', '因为', '所以', '由于'],
            '比较关系': ['比', '大于', '小于', '等于', '类似'],
            '社交关系': ['与', '和', '同', '一起', '合作'],
        }
    
    def extract_entities_and_relations(
        self,
        text: str,
        kb_id: int,
        doc_id: int,
        chunk_id: Optional[int] = None,
        document_text: Optional[str] = None,  # 可选：传入完整文档文本用于分析和规则生成
        db: Optional[Session] = None,  # 新增：数据库会话，用于获取高频实体
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取实体和关系，返回三元组列表
        
        新流程（优先）：
        1. 提取所有疑似高频实体
        2. 用LLM识别相似概念并建立别名关联
        3. 只抽取高频实体之间的关系
        
        Args:
            text: 输入文本
            kb_id: 知识库ID
            doc_id: 文档ID
            chunk_id: 分块ID（可选）
            
        Returns:
            三元组列表，每个三元组包含 subject, predicate, object, confidence
        """
        if not KG_EXTRACT_ENABLED:
            return []

        try:
            # 新流程：优先使用高频实体方案
            if db is not None:
                try:
                    # 1. 提取所有候选实体
                    candidate_entities = self._extract_all_candidate_entities(text, db=db, kb_id=kb_id)
                    logger.debug(f"提取到 {len(candidate_entities)} 个候选实体")
                    
                    if not candidate_entities:
                        return []
                    
                    # 2. 用LLM做实体归一（识别相似概念）
                    alias_map = self._normalize_entities_with_llm(candidate_entities, kb_id, db=db)
                    logger.debug(f"实体归一映射：{len(alias_map)} 个实体/别名")
                    
                    # 3. 从数据库加载高频实体列表（手动维护的 + 自动统计的）
                    hf_entity_names = set()
                    hf_entities_db = db.query(HighFrequencyEntity).filter(
                        HighFrequencyEntity.knowledge_base_id == kb_id
                    ).all()
                    
                    for hf_entity in hf_entities_db:
                        hf_entity_names.add(hf_entity.entity_name)
                        if hf_entity.aliases:
                            for alias in hf_entity.aliases:
                                hf_entity_names.add(alias)

                    # 读取知识库上配置的“高频最小频次阈值”，默认 3
                    hf_min_freq = 3
                    try:
                        from models.database_models import KnowledgeBase
                        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
                        if kb and kb.hf_min_frequency is not None and kb.hf_min_frequency > 0:
                            hf_min_freq = kb.hf_min_frequency
                    except Exception as cfg_e:
                        logger.debug(f"读取知识库高频阈值失败，使用默认值 3: {cfg_e}")
                    
                    # 如果没有手动维护的高频实体，使用频次统计（出现>=hf_min_freq次的实体）
                    if not hf_entity_names:
                        entity_freq = defaultdict(int)
                        for entity in candidate_entities:
                            entity_text = entity.get("text", "")
                            normalized = alias_map.get(entity_text, entity_text)
                            entity_freq[normalized] += 1
                        
                        # 选择频次>=hf_min_freq的实体作为高频实体
                        hf_entity_names = {name for name, freq in entity_freq.items() if freq >= hf_min_freq}
                        logger.debug(f"自动识别 {len(hf_entity_names)} 个高频实体（频次>={hf_min_freq}）")
                    
                    if not hf_entity_names:
                        logger.debug("未找到高频实体，跳过关系抽取")
                        return []
                    
                    # 4. 只抽取高频实体之间的关系
                    doc_cache = self._get_or_create_document_analysis(doc_id, document_text or text) if document_text else None
                    triples = self._extract_triples_between_hf_entities(
                        text, hf_entity_names, alias_map, doc_cache=doc_cache
                    )
                    
                    logger.debug(f"高频实体关系抽取得到 {len(triples)} 个三元组")
                    
                except Exception as e:
                    logger.warning(f"高频实体抽取流程失败，回退到默认抽取: {str(e)}", exc_info=True)
                    # 回退到原有流程
                    triples = self._extract_triples_fallback(text, kb_id, doc_id, chunk_id, document_text, db)
            else:
                # 没有数据库会话，使用原有流程
                triples = self._extract_triples_fallback(text, kb_id, doc_id, chunk_id, document_text, db)
            
            # 去重（确保每个三元组格式正确）
            seen = set()
            deduplicated_triples = []
            for t in triples:
                if len(t) < 3:
                    continue
                key = (t[0], t[1], t[2])
                if key in seen:
                    continue
                seen.add(key)
                deduplicated_triples.append(t if len(t) == 4 else (t[0], t[1], t[2], 0.8))
            triples = deduplicated_triples
            
            # 实体链接和规范化
            if KG_ENTITY_LINKING_ENABLED:
                triples = self._link_entities(triples, kb_id)
            
            # 添加元数据
            enriched_triples = []
            for triple in triples:
                enriched_triples.append({
                    'knowledge_base_id': kb_id,
                    'document_id': doc_id,
                    'chunk_id': chunk_id,
                    'subject': triple[0],
                    'predicate': triple[1],
                    'object': triple[2],
                    'confidence': triple[3] if len(triple) > 3 else 1.0,
                    'source_text': text[:200]
                })
            
            return enriched_triples
        except Exception as e:
            logger.error(f"提取实体和关系失败: {str(e)}", exc_info=True)
            return []
    
    def _extract_triples_fallback(
        self,
        text: str,
        kb_id: int,
        doc_id: int,
        chunk_id: Optional[int] = None,
        document_text: Optional[str] = None,
        db: Optional[Session] = None
    ) -> List[Tuple[str, str, str, float]]:
        """回退抽取方法（原有流程）"""
        triples: List[Tuple[str, str, str, float]] = []
        
        # 获取高频实体信息（如果可用）
        hf_data: Optional[Dict[str, Any]] = None
        section_title: Optional[str] = None
        
        if db is not None:
            try:
                if chunk_id is not None:
                    chunk = (
                        db.query(DocumentChunk)
                        .filter(DocumentChunk.id == chunk_id)
                        .first()
                    )
                    if chunk and chunk.chunk_metadata:
                        section_title = chunk.chunk_metadata.get("section_title")
                
                hf_data = self._get_high_frequency_entities(
                    db=db, kb_id=kb_id, document_id=doc_id, section_title=section_title
                )
            except Exception as e:
                logger.debug(f"获取高频实体失败: {str(e)}")
                hf_data = None
        
        # 根据模式选择抽取方法
        if KG_EXTRACT_MODE == "ner_rule":
            if self.ie_model_service and self.ie_model_service.is_available():
                doc_cache = self._get_or_create_document_analysis(doc_id, document_text or text)
                triples = self._extract_triples_ner_rule_hybrid(
                    text, doc_cache, hf_data=hf_data, section_title=section_title
                )
            else:
                triples = self._extract_triples_rule_based(
                    text, hf_data=hf_data, section_title=section_title
                )
        elif KG_EXTRACT_MODE == "model":
            if self.ie_model_service and self.ie_model_service.is_available():
                triples = self.ie_model_service.extract_triples(text)
            else:
                triples = self._extract_triples_rule_based(
                    text, hf_data=hf_data, section_title=section_title
                )
        elif KG_EXTRACT_MODE == "rule":
            triples = self._extract_triples_rule_based(
                text, hf_data=hf_data, section_title=section_title
            )
        elif KG_EXTRACT_MODE == "llm":
            triples = self._extract_triples_with_llm(text)
        else:  # hybrid 模式（默认）
            rule_triples = self._extract_triples_rule_based(
                text, hf_data=hf_data, section_title=section_title
            )
            triples = rule_triples
            
            if KG_LLM_FALLBACK_ENABLED and len(rule_triples) < 2:
                llm_triples = self._extract_triples_with_llm(text)
                seen = set((t[0], t[1], t[2]) for t in triples)
                for t in llm_triples:
                    key = (t[0], t[1], t[2])
                    if key not in seen:
                        seen.add(key)
                        triples.append(t)
        
        # 统一在这里做一次去重和实体链接，始终返回三元组元组列表
        if triples:
            seen = set()
            deduplicated_triples: List[Tuple[str, str, str, float]] = []
            for t in triples:
                # 只接受元组或列表形式的三元组
                if not isinstance(t, (tuple, list)) or len(t) < 3:
                    continue
                subj, pred, obj = t[0], t[1], t[2]
                key = (subj, pred, obj)
                if key in seen:
                    continue
                seen.add(key)
                conf = t[3] if len(t) > 3 else 0.8
                deduplicated_triples.append((subj, pred, obj, conf))
            triples = deduplicated_triples

        if KG_ENTITY_LINKING_ENABLED and triples:
            triples = self._link_entities(triples, kb_id)
        
        return triples
    
    def _extract_triples_with_llm(self, text: str) -> List[Tuple[str, str, str, float]]:
        """使用LLM提取三元组"""
        try:
            prompt = f"""请从以下文本中提取所有实体关系三元组。

要求：
1. 提取所有可能的(主语, 关系, 宾语)三元组
2. 实体可以是：人名、地名、机构名、概念、时间、数字等
3. 关系可以是：动作、属性、位置、时间、因果、比较等
4. 每个三元组一行，格式：主语 | 关系 | 宾语
5. 只输出三元组，不要其他解释

文本：
{text[:3000]}

输出格式示例：
张三 | 工作于 | 公司A
北京 | 位于 | 中国
项目X | 使用 | 技术Y"""

            def run_async():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    llm = get_llm_helper()
                    messages = [
                        {
                            "role": "system", 
                            "content": "你是一个专业的实体关系抽取专家，擅长从文本中准确识别实体和关系。"
                        },
                        {"role": "user", "content": prompt}
                    ]
                    return new_loop.run_until_complete(llm.call(messages, max_tokens=1500, temperature=0.1))
                finally:
                    new_loop.close()
            
            # 使用全局线程池执行异步调用（避免在解释器关闭时创建新线程池）
            executor = self._get_executor()
            if executor is None:
                logger.warning("无法创建线程池（解释器可能正在关闭），跳过LLM提取")
                return []
            
            try:
                result = executor.submit(run_async).result(timeout=30)  # 30秒超时
            except concurrent.futures.TimeoutError:
                logger.warning("LLM提取三元组超时")
                return []
            except RuntimeError as e:
                error_msg = str(e)
                if "cannot schedule new futures" in error_msg or "after shutdown" in error_msg:
                    logger.warning(f"线程池不可用: {error_msg}，尝试重新创建")
                    # 标记线程池为None，下次调用时会重新创建
                    KnowledgeGraphService._executor = None
                    return []
                raise
            
            return self._parse_triples(result)
            
        except Exception as e:
            logger.warning(f"LLM提取三元组失败: {str(e)}", exc_info=True)
            return []
    
    def _extract_triples_rule_based(
        self,
        text: str,
        hf_data: Optional[Dict[str, Any]] = None,
        section_title: Optional[str] = None,
    ) -> List[Tuple[str, str, str, float]]:
        """
        基于规则的快速三元组抽取（不调用LLM）
        
        适用场景：
        - 结构比较规整的文本
        - 常见模式：X 是 Y、X 位于 Y、X 属于 Y、X 使用 Y 等
        - 小说/历史文本：X和Y结义、X在Y地、X与Y等
        - 支持事件实体识别和事件-参与者关系
        """
        triples: List[Tuple[str, str, str, float]] = []
        if not text:
            return triples

        # 先识别事件实体（即使NER未加载也能工作）
        event_entities = self._extract_event_entities_rule_based(text)
        if event_entities:
            logger.debug(f"规则模式识别到 {len(event_entities)} 个事件实体")
            # 为事件建立三元组
            for event_info in event_entities:
                event_name = event_info["text"]
                location = event_info.get("location", "")
                participants = event_info.get("participants", [])
                
                # 事件类型
                triples.append((event_name, "类型", "结义事件", 0.9))
                # 事件地点
                if location:
                    triples.append((event_name, "发生地点", location, 0.9))
                # 参与者关系
                for participant in participants:
                    if participant:
                        triples.append((participant, "参与", event_name, 0.9))
        
        # 按句子粗略切分
        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 常见关系模式（扩展版，支持更多中文表达）
        patterns = [
            # X 是 Y
            (r"(.+?)是(.+)", "是", 1, 2),
            # X 位于 Y / 在 Y
            (r"(.+?)(位于|在)(.+)", None, 1, 3, 2),
            # X 属于 Y / 归属 Y
            (r"(.+?)(属于|归属)(.+)", None, 1, 3, 2),
            # X 使用 Y / 采用 Y
            (r"(.+?)(使用|采用)(.+)", None, 1, 3, 2),
            # X 包含 Y
            (r"(.+?)(包含)(.+)", "包含", 1, 3),
            # X 和 Y 结义 / X与Y结义
            (r"(.+?)(和|与|同)(.+?)(结义|结拜)", "结义", 1, 3),
            # X、Y、Z 结义（多人结义）
            (r"(.+?)[、，,](.+?)[、，,](.+?)(结义|结拜)", "结义", None),  # 特殊处理
            # X 在 Y 地
            (r"(.+?)(在)(.+?)(地|处|地方)", "位于", 1, 3),
            # X 来自 Y
            (r"(.+?)(来自|出自)(.+)", "来自", 1, 3),
            # X 去 Y / 到 Y
            (r"(.+?)(去|到|前往)(.+)", "前往", 1, 3),
            # X 说 Y - 降低优先级，只在没有其他关系时使用
            # (r"(.+?)(说|道|曰)(.+)", "说", 1, 3),  # 暂时禁用，噪音太多
            # X 做 Y / 进行 Y
            (r"(.+?)(做|进行|执行)(.+)", "执行", 1, 3),
            # X 有 Y
            (r"(.+?)(有)(.+)", "有", 1, 3),
            # X 成为 Y
            (r"(.+?)(成为|变成)(.+)", "成为", 1, 3),
        ]
        
        for sent in sentences:
            # 过滤过短句子
            if len(sent) < 6:
                continue
            
            for pattern_info in patterns:
                pattern = pattern_info[0]
                fixed_rel = pattern_info[1] if len(pattern_info) > 1 else None
                
                # 特殊处理多人结义模式
                if pattern == r"(.+?)[、，,](.+?)[、，,](.+?)(结义|结拜)":
                    m = re.search(pattern, sent)
                    if m:
                        persons = [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()]
                        # 为每对人创建结义关系
                        for i in range(len(persons)):
                            for j in range(i + 1, len(persons)):
                                subj = self._normalize_entity(persons[i])
                                obj = self._normalize_entity(persons[j])
                                if subj and obj and len(subj) < 50 and len(obj) < 50:
                                    triples.append((subj, "结义", obj, 0.8))
                        continue
                
                m = re.search(pattern, sent)  # 改用search而不是match，支持句子中间匹配
                if not m:
                    continue
                
                try:
                    if fixed_rel is not None:
                        # 固定关系模式
                        if len(pattern_info) == 4:
                            # (pattern, fixed_rel, subj_group, obj_group)
                            subj = m.group(pattern_info[2]).strip() if pattern_info[2] else ""
                            pred = fixed_rel
                            obj = m.group(pattern_info[3]).strip() if pattern_info[3] else ""
                        else:
                            # 默认：第一个group是subject，最后一个group是object
                            subj = m.group(1).strip()
                            pred = fixed_rel
                            obj = m.group(2).strip() if m.lastindex >= 2 else ""
                    else:
                        # 动态关系模式
                        if len(pattern_info) >= 5:
                            # (pattern, None, subj_group, obj_group, rel_group)
                            subj = m.group(pattern_info[2]).strip() if pattern_info[2] else ""
                            obj = m.group(pattern_info[3]).strip() if pattern_info[3] else ""
                            pred = m.group(pattern_info[4]).strip() if len(pattern_info) > 4 and pattern_info[4] else ""
                        else:
                            # 默认：group(1)=subject, group(2)=predicate, group(3)=object
                            subj = m.group(1).strip()
                            pred = m.group(2).strip() if m.lastindex >= 2 else ""
                            obj = m.group(3).strip() if m.lastindex >= 3 else ""
                except (IndexError, AttributeError):
                    continue
                
                # 清理和验证
                subj = self._normalize_entity(subj)
                obj = self._normalize_entity(obj)
                pred = pred.strip()
                
                # 简单约束
                if not subj or not obj or not pred:
                    continue
                # 限制长度，避免整句被当成实体
                if len(subj) > 20 or len(obj) > 20 or len(pred) > 20:
                    continue
                # 过滤掉明显不是实体的内容（如单个字符、包含大量标点等）
                if len(subj) < 2 or len(obj) < 2:
                    continue
                # 如果主体或宾语里包含明显的句子级标点/空白，也认为不是实体
                if re.search(r"[，。,\.！？!？；;：:“\"'\s]", subj):
                    continue
                if re.search(r"[，。,\.！？!？；;：:“\"'\s]", obj):
                    continue
                # 要求至少包含一个中文或字母/数字
                if not re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", subj):
                    continue
                if not re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", obj):
                    continue
                
                # 置信度：规则匹配给个中等偏上的值
                conf = 0.8
                triples.append((subj, pred, obj, conf))
        
        if triples:
            logger.debug(f"规则抽取得到 {len(triples)} 个三元组(原始)")

        # 使用高频实体进行一次置信度与实体归一调整
        if hf_data:
            triples = self._adjust_triples_with_hf_entities(
                triples, hf_data, section_title=section_title
            )
            if triples:
                logger.debug(f"规则抽取经高频实体调整后保留 {len(triples)} 个三元组")

        return triples
    
    def _extract_event_entities_rule_based(self, text: str) -> List[Dict[str, Any]]:
        """
        使用规则识别事件实体（不依赖NER模型）
        """
        import re
        event_entities = []
        
        # 事件模式1：X、Y、Z在W地结义/结拜
        pattern1 = r"(.+?)[、，,](.+?)[、，,](.+?)在(.+?)(结义|结拜)"
        matches1 = re.finditer(pattern1, text)
        for match in matches1:
            participants = [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
            location = match.group(4).strip()
            action = match.group(5).strip()
            event_name = f"{location}{action}"  # "桃园结义"
            
            event_entities.append({
                "text": event_name,
                "location": location,
                "action": action,
                "participants": participants,
                "event_type": "结义事件"
            })
            logger.debug(f"识别到事件实体: {event_name} (地点: {location}, 参与者: {participants})")
        
        # 事件模式2：X和Y在W地结义/结拜
        pattern2 = r"(.+?)(和|与|同)(.+?)在(.+?)(结义|结拜)"
        matches2 = re.finditer(pattern2, text)
        for match in matches2:
            participant1 = match.group(1).strip()
            participant2 = match.group(3).strip()
            location = match.group(4).strip()
            action = match.group(5).strip()
            event_name = f"{location}{action}"
            
            event_entities.append({
                "text": event_name,
                "location": location,
                "action": action,
                "participants": [participant1, participant2],
                "event_type": "结义事件"
            })
            logger.debug(f"识别到事件实体: {event_name} (地点: {location}, 参与者: [{participant1}, {participant2}])")
        
        # 事件模式3：在W地结义/结拜（参与者在前文）
        pattern3 = r"在(.+?)(结义|结拜)"
        matches3 = re.finditer(pattern3, text)
        for match in matches3:
            location = match.group(1).strip()
            action = match.group(2).strip()
            event_name = f"{location}{action}"
            
            # 查找前文中的参与者（在事件前50个字符内）
            context_start = max(0, match.start() - 50)
            context_text = text[context_start:match.start()]
            
            # 简单提取人名（2-4个中文字符，以常见姓氏开头）
            common_surnames = ['刘', '关', '张', '赵', '马', '黄', '曹', '孙', '周', '吴', '郑', '王', '李', '陈', '杨', '林', '何', '郭', '罗', '高']
            person_pattern = r"([\u4e00-\u9fa5]{2,4})(?=[，、。！？\s]|$)"
            participants = []
            for person_match in re.finditer(person_pattern, context_text):
                person = person_match.group(1)
                if person[0] in common_surnames:
                    participants.append(person)
            
            if participants or location:
                event_entities.append({
                    "text": event_name,
                    "location": location,
                    "action": action,
                    "participants": participants,
                    "event_type": "结义事件"
                })
                logger.debug(f"识别到事件实体: {event_name} (地点: {location}, 参与者: {participants})")
        
        # 去重（相同事件只保留一个）
        seen_events = set()
        unique_events = []
        for event in event_entities:
            if event["text"] not in seen_events:
                seen_events.add(event["text"])
                unique_events.append(event)
        
        return unique_events
    
    def _sample_text(self, text: str, max_length: int = None) -> str:
        """
        采样文本用于分析
        
        Args:
            text: 原始文本
            max_length: 最大采样长度
            
        Returns:
            采样后的文本
        """
        if max_length is None:
            max_length = KG_SAMPLE_TEXT_LENGTH
        
        if len(text) <= max_length:
            return text
        
        method = KG_SAMPLE_METHOD
        
        if method == "fixed":
            # 固定开头采样
            return text[:max_length]
        elif method == "random":
            # 随机采样中间段落
            start = random.randint(0, max(0, len(text) - max_length))
            return text[start:start + max_length]
        elif method == "mixed":
            # 混合采样：开头 + 中间随机段落
            part1_length = max_length // 2
            part2_length = max_length - part1_length
            
            part1 = text[:part1_length]
            if len(text) > part1_length:
                start = random.randint(part1_length, max(part1_length, len(text) - part2_length))
                part2 = text[start:start + part2_length]
                return part1 + "\n...\n" + part2
            return part1
        else:
            # 默认：固定开头
            return text[:max_length]
    
    def _analyze_text_content_with_llm(self, sample_text: str) -> Dict[str, Any]:
        """
        使用LLM分析文本核心内容
        
        Args:
            sample_text: 采样文本
            
        Returns:
            包含文本类型、核心主题、常见关系类型的字典
        """
        try:
            prompt = f"""请分析以下文本的核心内容，并回答以下问题：

1. 文本类型（如：小说、历史、技术文档、新闻、对话等）
2. 核心主题（1-3个关键词）
3. 文本中常见的关系类型（如：人物关系、地理位置、时间顺序、因果关系等）
4. 文本的语言风格（如：正式、口语化、叙述性等）

文本样本：
{sample_text[:1500]}

请以JSON格式输出，格式如下：
{{
    "text_type": "文本类型",
    "core_themes": ["主题1", "主题2"],
    "common_relations": ["关系类型1", "关系类型2"],
    "language_style": "语言风格"
}}

重要要求：
1. 必须输出有效的JSON格式，不要包含任何markdown代码块标记
2. 只输出JSON，不要添加任何解释文字

示例输出：
{{"text_type": "小说", "core_themes": ["历史", "人物"], "common_relations": ["人物关系", "地理位置"], "language_style": "叙述性"}}"""

            def run_async():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    llm = get_llm_helper()
                    messages = [
                        {
                            "role": "system",
                            "content": "你是一个专业的文本分析专家，擅长快速识别文本类型、主题和关系模式。"
                        },
                        {"role": "user", "content": prompt}
                    ]
                    return new_loop.run_until_complete(
                        llm.call(messages, max_tokens=500, temperature=0.3)
                    )
                finally:
                    new_loop.close()
            
            # 使用全局线程池执行异步调用（避免在解释器关闭时创建新线程池）
            executor = self._get_executor()
            if executor is None:
                logger.warning("无法创建线程池（解释器可能正在关闭），跳过LLM分析")
                raise RuntimeError("解释器正在关闭")
            
            try:
                result = executor.submit(run_async).result(timeout=30)  # 30秒超时
            except concurrent.futures.TimeoutError:
                logger.warning("LLM分析文本内容超时")
                raise
            except RuntimeError as e:
                error_msg = str(e)
                if "cannot schedule new futures" in error_msg or "after shutdown" in error_msg:
                    logger.warning(f"线程池不可用: {error_msg}，尝试重新创建")
                    # 标记线程池为None，下次调用时会重新创建
                    KnowledgeGraphService._executor = None
                    raise RuntimeError("线程池已关闭，无法执行LLM调用")
                raise
            
            # 解析JSON结果
            result_str = str(result).strip()
            logger.debug(f"LLM分析原始返回: {result_str[:300]}")
            
            analysis = None
            
            # 策略1: 直接解析
            try:
                analysis = json.loads(result_str)
            except json.JSONDecodeError:
                pass
            
            # 策略2: 提取代码块中的JSON
            if not analysis:
                code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_str, re.DOTALL)
                if code_block_match:
                    try:
                        analysis = json.loads(code_block_match.group(1))
                    except json.JSONDecodeError:
                        pass
            
            # 策略3: 查找第一个完整的JSON对象
            if not analysis:
                start_idx = result_str.find('{')
                if start_idx != -1:
                    brace_count = 0
                    end_idx = start_idx
                    for i in range(start_idx, len(result_str)):
                        if result_str[i] == '{':
                            brace_count += 1
                        elif result_str[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    
                    if brace_count == 0:
                        json_str = result_str[start_idx:end_idx]
                        try:
                            analysis = json.loads(json_str)
                        except json.JSONDecodeError:
                            pass
            
            if analysis and isinstance(analysis, dict):
                logger.debug(f"文本分析结果: {analysis}")
                return analysis
            else:
                logger.warning(f"LLM返回的JSON解析失败: {result_str[:300]}")
                # 回退到默认分析
                return {
                    "text_type": "未知",
                    "core_themes": [],
                    "common_relations": [],
                    "language_style": "未知"
                }
                
        except Exception as e:
            logger.warning(f"LLM分析文本内容失败: {str(e)}", exc_info=True)
            return {
                "text_type": "未知",
                "core_themes": [],
                "common_relations": [],
                "language_style": "未知"
            }
    
    def _generate_rules_with_llm(
        self, 
        sample_text: str, 
        analysis: Dict[str, Any],
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        使用LLM根据文本分析结果生成匹配规则
        
        Args:
            sample_text: 采样文本
            analysis: 文本分析结果
            entities: NER识别的实体列表
            
        Returns:
            规则列表，每个规则包含 pattern, relation, description
        """
        try:
            # 提取实体类型
            entity_types = set()
            entity_examples = {}
            for entity in entities[:10]:  # 只取前10个实体作为示例
                label = entity.get("label", "UNKNOWN")
                text = entity.get("text", "")
                entity_types.add(label)
                if label not in entity_examples:
                    entity_examples[label] = []
                if len(entity_examples[label]) < 3:
                    entity_examples[label].append(text)
            
            entity_info = "\n".join([
                f"- {label}: {', '.join(examples)}"
                for label, examples in entity_examples.items()
            ])
            
            prompt = f"""根据以下信息，为文本生成适合的关系提取规则（正则表达式模式）。

文本类型：{analysis.get('text_type', '未知')}
核心主题：{', '.join(analysis.get('core_themes', []))}
常见关系：{', '.join(analysis.get('common_relations', []))}
语言风格：{analysis.get('language_style', '未知')}

识别到的实体类型和示例：
{entity_info}

文本样本：
{sample_text[:1000]}

请生成5-10个关系提取规则，每个规则包含：
1. 正则表达式模式（用于匹配关系）
2. 关系名称（中文）
3. 规则描述

规则应该：
- 匹配文本中常见的关系表达
- 考虑文本的语言风格和主题
- 能够提取 (主语, 关系, 宾语) 三元组

请以JSON格式输出，格式如下：
{{
    "rules": [
        {{
            "pattern": "正则表达式模式",
            "relation": "关系名称",
            "description": "规则描述",
            "subject_group": 1,
            "object_group": 3,
            "relation_group": 2
        }}
    ]
}}

重要要求：
1. 必须输出有效的JSON格式，不要包含任何markdown代码块标记
2. pattern 应该使用捕获组，第一个捕获组通常是主语，最后一个通常是宾语
3. subject_group, object_group, relation_group 表示在正则匹配结果中的组索引（从1开始）
4. 如果关系是固定的，relation_group 可以为 null 或不设置
5. 只输出JSON，不要添加任何解释文字

示例输出：
{{"rules": [{{"pattern": "(.+?)(是|为)(.+)", "relation": "是", "description": "识别是/为关系", "subject_group": 1, "object_group": 3, "relation_group": null}}]}}"""

            def run_async():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    llm = get_llm_helper()
                    messages = [
                        {
                            "role": "system",
                            "content": "你是一个专业的正则表达式和关系提取专家，擅长根据文本特点生成精准的匹配规则。"
                        },
                        {"role": "user", "content": prompt}
                    ]
                    return new_loop.run_until_complete(
                        llm.call(messages, max_tokens=1500, temperature=0.2)
                    )
                finally:
                    new_loop.close()
            
            # 使用全局线程池执行异步调用（避免在解释器关闭时创建新线程池）
            executor = self._get_executor()
            if executor is None:
                logger.warning("无法创建线程池（解释器可能正在关闭），跳过LLM规则生成")
                raise RuntimeError("解释器正在关闭")
            
            try:
                result = executor.submit(run_async).result(timeout=30)  # 30秒超时
            except concurrent.futures.TimeoutError:
                logger.warning("LLM生成规则超时")
                raise
            except RuntimeError as e:
                error_msg = str(e)
                if "cannot schedule new futures" in error_msg or "after shutdown" in error_msg:
                    logger.warning(f"线程池不可用: {error_msg}，尝试重新创建")
                    # 标记线程池为None，下次调用时会重新创建
                    KnowledgeGraphService._executor = None
                    raise RuntimeError("线程池已关闭，无法执行LLM调用")
                raise
            
            # 解析JSON结果
            result_str = str(result).strip()
            logger.info(f"=== LLM返回的原始规则内容 ===")
            logger.info(f"长度: {len(result_str)} 字符")
            logger.info(f"完整内容:\n{result_str}")
            logger.info(f"=== 原始内容结束 ===")
            
            # 尝试多种JSON提取策略
            rules_data = None
            parse_error = None
            
            # 策略1: 直接解析整个字符串
            try:
                rules_data = json.loads(result_str)
                logger.debug("策略1成功: 直接解析")
            except json.JSONDecodeError as e:
                parse_error = str(e)
                logger.debug(f"策略1失败: {parse_error}")
            
            # 策略2: 提取代码块中的JSON（如果被markdown代码块包裹）
            if not rules_data:
                # 改进：匹配更灵活的代码块格式
                code_block_patterns = [
                    r'```(?:json)?\s*(\{.*?\})\s*```',  # 标准代码块
                    r'```json\s*(\{.*?\})\s*```',  # 明确json标记
                    r'```\s*(\{.*?\})\s*```',  # 无语言标记
                ]
                for pattern in code_block_patterns:
                    code_block_match = re.search(pattern, result_str, re.DOTALL)
                    if code_block_match:
                        try:
                            json_str = code_block_match.group(1)
                            rules_data = json.loads(json_str)
                            logger.debug("策略2成功: 从代码块提取")
                            break
                        except json.JSONDecodeError as e:
                            logger.debug(f"策略2尝试失败: {str(e)}")
                            continue
            
            # 策略3: 查找第一个完整的JSON对象（支持嵌套，改进版）
            if not rules_data:
                # 使用栈来匹配嵌套的大括号，同时处理字符串内的转义
                start_idx = result_str.find('{')
                if start_idx != -1:
                    brace_count = 0
                    end_idx = start_idx
                    in_string = False
                    escape_next = False
                    
                    for i in range(start_idx, len(result_str)):
                        char = result_str[i]
                        
                        # 处理转义字符
                        if escape_next:
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            continue
                        
                        # 处理字符串边界
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        
                        # 只在非字符串内计数大括号
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i + 1
                                    break
                    
                    if brace_count == 0 and end_idx > start_idx:
                        json_str = result_str[start_idx:end_idx]
                        try:
                            rules_data = json.loads(json_str)
                            logger.debug(f"策略3成功: 栈匹配提取，JSON长度: {len(json_str)}")
                        except json.JSONDecodeError as e:
                            parse_error = str(e)
                            logger.debug(f"策略3提取成功但解析失败: {parse_error}, JSON片段: {json_str[:200]}")
            
            # 策略4: 尝试修复常见的JSON格式问题并手动解析
            if not rules_data:
                # 移除可能的markdown标记和前后空白
                cleaned = re.sub(r'```json\s*', '', result_str)
                cleaned = re.sub(r'```\s*', '', cleaned)
                cleaned = cleaned.strip()
                
                # 尝试修复正则表达式中的转义字符问题
                # LLM可能返回 \W, \d, \s 等，在JSON字符串中需要转义为 \\W, \\d, \\s
                # 但要注意：已经在字符串内的 \\ 不应该再转义
                def fix_regex_escapes(json_str: str) -> str:
                    """修复JSON字符串中正则表达式的转义字符"""
                    # 方法：在字符串值中，将单个反斜杠后跟字母/数字/特殊字符的转义为双反斜杠
                    # 但要注意：已经是 \\ 的不要重复转义
                    result = []
                    i = 0
                    in_string = False
                    escape_next = False
                    
                    while i < len(json_str):
                        char = json_str[i]
                        
                        if escape_next:
                            escape_next = False
                            # 如果是在字符串内，且是单个反斜杠后跟字母/数字/特殊字符，需要转义
                            if in_string:
                                # 检查是否是正则转义字符（\W, \d, \s, \w, \D, \S, \u等）
                                # 或者是Unicode转义（\u4e00等）
                                if (char.isalnum() or 
                                    (char == 'u' and i + 4 < len(json_str) and 
                                     all(c in '0123456789abcdefABCDEF' for c in json_str[i+1:i+5]))):
                                    result.append('\\')  # 添加额外的反斜杠
                            result.append(char)
                            i += 1
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            result.append(char)
                            i += 1
                            continue
                        
                        if char == '"':
                            in_string = not in_string
                            result.append(char)
                            i += 1
                            continue
                        
                        result.append(char)
                        i += 1
                    
                    return ''.join(result)
                
                # 尝试修复转义字符后解析
                try:
                    fixed_json = fix_regex_escapes(cleaned)
                    rules_data = json.loads(fixed_json)
                    logger.debug("策略4成功: 修复转义字符后解析")
                except (json.JSONDecodeError, Exception) as e:
                    logger.debug(f"策略4修复转义字符后仍失败: {str(e)}")
                
                # 如果还是失败，尝试直接解析清理后的字符串
                if not rules_data:
                    try:
                        rules_data = json.loads(cleaned)
                        logger.debug("策略4成功: 清理后直接解析")
                    except json.JSONDecodeError:
                        # 如果还是失败，尝试手动提取rules数组
                        try:
                            # 使用更精确的正则，考虑嵌套结构
                            rules_match = re.search(r'"rules"\s*:\s*\[', cleaned)
                            if rules_match:
                                start_pos = rules_match.end()
                                # 使用栈匹配找到数组的结束位置
                                bracket_count = 0
                                in_string = False
                                escape_next = False
                                end_pos = start_pos
                                
                                for i in range(start_pos, len(cleaned)):
                                    char = cleaned[i]
                                    
                                    if escape_next:
                                        escape_next = False
                                        continue
                                    
                                    if char == '\\':
                                        escape_next = True
                                        continue
                                    
                                    if char == '"' and not escape_next:
                                        in_string = not in_string
                                        continue
                                    
                                    if not in_string:
                                        if char == '[':
                                            bracket_count += 1
                                        elif char == ']':
                                            bracket_count -= 1
                                            if bracket_count == 0:
                                                end_pos = i
                                                break
                                
                                if bracket_count == 0:
                                    rules_content = cleaned[start_pos:end_pos]
                                    # 尝试解析整个JSON（包含rules数组）
                                    try:
                                        full_json = '{"rules": [' + rules_content + ']}'
                                        rules_data = json.loads(full_json)
                                        logger.debug("策略4成功: 手动构建完整JSON")
                                    except json.JSONDecodeError:
                                        # 如果还是失败，尝试逐个解析规则对象
                                        rule_objects = []
                                        # 使用改进的规则对象匹配（考虑嵌套和转义）
                                        obj_start = -1
                                        obj_brace_count = 0
                                        obj_in_string = False
                                        obj_escape_next = False
                                        
                                        for i, char in enumerate(rules_content):
                                            if obj_escape_next:
                                                obj_escape_next = False
                                                continue
                                            
                                            if char == '\\':
                                                obj_escape_next = True
                                                continue
                                            
                                            if char == '"' and not obj_escape_next:
                                                obj_in_string = not obj_in_string
                                                continue
                                            
                                            if not obj_in_string:
                                                if char == '{':
                                                    if obj_brace_count == 0:
                                                        obj_start = i
                                                    obj_brace_count += 1
                                                elif char == '}':
                                                    obj_brace_count -= 1
                                                    if obj_brace_count == 0 and obj_start >= 0:
                                                        obj_str = rules_content[obj_start:i+1]
                                                        try:
                                                            # 尝试修复转义字符
                                                            fixed_obj_str = fix_regex_escapes(obj_str)
                                                            rule_obj = json.loads(fixed_obj_str)
                                                            rule_objects.append(rule_obj)
                                                        except json.JSONDecodeError:
                                                            # 如果修复后还是失败，尝试原始字符串
                                                            try:
                                                                rule_obj = json.loads(obj_str)
                                                                rule_objects.append(rule_obj)
                                                            except json.JSONDecodeError:
                                                                pass
                                                        obj_start = -1
                                        
                                        if rule_objects:
                                            rules_data = {"rules": rule_objects}
                                            logger.debug(f"策略4成功: 手动解析 {len(rule_objects)} 个规则对象")
                        except Exception as e:
                            logger.debug(f"策略4手动构建失败: {str(e)}")
            
            # 如果成功解析，提取rules
            if rules_data:
                rules = rules_data.get("rules", [])
                if isinstance(rules, list) and len(rules) > 0:
                    logger.info(f"=== 成功解析出 {len(rules)} 个动态规则 ===")
                    # 验证规则格式并打印详细信息
                    valid_rules = []
                    for idx, rule in enumerate(rules, 1):
                        logger.info(f"规则 {idx}:")
                        logger.info(f"  类型: {type(rule)}")
                        logger.info(f"  内容: {rule}")
                        if isinstance(rule, dict):
                            logger.info(f"  字段: {list(rule.keys())}")
                            logger.info(f"  pattern: {rule.get('pattern', 'N/A')}")
                            logger.info(f"  relation: {rule.get('relation', 'N/A')}")
                            logger.info(f"  description: {rule.get('description', 'N/A')}")
                            logger.info(f"  subject_group: {rule.get('subject_group', 'N/A')}")
                            logger.info(f"  object_group: {rule.get('object_group', 'N/A')}")
                            logger.info(f"  relation_group: {rule.get('relation_group', 'N/A')}")
                            
                            if "pattern" in rule and "relation" in rule:
                                valid_rules.append(rule)
                                logger.info(f"  ✓ 规则有效")
                            else:
                                logger.warning(f"  ✗ 规则格式无效: 缺少 pattern 或 relation 字段")
                        else:
                            logger.warning(f"  ✗ 规则格式无效: 不是字典类型")
                        logger.info("")
                    
                    if valid_rules:
                        logger.info(f"=== 最终有效规则数量: {len(valid_rules)} ===")
                        for idx, rule in enumerate(valid_rules, 1):
                            logger.info(f"有效规则 {idx}: {rule.get('relation')} - {rule.get('pattern', '')[:50]}")
                        return valid_rules
                    else:
                        logger.warning("=== 没有有效的规则 ===")
                else:
                    logger.warning(f"rules字段不是有效列表或为空: {rules}")
            else:
                # 显示更详细的错误信息
                logger.warning(f"=== LLM返回的规则JSON解析失败 ===")
                logger.warning(f"原始内容长度: {len(result_str)}")
                logger.warning(f"完整原始内容:\n{result_str}")
                if parse_error:
                    logger.warning(f"最后解析错误: {parse_error}")
                logger.warning(f"=== 解析失败结束 ===")
            
            return []
                
        except Exception as e:
            logger.warning(f"LLM生成规则失败: {str(e)}", exc_info=True)
            return []
    
    def _get_or_create_document_analysis(self, doc_id: int, document_text: str) -> Dict[str, Any]:
        """
        获取或创建文档级别的分析和规则（每个文档只分析一次）
        
        Args:
            doc_id: 文档ID
            document_text: 完整文档文本（用于分析和规则生成）
            
        Returns:
            包含 analysis 和 dynamic_rules 的字典
        """
        with self._cache_lock:
            # 检查缓存
            if doc_id in self._document_cache:
                logger.debug(f"使用文档 {doc_id} 的缓存分析和规则")
                return self._document_cache[doc_id]
            
            # 生成新的分析和规则
            logger.info(f"为文档 {doc_id} 生成分析和规则（仅一次）")
            cache = {
                "analysis": None,
                "dynamic_rules": []
            }
            
            if KG_DYNAMIC_RULES_ENABLED:
                # 采样文本
                sample_text = self._sample_text(document_text)
                logger.debug(f"采样文本长度: {len(sample_text)}")
                
                # 分析文本内容（带重试）
                analysis = None
                for retry in range(KG_DYNAMIC_RULES_RETRY_COUNT):
                    try:
                        analysis = self._analyze_text_content_with_llm(sample_text)
                        if analysis and analysis.get('text_type') != '未知':
                            logger.info(f"文档 {doc_id} 文本分析成功（尝试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}）: 类型={analysis.get('text_type')}, 主题={analysis.get('core_themes')}")
                            break
                        else:
                            if retry < KG_DYNAMIC_RULES_RETRY_COUNT - 1:
                                logger.warning(f"文档 {doc_id} 文本分析返回默认值，重试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}")
                                time.sleep(KG_DYNAMIC_RULES_RETRY_DELAY)
                    except Exception as e:
                        if retry < KG_DYNAMIC_RULES_RETRY_COUNT - 1:
                            logger.warning(f"文档 {doc_id} 文本分析失败（尝试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}），将重试: {str(e)[:200]}")
                            time.sleep(KG_DYNAMIC_RULES_RETRY_DELAY)
                        else:
                            logger.error(f"文档 {doc_id} 文本分析失败（已重试 {KG_DYNAMIC_RULES_RETRY_COUNT} 次）: {str(e)[:200]}")
                            analysis = {
                                "text_type": "未知",
                                "core_themes": [],
                                "common_relations": [],
                                "language_style": "未知"
                            }
                
                cache["analysis"] = analysis
                
                # 提取一些实体用于规则生成（从采样文本中）
                entities = self.ie_model_service.extract_entities(sample_text) if self.ie_model_service else []
                
                # 生成动态规则（带重试）
                dynamic_rules = []
                for retry in range(KG_DYNAMIC_RULES_RETRY_COUNT):
                    try:
                        dynamic_rules = self._generate_rules_with_llm(sample_text, analysis, entities)
                        if dynamic_rules and len(dynamic_rules) > 0:
                            logger.info(f"文档 {doc_id} 生成了 {len(dynamic_rules)} 个动态规则（尝试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}）")
                            break
                        else:
                            if retry < KG_DYNAMIC_RULES_RETRY_COUNT - 1:
                                logger.warning(f"文档 {doc_id} 动态规则生成返回空列表，重试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}")
                                time.sleep(KG_DYNAMIC_RULES_RETRY_DELAY)
                    except Exception as e:
                        if retry < KG_DYNAMIC_RULES_RETRY_COUNT - 1:
                            logger.warning(f"文档 {doc_id} 动态规则生成失败（尝试 {retry + 1}/{KG_DYNAMIC_RULES_RETRY_COUNT}），将重试: {str(e)[:200]}")
                            time.sleep(KG_DYNAMIC_RULES_RETRY_DELAY)
                        else:
                            logger.error(f"文档 {doc_id} 动态规则生成失败（已重试 {KG_DYNAMIC_RULES_RETRY_COUNT} 次）: {str(e)[:200]}")
                            dynamic_rules = []
                
                cache["dynamic_rules"] = dynamic_rules
            
            # 缓存结果
            self._document_cache[doc_id] = cache
            return cache
    
    def _clear_document_cache(self, doc_id: int):
        """清理文档缓存"""
        with self._cache_lock:
            if doc_id in self._document_cache:
                del self._document_cache[doc_id]
                logger.debug(f"已清理文档 {doc_id} 的缓存")
    
    def _extract_triples_ner_rule_hybrid(
        self,
        text: str,
        doc_cache: Optional[Dict[str, Any]] = None,
        hf_data: Optional[Dict[str, Any]] = None,
        section_title: Optional[str] = None,
    ) -> List[Tuple[str, str, str, float]]:
        """
        NER + 规则混合提取：使用NER识别实体，然后用规则提取关系
        
        优势：
        1. NER模型准确识别实体（人名、地名、机构等）
        2. 规则提取关系速度快、可控性强
        3. 结合实体位置信息，提高关系匹配准确性
        4. 动态规则生成：根据文本内容自动生成匹配规则
        """
        triples: List[Tuple[str, str, str, float]] = []
        if not text:
            return triples

        # 1. 使用NER模型提取实体
        entities = []
        if self.ie_model_service and self.ie_model_service.is_available():
            entities = self.ie_model_service.extract_entities(text)
            logger.debug(f"NER识别到 {len(entities)} 个实体")
        else:
            logger.debug("NER模型未加载，使用规则模式识别实体和事件")
            # 即使NER未加载，也尝试用简单规则识别实体（用于事件识别）
            entities = self._extract_entities_by_rules(text)
        
        if not entities:
            logger.debug("未识别到任何实体，回退到纯规则模式")
            return self._extract_triples_rule_based(
                text, hf_data=hf_data, section_title=section_title
            )

        # 2. 使用文档级别的分析和规则（如果提供）
        dynamic_rules = []
        if doc_cache:
            dynamic_rules = doc_cache.get("dynamic_rules", [])
            if dynamic_rules:
                logger.debug(f"使用文档级别的 {len(dynamic_rules)} 个动态规则")
        
        # 2. 构建实体映射：实体文本 -> 实体信息（包含位置和类型）
        entity_map = {}
        entity_texts = set()
        for entity in entities:
            entity_text = entity.get("text", "").strip()
            if not entity_text or len(entity_text) < 2:
                continue
            entity_texts.add(entity_text)
            # 记录实体的所有出现位置
            if entity_text not in entity_map:
                entity_map[entity_text] = {
                    "label": entity.get("label", "UNKNOWN"),
                    "positions": []
                }
            # 注意：NER返回的start/end是token位置，需要转换为字符位置
            # 这里简化处理，使用实体文本在原文中的位置
            start_pos = text.find(entity_text)
            if start_pos >= 0:
                entity_map[entity_text]["positions"].append({
                    "start": start_pos,
                    "end": start_pos + len(entity_text),
                    "label": entity.get("label", "UNKNOWN")
                })
        
        # 3. 按句子切分文本
        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 6]
        
        # 4. 构建关系模式列表（默认规则 + 动态规则）
        relation_patterns = []
        
        # 4.1 添加默认规则
        default_patterns = [
            # 基本关系
            (r"(.+?)(是|为|成为)(.+)", "是", ["person", "organization", "location", "UNKNOWN"], 1, 3, None),
            (r"(.+?)(位于|在|处于)(.+)", "位于", ["location", "organization", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(属于|归属)(.+)", "属于", ["person", "organization", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(使用|采用|利用)(.+)", "使用", ["person", "organization", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(包含|包括)(.+)", "包含", ["organization", "location", "UNKNOWN"], 1, 3, None),
            (r"(.+?)(创建|建立|开发)(.+)", "创建", ["person", "organization", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(工作于|就职于)(.+)", "工作于", ["person", "UNKNOWN"], 1, 3, 2),
            
            # 社交关系（小说/历史文本）
            (r"(.+?)(和|与|同)(.+?)(结义|结拜)", "结义", ["person", "UNKNOWN"], 1, 3, None),
            (r"(.+?)(和|与|同)(.+?)(是|为)(.+)", "是", ["person", "organization", "UNKNOWN"], 1, 5, None),
            (r"(.+?)(和|与|同)(.+?)(一起|共同)(.+)", "合作", ["person", "organization", "UNKNOWN"], 1, 5, None),
            
            # 动作关系
            (r"(.+?)(说|道|曰)(.+)", "说", ["person", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(做|进行|执行)(.+)", "执行", ["person", "organization", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(去|到|前往)(.+)", "前往", ["person", "UNKNOWN"], 1, 3, 2),
            (r"(.+?)(来自|出自)(.+)", "来自", ["person", "location", "UNKNOWN"], 1, 3, 2),
            
            # 属性关系
            (r"(.+?)(有)(.+)", "有", ["person", "organization", "UNKNOWN"], 1, 3, None),
            (r"(.+?)(拥有)(.+)", "拥有", ["person", "organization", "UNKNOWN"], 1, 3, None),
            
            # 时间/位置关系
            (r"(.+?)(在)(.+?)(地|处|地方)", "位于", ["person", "location", "UNKNOWN"], 1, 3, None),
            (r"(.+?)(于)(.+?)(时|时候|期间)", "发生于", ["person", "organization", "UNKNOWN"], 1, 3, None),
        ]
        relation_patterns.extend(default_patterns)
        
        # 4.2 添加动态规则
        for rule in dynamic_rules:
            try:
                pattern = rule.get("pattern", "")
                relation = rule.get("relation", "")
                subject_group = rule.get("subject_group", 1)
                object_group = rule.get("object_group", 3)
                relation_group = rule.get("relation_group", None)
                
                if pattern and relation:
                    # 动态规则允许所有实体类型（由规则本身决定）
                    relation_patterns.append((
                        pattern,
                        relation,
                        ["person", "organization", "location", "UNKNOWN"],  # 允许所有类型
                        subject_group,
                        object_group,
                        relation_group
                    ))
                    logger.debug(f"添加动态规则: {relation} - {pattern[:50]}")
            except Exception as e:
                logger.warning(f"解析动态规则失败: {str(e)}, 规则: {rule}")
        
        logger.info(
            f"总共使用 {len(relation_patterns)} 个规则（{len(default_patterns)} 个默认 + {len(dynamic_rules)} 个动态）"
        )

        # 5. 在每个句子中查找关系
        for sent in sentences:
            # 检查句子中是否包含实体
            sent_entities = []
            for entity_text in entity_texts:
                if entity_text in sent:
                    # 找到实体在句子中的位置
                    start_pos = sent.find(entity_text)
                    if start_pos >= 0:
                        sent_entities.append({
                            "text": entity_text,
                            "start": start_pos,
                            "end": start_pos + len(entity_text),
                            "label": entity_map[entity_text]["label"]
                        })
            
            if len(sent_entities) < 2:
                # 句子中实体少于2个，跳过（至少需要2个实体才能形成关系）
                continue
            
            # 6. 使用规则模式匹配关系
            for pattern_info in relation_patterns:
                pattern = pattern_info[0]
                fixed_rel = pattern_info[1]
                allowed_labels = pattern_info[2] if len(pattern_info) > 2 else None
                # 支持新的规则格式：包含组索引信息
                subject_group = pattern_info[3] if len(pattern_info) > 3 else 1
                object_group = pattern_info[4] if len(pattern_info) > 4 else None
                relation_group = pattern_info[5] if len(pattern_info) > 5 else None
                
                matches = re.finditer(pattern, sent)
                for match in matches:
                    # 提取匹配的组
                    groups = match.groups()
                    if len(groups) < 2:
                        continue
                    
                    # 根据规则配置提取subject、object和relation
                    subj_text = None
                    obj_text = None
                    rel_text = fixed_rel
                    
                    try:
                        # 使用规则中指定的组索引
                        if subject_group and subject_group <= len(groups):
                            subj_text = groups[subject_group - 1].strip() if groups[subject_group - 1] else None
                        
                        if object_group and object_group <= len(groups):
                            obj_text = groups[object_group - 1].strip() if groups[object_group - 1] else None
                        elif not object_group:
                            # 如果没有指定object_group，使用最后一个组
                            obj_text = groups[-1].strip() if groups else None
                        
                        # 如果关系组有指定，使用匹配到的关系；否则使用固定关系
                        if relation_group and relation_group <= len(groups) and groups[relation_group - 1]:
                            rel_text = groups[relation_group - 1].strip()
                        elif not fixed_rel and len(groups) >= 2:
                            # 如果没有固定关系，尝试从中间组提取
                            rel_text = groups[1].strip() if len(groups) > 1 else ""
                    except (IndexError, AttributeError) as e:
                        logger.debug(f"提取规则组失败: {str(e)}, 规则: {pattern[:50]}")
                        continue
                    
                    # 如果使用组索引方式没有提取到，回退到原来的逻辑
                    if not subj_text or not obj_text:
                        # 处理特殊模式（保持向后兼容）
                        if fixed_rel == "是" and len(groups) >= 3:
                            # X 是 Y 或 X 和 Y 是 Z
                            if "和" in groups[0] or "与" in groups[0] or "同" in groups[0]:
                                # 多人关系：X和Y是Z
                                persons = re.split(r"[和与同]", groups[0])
                                obj_text = groups[-1].strip() if not obj_text else obj_text
                                for person in persons:
                                    person = person.strip()
                                    if person in entity_texts:
                                        subj_text = person
                                        break
                            else:
                                subj_text = groups[0].strip() if not subj_text else subj_text
                                obj_text = groups[-1].strip() if not obj_text else obj_text
                        elif "结义" in pattern or "结拜" in pattern:
                            # 结义关系：X和Y结义
                            subj_text = groups[0].strip() if not subj_text else subj_text
                            obj_text = groups[2].strip() if len(groups) > 2 and not obj_text else obj_text
                        elif len(groups) >= 3:
                            # 标准模式：X 关系词 Y
                            subj_text = groups[0].strip() if not subj_text else subj_text
                            obj_text = groups[-1].strip() if not obj_text else obj_text
                            if relation_group is None and not fixed_rel and len(groups) > 2:
                                rel_text = groups[1].strip()
                    
                    # 验证提取的实体是否在NER识别的实体列表中
                    if not subj_text or not obj_text:
                        continue
                    
                    # 检查subject和object是否都是实体
                    subj_is_entity = subj_text in entity_texts
                    obj_is_entity = obj_text in entity_texts
                    
                    # 如果都不是实体，跳过
                    if not subj_is_entity and not obj_is_entity:
                        continue
                    
                    # 如果只有一个实体，尝试从文本中提取另一个实体
                    if subj_is_entity and not obj_is_entity:
                        # object不是实体，尝试从object文本中查找实体
                        for entity_text in entity_texts:
                            if entity_text in obj_text and len(entity_text) >= 2:
                                obj_text = entity_text
                                obj_is_entity = True
                                break
                    
                    if obj_is_entity and not subj_is_entity:
                        # subject不是实体，尝试从subject文本中查找实体
                        for entity_text in entity_texts:
                            if entity_text in subj_text and len(entity_text) >= 2:
                                subj_text = entity_text
                                subj_is_entity = True
                                break
                    
                    # 验证实体类型是否符合关系模式
                    if allowed_labels:
                        subj_label = entity_map.get(subj_text, {}).get("label", "UNKNOWN")
                        obj_label = entity_map.get(obj_text, {}).get("label", "UNKNOWN")
                        if subj_label not in allowed_labels and "UNKNOWN" not in allowed_labels:
                            continue
                        if obj_label not in allowed_labels and "UNKNOWN" not in allowed_labels:
                            continue
                    
                    # 规范化实体
                    subj = self._normalize_entity(subj_text)
                    obj = self._normalize_entity(obj_text)
                    pred = rel_text.strip()
                    
                    # 验证三元组
                    if not subj or not obj or not pred:
                        continue
                    if len(subj) > 100 or len(obj) > 100 or len(pred) > 20:
                        continue
                    if len(subj) < 2 or len(obj) < 2:
                        continue
                    
                    # 计算置信度：NER识别的实体 + 规则匹配
                    confidence = 0.85  # 基础置信度
                    if subj_is_entity and obj_is_entity:
                        confidence = 0.9  # 两个都是NER识别的实体，置信度更高
                    
                    triples.append((subj, pred, obj, confidence))
        
        # 7. 处理多人关系（如：刘备、关羽、张飞结义）
        for sent in sentences:
            # 查找多人结义模式
            multi_person_pattern = r"(.+?)[、，,](.+?)[、，,](.+?)(结义|结拜)"
            match = re.search(multi_person_pattern, sent)
            if match:
                persons = [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
                # 验证是否都是实体
                valid_persons = [p for p in persons if p in entity_texts]
                if len(valid_persons) >= 2:
                    # 为每对人创建结义关系
                    for i in range(len(valid_persons)):
                        for j in range(i + 1, len(valid_persons)):
                            subj = self._normalize_entity(valid_persons[i])
                            obj = self._normalize_entity(valid_persons[j])
                            if subj and obj:
                                triples.append((subj, "结义", obj, 0.9))
        
        # 8. 处理事件实体（EVENT标签）和事件-参与者关系
        event_entities = {e["text"]: e for e in entities if e.get("label") == "EVENT"}
        if event_entities:
            logger.debug(f"发现 {len(event_entities)} 个事件实体，开始建立事件-参与者关系")
            
            for event_name, event_info in event_entities.items():
                event_metadata = event_info.get("metadata", {})
                location = event_metadata.get("location", "")
                participants = event_metadata.get("participants", [])
                event_type = event_metadata.get("event_type", "事件")
                
                # 8.1 建立事件类型关系
                if event_type:
                    triples.append((event_name, "类型", event_type, 0.95))
                
                # 8.2 建立事件-地点关系
                if location and location in entity_texts:
                    triples.append((event_name, "发生地点", location, 0.95))
                
                # 8.3 建立事件-参与者关系
                for participant in participants:
                    participant_normalized = self._normalize_entity(participant)
                    if participant_normalized and participant_normalized in entity_texts:
                        triples.append((participant_normalized, "参与", event_name, 0.95))
                        logger.debug(f"建立事件-参与者关系: ({participant_normalized}, 参与, {event_name})")
                
                # 8.4 如果事件名中包含地点，也建立关系
                # 例如："桃园结义" -> (桃园结义, 包含地点, 桃园)
                if location and location in event_name:
                    # 提取地点部分
                    location_part = location
                    if location_part in entity_texts:
                        triples.append((event_name, "包含地点", location_part, 0.9))
        
        # 9. 去重
        seen = set()
        unique_triples = []
        for triple in triples:
            key = (triple[0], triple[1], triple[2])
            if key not in seen:
                seen.add(key)
                unique_triples.append(triple)
        
        if unique_triples:
            logger.debug(f"NER+规则混合抽取得到 {len(unique_triples)} 个三元组")
        return unique_triples
    
    def _parse_triples(self, text: str) -> List[Tuple[str, str, str, float]]:
        """解析LLM返回的三元组"""
        triples = []
        if not text:
            return triples
        
        lines = [l.strip() for l in str(text).splitlines() if l.strip()]
        
        for line in lines:
            # 跳过非三元组行
            if re.match(r'^\d+[\.\)]', line) or line.startswith(('-', '*', '#')):
                line = re.sub(r'^\d+[\.\)]\s*', '', line)
                line = re.sub(r'^[-*#]\s*', '', line)
            
            # 尝试多种分隔符
            separators = ['|', '，', ',', '\t', ' -> ', ' ->', '-> ', '→']
            parts = None
            
            for sep in separators:
                if sep in line:
                    parts = [p.strip().strip('"\'') for p in line.split(sep)]
                    if len(parts) >= 3:
                        break
            
            if parts and len(parts) >= 3:
                subject = parts[0].strip()
                predicate = parts[1].strip()
                obj = parts[2].strip()
                
                # 验证三元组
                if (len(subject) > 0 and len(predicate) > 0 and len(obj) > 0 and
                    len(subject) < 200 and len(predicate) < 100 and len(obj) < 200):
                    # 计算置信度（基于关系类型的常见程度）
                    confidence = self._calculate_confidence(predicate)
                    triples.append((subject, predicate, obj, confidence))
        
        logger.debug(f"解析得到 {len(triples)} 个三元组")
        return triples
    
    def _calculate_confidence(self, predicate: str) -> float:
        """计算关系置信度"""
        # 基于关系类型和常见程度
        base_confidence = 0.8
        
        # 检查是否是常见关系词
        for rel_type, keywords in self.relation_types.items():
            if any(kw in predicate for kw in keywords):
                return min(1.0, base_confidence + 0.1)
        
        return base_confidence
    
    def _link_entities(
        self, 
        triples: List[Tuple[str, str, str, float]], 
        kb_id: int
    ) -> List[Tuple[str, str, str, float]]:
        """实体链接：将相似的实体链接到同一个规范化实体"""
        if not triples:
            return triples
        
        # 收集所有实体
        entities = set()
        for s, p, o, c in triples:
            entities.add(s)
            entities.add(o)
        
        # 简单的实体链接：基于字符串相似度
        # 这里可以使用更复杂的实体链接算法
        entity_map = {}
        for entity in entities:
            # 规范化实体名（去除多余空格、统一格式）
            normalized = self._normalize_entity(entity)
            entity_map[entity] = normalized
        
        # 应用实体映射
        linked_triples = []
        for s, p, o, c in triples:
            linked_triples.append((
                entity_map.get(s, s),
                p,
                entity_map.get(o, o),
                c
            ))
        
        return linked_triples
    
    def _normalize_entity(self, entity: str) -> str:
        """规范化实体名"""
        # 去除多余空格
        normalized = ' '.join(entity.split())
        
        # 统一标点符号
        normalized = normalized.replace('，', ',').replace('。', '.')
        
        # 去除前后标点
        normalized = normalized.strip('.,;:!?，。；：！？')
        
        return normalized
    
    def store_triples(self, db: Session, triples: List[Dict[str, Any]]) -> int:
        """存储三元组到数据库"""
        if not triples:
            return 0
        
        stored_count = 0
        try:
            for triple_data in triples:
                # 检查是否已存在（避免重复）
                existing = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == triple_data['knowledge_base_id'],
                    KnowledgeTriple.subject == triple_data['subject'],
                    KnowledgeTriple.predicate == triple_data['predicate'],
                    KnowledgeTriple.object == triple_data['object']
                ).first()
                
                if not existing:
                    triple = KnowledgeTriple(**triple_data)
                    db.add(triple)
                    stored_count += 1
            
            db.commit()
            logger.info(f"成功存储 {stored_count} 个三元组到知识图谱")
            
        except Exception as e:
            db.rollback()
            logger.error(f"存储三元组失败: {str(e)}")
        
        return stored_count
    
    def query_entities(
        self, 
        db: Session, 
        kb_id: int, 
        entity_name: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """查询与指定实体相关的所有三元组（支持事件查询）"""
        try:
            # 先尝试精确匹配
            triples = db.query(KnowledgeTriple).filter(
                KnowledgeTriple.knowledge_base_id == kb_id,
                or_(
                    KnowledgeTriple.subject == entity_name,
                    KnowledgeTriple.object == entity_name
                )
            ).limit(limit).all()
            
            # 如果精确匹配结果不足，使用模糊匹配
            if len(triples) < limit:
                fuzzy_triples = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == kb_id,
                    and_(
                        or_(
                            KnowledgeTriple.subject.contains(entity_name),
                            KnowledgeTriple.object.contains(entity_name)
                        ),
                        # 排除已经精确匹配的
                        ~or_(
                            KnowledgeTriple.subject == entity_name,
                            KnowledgeTriple.object == entity_name
                        )
                    )
                ).limit(limit - len(triples)).all()
                triples.extend(fuzzy_triples)
            
            results = []
            for triple in triples:
                results.append({
                    'subject': triple.subject,
                    'predicate': triple.predicate,
                    'object': triple.object,
                    'confidence': triple.confidence,
                    'source_text': triple.source_text,
                    'chunk_id': triple.chunk_id,
                    'document_id': triple.document_id
                })
            
            return results
            
        except Exception as e:
            logger.error(f"查询实体失败: {str(e)}")
            return []
    
    def query_event_participants(
        self,
        db: Session,
        kb_id: int,
        event_name: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        查询事件的参与者
        
        例如：query_event_participants(db, kb_id, "桃园结义")
        返回：所有参与"桃园结义"的实体
        """
        try:
            # 查询所有 (X, 参与, event_name) 的三元组
            triples = db.query(KnowledgeTriple).filter(
                KnowledgeTriple.knowledge_base_id == kb_id,
                KnowledgeTriple.object == event_name,
                KnowledgeTriple.predicate == "参与"
            ).limit(limit).all()
            
            # 如果精确匹配失败，尝试模糊匹配
            if not triples:
                triples = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == kb_id,
                    KnowledgeTriple.object.contains(event_name),
                    KnowledgeTriple.predicate == "参与"
                ).limit(limit).all()
            
            results = []
            for triple in triples:
                results.append({
                    'participant': triple.subject,
                    'event': triple.object,
                    'relation': triple.predicate,
                    'confidence': triple.confidence,
                    'source_text': triple.source_text,
                    'chunk_id': triple.chunk_id,
                    'document_id': triple.document_id
                })
            
            logger.debug(f"查询事件 {event_name} 的参与者，找到 {len(results)} 个")
            return results
            
        except Exception as e:
            logger.error(f"查询事件参与者失败: {str(e)}")
            return []
    
    def query_relation_path(
        self,
        db: Session,
        kb_id: int,
        start_entity: str,
        end_entity: str,
        max_hops: int = 3
    ) -> List[List[Dict[str, Any]]]:
        """查询两个实体之间的路径"""
        try:
            paths = []
            visited = set()
            
            def dfs(current: str, target: str, path: List[Dict], hops: int):
                if hops > max_hops or current in visited:
                    return
                
                if current == target and len(path) > 0:
                    paths.append(path.copy())
                    return
                
                visited.add(current)
                
                # 查找包含当前实体的三元组
                triples = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == kb_id,
                    or_(
                        KnowledgeTriple.subject == current,
                        KnowledgeTriple.object == current
                    )
                ).limit(10).all()
                
                for triple in triples:
                    next_entity = triple.object if triple.subject == current else triple.subject
                    
                    if next_entity not in visited:
                        path.append({
                            'subject': triple.subject,
                            'predicate': triple.predicate,
                            'object': triple.object,
                            'confidence': triple.confidence
                        })
                        dfs(next_entity, target, path, hops + 1)
                        path.pop()
                
                visited.remove(current)
            
            dfs(start_entity, end_entity, [], 0)
            
            # 按路径长度和置信度排序
            paths.sort(key=lambda p: (len(p), -sum(t.get('confidence', 0) for t in p)))
            
            return paths[:5]  # 返回前5条路径
            
        except Exception as e:
            logger.error(f"查询关系路径失败: {str(e)}")
            return []
    
    def multi_hop_query(
        self,
        db: Session,
        kb_id: int,
        query: str,
        max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """多跳查询：从查询中提取实体，查找相关实体和关系"""
        try:
            # 提取查询中的实体
            entities = self._extract_entities_from_query(query)
            
            if not entities:
                return []
            
            all_triples = []
            visited_entities = set(entities)
            current_entities = set(entities)
            
            # 多跳搜索
            for hop in range(max_hops + 1):
                if not current_entities:
                    break
                
                new_triples = []
                next_entities = set()
                
                for entity in current_entities:
                    # 查询包含该实体的三元组
                    triples = db.query(KnowledgeTriple).filter(
                        KnowledgeTriple.knowledge_base_id == kb_id,
                        or_(
                            KnowledgeTriple.subject.contains(entity),
                            KnowledgeTriple.object.contains(entity)
                        )
                    ).limit(20).all()
                    
                    for triple in triples:
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
                        triple_key = (triple.subject, triple.predicate, triple.object)
                        if triple_key not in {(t['subject'], t['predicate'], t['object']) for t in all_triples}:
                            new_triples.append(triple_dict)
                            all_triples.append(triple_dict)
                            
                            # 收集新实体
                            if triple.subject not in visited_entities:
                                next_entities.add(triple.subject)
                            if triple.object not in visited_entities:
                                next_entities.add(triple.object)
                
                visited_entities.update(next_entities)
                current_entities = next_entities
                
                if not new_triples:
                    break
            
            # 按跳数和置信度排序
            all_triples.sort(key=lambda x: (x.get('hop', 0), -x.get('confidence', 0)))
            
            logger.info(f"多跳查询完成: 找到 {len(all_triples)} 个三元组, {len(visited_entities)} 个实体")
            return all_triples[:50]
            
        except Exception as e:
            logger.error(f"多跳查询失败: {str(e)}")
            return []
    
    def _extract_entities_from_query(self, query: str) -> List[str]:
        """从查询中提取实体（简单实现）"""
        # 这里可以使用NER模型或LLM提取实体
        # 简单实现：查找可能的人名、地名、机构名等
        
        entities = []
        
        # 查找可能的实体（大写字母开头的词、引号内的内容等）
        patterns = [
            r'["""]([^"""]+)["""]',  # 引号内的内容
            r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',  # 大写开头的词
            r'[《》]([^《》]+)[《》]',  # 书名号内的内容
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, query)
            entities.extend(matches)
        
        # 去重
        entities = list(set(entities))
        
        return entities[:5]  # 最多返回5个实体
    
    def get_entity_statistics(self, db: Session, kb_id: int) -> Dict[str, Any]:
        """获取知识图谱统计信息"""
        try:
            total_triples = db.query(KnowledgeTriple).filter(
                KnowledgeTriple.knowledge_base_id == kb_id
            ).count()
            
            # 统计实体数量
            subjects = db.query(KnowledgeTriple.subject).filter(
                KnowledgeTriple.knowledge_base_id == kb_id
            ).distinct().count()
            
            objects = db.query(KnowledgeTriple.object).filter(
                KnowledgeTriple.knowledge_base_id == kb_id
            ).distinct().count()
            
            # 统计关系类型
            predicates = db.query(
                KnowledgeTriple.predicate,
                func.count(KnowledgeTriple.id).label('count')
            ).filter(
                KnowledgeTriple.knowledge_base_id == kb_id
            ).group_by(KnowledgeTriple.predicate).order_by(
                func.count(KnowledgeTriple.id).desc()
            ).limit(10).all()
            
            return {
                'total_triples': total_triples,
                'unique_subjects': subjects,
                'unique_objects': objects,
                'unique_entities': subjects + objects,  # 近似值
                'top_relations': [{'predicate': p, 'count': c} for p, c in predicates]
            }
            
        except Exception as e:
            logger.error(f"获取图谱统计失败: {str(e)}")
            return {}
    
    def enhance_rag_context(
        self,
        db: Session,
        kb_id: int,
        query: str,
        vector_results: List[Dict[str, Any]],
        max_triples: int = 10
    ) -> Dict[str, Any]:
        """
        使用知识图谱增强RAG上下文
        
        Args:
            db: 数据库会话
            kb_id: 知识库ID
            query: 用户查询
            vector_results: 向量搜索结果
            max_triples: 最大三元组数量
            
        Returns:
            增强后的上下文，包含图谱三元组和相关实体
        """
        try:
            # 从向量结果中提取实体
            entities = set()
            for result in vector_results[:5]:  # 只从前5个结果提取
                content = result.get('content', '')
                extracted = self._extract_entities_from_query(content)
                entities.update(extracted)
            
            # 从查询中提取实体
            query_entities = self._extract_entities_from_query(query)
            entities.update(query_entities)
            
            # 查询相关三元组
            all_triples = []
            for entity in list(entities)[:5]:  # 最多查询5个实体
                entity_triples = self.query_entities(db, kb_id, entity, limit=5)
                all_triples.extend(entity_triples)
            
            # 去重
            seen = set()
            unique_triples = []
            for triple in all_triples:
                key = (triple['subject'], triple['predicate'], triple['object'])
                if key not in seen:
                    seen.add(key)
                    unique_triples.append(triple)
            
            # 按置信度排序
            unique_triples.sort(key=lambda x: x.get('confidence', 0), reverse=True)
            unique_triples = unique_triples[:max_triples]
            
            # 构建图谱上下文
            graph_context = ""
            if unique_triples:
                graph_context = "相关实体关系：\n"
                for triple in unique_triples:
                    graph_context += f"- {triple['subject']} {triple['predicate']} {triple['object']}\n"
            
            return {
                'graph_triples': unique_triples,
                'graph_context': graph_context,
                'entities': list(entities),
                'enhanced': len(unique_triples) > 0
            }
            
        except Exception as e:
            logger.error(f"增强RAG上下文失败: {str(e)}")
            return {
                'graph_triples': [],
                'graph_context': '',
                'entities': [],
                'enhanced': False
            }
    
    def _compute_high_frequency_entities(
        self,
        db: Session,
        kb_id: int,
        document_id: Optional[int] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        计算高频实体（章节级 + 全局级）
        
        目标：不是为了统计展示，而是为了提高知识图谱准确率
        - 章节级高频实体：用于局部上下文优化
        - 全局级高频实体：用于实体归一、置信度调整、规则优化
        
        Args:
            db: 数据库会话
            kb_id: 知识库ID
            document_id: 文档ID（可选，如果指定则只统计该文档）
            force_refresh: 是否强制刷新缓存
            
        Returns:
            {
                'chapter_entities': {section_title: [entities]},
                'global_entities': {entity_name: {count, chapters, type}},
                'entity_aliases': {alias: canonical_name}  # 别名归一映射
            }
        """
        cache_key = f"{kb_id}_{document_id or 'all'}"
        
        # 检查缓存
        if not force_refresh:
            with self._hf_cache_lock:
                if cache_key in self._hf_entity_cache:
                    logger.debug(f"使用缓存的高频实体数据: {cache_key}")
                    return self._hf_entity_cache[cache_key]
        
        try:
            logger.info(f"开始计算高频实体: kb_id={kb_id}, doc_id={document_id}")
            
            # 1. 从三元组中提取所有实体（subject + object）
            query = db.query(KnowledgeTriple).filter(
                KnowledgeTriple.knowledge_base_id == kb_id
            )
            if document_id:
                query = query.filter(KnowledgeTriple.document_id == document_id)
            
            triples = query.all()
            
            if not triples:
                logger.warning(f"未找到三元组，无法计算高频实体")
                return {'chapter_entities': {}, 'global_entities': {}, 'entity_aliases': {}}
            
            # 2. 通过chunk_id关联DocumentChunk，获取章节信息
            from models.database_models import DocumentChunk
            chunk_ids = [t.chunk_id for t in triples if t.chunk_id]
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.id.in_(chunk_ids)
            ).all()
            
            # 构建chunk_id -> chunk的映射
            chunk_map = {c.id: c for c in chunks}
            
            # 3. 章节级统计
            chapter_entity_counts: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(lambda: defaultdict(lambda: {
                'count': 0,
                'type': 'UNKNOWN',
                'chunk_ids': set()
            }))
            
            # 4. 全局级统计
            global_entity_counts: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
                'count': 0,
                'chapters': set(),
                'type': 'UNKNOWN',
                'first_chapter': None
            })
            
            # 5. 遍历三元组，统计实体
            for triple in triples:
                chunk = chunk_map.get(triple.chunk_id) if triple.chunk_id else None
                section_title = "__NO_SECTION__"
                
                if chunk and chunk.chunk_metadata:
                    section_title = chunk.chunk_metadata.get('section_title', '__NO_SECTION__')
                
                # 统计subject
                subj = triple.subject.strip()
                if subj and len(subj) >= 2:
                    # 章节级
                    chapter_entity_counts[section_title][subj]['count'] += 1
                    if triple.chunk_id:
                        chapter_entity_counts[section_title][subj]['chunk_ids'].add(triple.chunk_id)
                    
                    # 全局级
                    global_entity_counts[subj]['count'] += 1
                    global_entity_counts[subj]['chapters'].add(section_title)
                    if not global_entity_counts[subj]['first_chapter']:
                        global_entity_counts[subj]['first_chapter'] = section_title
                
                # 统计object
                obj = triple.object.strip()
                if obj and len(obj) >= 2:
                    # 章节级
                    chapter_entity_counts[section_title][obj]['count'] += 1
                    if triple.chunk_id:
                        chapter_entity_counts[section_title][obj]['chunk_ids'].add(triple.chunk_id)
                    
                    # 全局级
                    global_entity_counts[obj]['count'] += 1
                    global_entity_counts[obj]['chapters'].add(section_title)
                    if not global_entity_counts[obj]['first_chapter']:
                        global_entity_counts[obj]['first_chapter'] = section_title
            
            # 6. 构建章节级结果（只保留高频实体，top_k_per_chapter）
            chapter_entities = {}
            top_k_per_chapter = 30  # 每章节保留前30个高频实体
            
            for section_title, entities in chapter_entity_counts.items():
                sorted_entities = sorted(
                    entities.items(),
                    key=lambda x: x[1]['count'],
                    reverse=True
                )[:top_k_per_chapter]
                
                chapter_entities[section_title] = [
                    {
                        'name': name,
                        'count': info['count'],
                        'type': info['type']
                    }
                    for name, info in sorted_entities
                ]
            
            # 7. 构建全局级结果（只保留高频实体，top_k_global）
            top_k_global = 100  # 全局保留前100个高频实体
            sorted_global = sorted(
                global_entity_counts.items(),
                key=lambda x: (x[1]['count'], len(x[1]['chapters'])),
                reverse=True
            )[:top_k_global]
            
            global_entities = {}
            for name, info in sorted_global:
                global_entities[name] = {
                    'count': info['count'],
                    'chapter_count': len(info['chapters']),
                    'first_chapter': info['first_chapter'],
                    'type': info['type']
                }
            
            # 8. 简单的实体别名归一（基于规则和相似度）
            entity_aliases = self._build_entity_aliases(global_entities)
            
            result = {
                'chapter_entities': chapter_entities,
                'global_entities': global_entities,
                'entity_aliases': entity_aliases
            }
            
            # 缓存结果
            with self._hf_cache_lock:
                self._hf_entity_cache[cache_key] = result
            
            logger.info(f"高频实体计算完成: {len(chapter_entities)} 个章节, {len(global_entities)} 个全局高频实体")
            return result
            
        except Exception as e:
            logger.error(f"计算高频实体失败: {str(e)}", exc_info=True)
            return {'chapter_entities': {}, 'global_entities': {}, 'entity_aliases': {}}
    
    def _build_entity_aliases(self, global_entities: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        构建实体别名归一映射
        
        简单规则：
        1. 常见别名模式（如：刘备/玄德/刘玄德）
        2. 基于频次：高频实体作为标准名，低频实体作为别名
        3. 字符串相似度（简单版）
        """
        aliases = {}
        
        # 常见中文别名模式（可以扩展）
        common_patterns = [
            # 三国人物别名
            (r'^(.+?)(字|号|又称)(.+?)$', lambda m: (m.group(3), m.group(1))),
        ]
        
        # 按频次排序，高频的作为标准名
        sorted_entities = sorted(
            global_entities.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        
        # 简单的字符串相似度匹配（相同前缀/后缀）
        for i, (name1, info1) in enumerate(sorted_entities):
            if name1 in aliases:  # 已经是别名了，跳过
                continue
            
            for j, (name2, info2) in enumerate(sorted_entities[i+1:], start=i+1):
                if name2 in aliases:  # 已经是别名了，跳过
                    continue
                
                # 规则1: 完全包含关系（如"刘备"包含"玄德"）
                if name1 in name2 or name2 in name1:
                    # 频次高的作为标准名
                    if info1['count'] >= info2['count']:
                        aliases[name2] = name1
                    else:
                        aliases[name1] = name2
                    continue
                
                # 规则2: 相同前缀（如"刘玄德"和"刘备"）
                if len(name1) >= 2 and len(name2) >= 2:
                    if name1[0] == name2[0] and abs(len(name1) - len(name2)) <= 2:
                        # 频次高的作为标准名
                        if info1['count'] >= info2['count']:
                            aliases[name2] = name1
                        else:
                            aliases[name1] = name2
        
        logger.debug(f"构建了 {len(aliases)} 个别名映射")
        return aliases
    
    def _get_high_frequency_entities(
        self,
        db: Session,
        kb_id: int,
        document_id: Optional[int] = None,
        section_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取高频实体（带缓存）
        
        Args:
            db: 数据库会话
            kb_id: 知识库ID
            document_id: 文档ID（可选）
            section_title: 章节标题（可选，用于获取章节级高频实体）
            
        Returns:
            高频实体信息
        """
        hf_data = self._compute_high_frequency_entities(db, kb_id, document_id)
        
        if section_title:
            # 返回指定章节的高频实体
            chapter_entities = hf_data['chapter_entities'].get(section_title, [])
            return {
                'chapter_entities': chapter_entities,
                'global_entities': hf_data['global_entities'],
                'entity_aliases': hf_data['entity_aliases']
            }
        else:
            return hf_data
    
    def _is_high_frequency_entity(
        self,
        entity_name: str,
        hf_data: Dict[str, Any],
        section_title: Optional[str] = None
    ) -> Tuple[bool, float]:
        """
        判断实体是否为高频实体，返回(is_hf, frequency_score)
        
        frequency_score: 0.0-1.0，表示实体频率的归一化分数
        """
        # 先做别名归一
        normalized_name = hf_data['entity_aliases'].get(entity_name, entity_name)
        
        global_entities = hf_data['global_entities']
        
        # 检查全局高频实体
        if normalized_name in global_entities:
            global_info = global_entities[normalized_name]
            # 频率分数 = min(1.0, count / 100)  # 假设100次为满分
            frequency_score = min(1.0, global_info['count'] / 100.0)
            
            # 如果指定了章节，检查章节级高频
            if section_title:
                chapter_entities = hf_data['chapter_entities'].get(section_title, [])
                chapter_hf = any(e['name'] == normalized_name for e in chapter_entities)
                if chapter_hf:
                    frequency_score = min(1.0, frequency_score + 0.2)  # 章节级额外加分
            
            return True, frequency_score
        
        return False, 0.0
    
    def _extract_entities_by_rules(self, text: str) -> List[Dict[str, Any]]:
        """
        简单规则实体识别（在NER未加载或高频实体候选阶段使用）
        
        目标：提供一个轻量级备选方案，主要识别人名/专有名词候选，不追求完美，只要能给出候选集即可。
        """
        entities: List[Dict[str, Any]] = []
        if not text:
            return entities

        # 1. 基于连续中文字符的粗略识别（2-4个连续中文字符）
        #    不强依赖姓氏表，避免漏掉特殊名字
        name_pattern = r"[\u4e00-\u9fa5]{2,4}"
        for m in re.finditer(name_pattern, text):
            ent_text = m.group(0)
            # 过滤一些明显无意义的短词
            if ent_text in ("第一", "第二", "第三", "其中", "我们", "你们", "他们"):
                continue
            entities.append({
                "text": ent_text,
                "label": "UNKNOWN",
                "start": m.start(),
                "end": m.end()
            })

        # 2. 简单去重（按 text + 位置）
        unique: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        for ent in entities:
            key = (ent["text"], ent["start"], ent["end"])
            if key not in unique:
                unique[key] = ent

        result = list(unique.values())
        logger.debug(f"规则实体识别得到 {len(result)} 个候选实体")
        return result
    
    def _extract_all_candidate_entities(
        self,
        text: str,
        db: Optional[Session] = None,
        kb_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        提取所有疑似高频实体（候选实体）
        
        策略：
        1. 优先使用NER模型识别实体
        2. 如果没有NER模型，使用规则识别
        3. 统计每个实体的出现频次
        
        Returns:
            List[Dict] 每个实体包含：text, label, start, end, frequency
        """
        entities = []
        
        # 1. 优先使用NER模型
        if self.ie_model_service and self.ie_model_service.is_available():
            entities = self.ie_model_service.extract_entities(text)
            logger.debug(f"NER识别到 {len(entities)} 个候选实体")
        else:
            # 2. 回退到规则识别
            entities = self._extract_entities_by_rules(text)
            logger.debug(f"规则识别到 {len(entities)} 个候选实体")
        
        # 3. 统计频次（如果提供了数据库，可以从已有三元组中统计）
        entity_freq = defaultdict(int)
        if db and kb_id:
            try:
                # 从已有三元组中统计实体频次
                existing_triples = db.query(KnowledgeTriple).filter(
                    KnowledgeTriple.knowledge_base_id == kb_id
                ).all()
                
                for triple in existing_triples:
                    entity_freq[triple.subject] += 1
                    entity_freq[triple.object] += 1
            except Exception as e:
                logger.debug(f"统计已有实体频次失败: {str(e)}")
        
        # 4. 为每个实体添加频次信息
        for entity in entities:
            entity_text = entity.get("text", "")
            entity["frequency"] = entity_freq.get(entity_text, 0)
        
        return entities
    
    def _normalize_entities_with_llm(
        self,
        entities: List[Dict[str, Any]],
        kb_id: int,
        db: Optional[Session] = None
    ) -> Dict[str, str]:
        """
        使用LLM识别相似概念并建立别名关联
        
        例如：刘备和玄德 -> {"玄德": "刘备", "刘玄德": "刘备"}
        
        Args:
            entities: 候选实体列表
            kb_id: 知识库ID
            db: 数据库会话（用于保存归一结果）
            
        Returns:
            别名映射字典 {alias: canonical_name}
        """
        if not entities:
            return {}
        
        # 1. 从数据库中加载已有的高频实体和别名映射
        alias_map = {}
        if db:
            try:
                hf_entities = db.query(HighFrequencyEntity).filter(
                    HighFrequencyEntity.knowledge_base_id == kb_id
                ).all()
                
                for hf_entity in hf_entities:
                    canonical = hf_entity.entity_name
                    alias_map[canonical] = canonical  # 标准名称映射到自己
                    if hf_entity.aliases:
                        for alias in hf_entity.aliases:
                            alias_map[alias] = canonical
            except Exception as e:
                logger.warning(f"加载已有高频实体失败: {str(e)}")
        
        # 2. 提取实体名称列表（去重）
        entity_names = list(set([e.get("text", "") for e in entities if e.get("text")]))
        
        if not entity_names:
            return alias_map
        
        # 3. 如果实体数量太多，分批处理
        batch_size = 50
        all_aliases = {}
        
        for i in range(0, len(entity_names), batch_size):
            batch = entity_names[i:i + batch_size]
            
            try:
                # 4. 调用LLM识别相似概念
                prompt = f"""请分析以下实体列表，识别出哪些实体指的是同一个概念（人物、地点、组织等），并将它们归类。

要求：
1. 识别别名关系（如：刘备、玄德、刘玄德、先主 -> 都指向"刘备"）
2. 识别简称和全称（如：张飞、张翼德 -> 都指向"张飞"）
3. 识别不同写法（如：关羽、关云长 -> 都指向"关羽"）
4. 对于每个组，选择一个最标准、最常见的名称作为主名称
5. 只输出JSON格式，不要其他解释

实体列表：
{json.dumps(batch, ensure_ascii=False, indent=2)}

输出格式（JSON）：
{{
  "groups": [
    {{
      "canonical": "刘备",
      "aliases": ["玄德", "刘玄德", "先主"]
    }},
    {{
      "canonical": "张飞",
      "aliases": ["张翼德", "翼德"]
    }}
  ]
}}"""

                # 使用线程池执行异步LLM调用
                def run_async():
                    """在新线程中运行异步代码"""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        llm = get_llm_helper()
                        messages = [
                            {
                                "role": "system",
                                "content": "你是一个专业的实体归一专家，擅长识别不同名称指向的同一实体。"
                            },
                            {"role": "user", "content": prompt}
                        ]
                        return new_loop.run_until_complete(llm.call(messages, max_tokens=2000, temperature=0.1))
                    finally:
                        new_loop.close()
                
                executor = self._get_executor()
                if executor is None:
                    logger.warning("无法创建线程池，跳过LLM实体归一")
                    continue
                
                try:
                    result = executor.submit(run_async).result(timeout=30)
                except concurrent.futures.TimeoutError:
                    logger.warning("LLM实体归一超时")
                    continue
                except Exception as e:
                    logger.warning(f"LLM实体归一失败: {str(e)}")
                    continue
                
                # 5. 解析LLM返回的JSON
                try:
                    # 尝试提取JSON（可能包含markdown代码块）
                    json_str = result.strip()
                    if "```json" in json_str:
                        json_str = re.search(r"```json\s*(.*?)\s*```", json_str, re.DOTALL).group(1)
                    elif "```" in json_str:
                        json_str = re.search(r"```\s*(.*?)\s*```", json_str, re.DOTALL).group(1)
                    
                    parsed = json.loads(json_str)
                    groups = parsed.get("groups", [])
                    
                    # 6. 构建别名映射
                    for group in groups:
                        canonical = group.get("canonical", "").strip()
                        aliases = group.get("aliases", [])
                        
                        if canonical:
                            # 标准名称映射到自己
                            all_aliases[canonical] = canonical
                            # 别名映射到标准名称
                            for alias in aliases:
                                alias = alias.strip()
                                if alias and alias != canonical:
                                    all_aliases[alias] = canonical
                    
                    logger.debug(f"LLM识别到 {len(groups)} 个实体组，{len(all_aliases)} 个别名映射")
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"LLM返回的实体归一JSON解析失败: {str(e)}, 原始输出: {result[:200]}")
                except Exception as e:
                    logger.warning(f"处理LLM实体归一结果失败: {str(e)}")
                    
            except Exception as e:
                logger.warning(f"LLM实体归一失败: {str(e)}")
                continue
        
        # 7. 合并到已有映射
        alias_map.update(all_aliases)
        
        # 8. 保存到数据库（如果提供了db）
        if db:
            try:
                self._save_entity_aliases_to_db(db, kb_id, alias_map)
            except Exception as e:
                logger.warning(f"保存实体别名到数据库失败: {str(e)}")
        
        return alias_map
    
    def _save_entity_aliases_to_db(
        self,
        db: Session,
        kb_id: int,
        alias_map: Dict[str, str]
    ):
        """保存实体别名映射到数据库"""
        # 按标准名称分组
        canonical_groups = defaultdict(list)
        for alias, canonical in alias_map.items():
            if alias != canonical:
                canonical_groups[canonical].append(alias)
        
        # 更新或创建高频实体记录
        for canonical, aliases in canonical_groups.items():
            hf_entity = db.query(HighFrequencyEntity).filter(
                HighFrequencyEntity.knowledge_base_id == kb_id,
                HighFrequencyEntity.entity_name == canonical
            ).first()
            
            if hf_entity:
                # 更新别名列表（合并去重）
                existing_aliases = set(hf_entity.aliases or [])
                existing_aliases.update(aliases)
                hf_entity.aliases = list(existing_aliases)
                hf_entity.updated_at = datetime.utcnow()
            else:
                # 创建新记录
                hf_entity = HighFrequencyEntity(
                    knowledge_base_id=kb_id,
                    entity_name=canonical,
                    aliases=aliases,
                    frequency=0,
                    is_manual=False
                )
                db.add(hf_entity)
        
        db.commit()
    
    def _extract_triples_between_hf_entities(
        self,
        text: str,
        hf_entity_names: Set[str],
        alias_map: Dict[str, str],
        doc_cache: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, str, str, float]]:
        """
        只提取高频实体之间的关系
        
        Args:
            text: 输入文本
            hf_entity_names: 高频实体名称集合
            alias_map: 别名映射 {alias: canonical}
            doc_cache: 文档级别的缓存（动态规则等）
            
        Returns:
            三元组列表
        """
        triples = []
        
        # 1. 归一化实体名称集合（包含别名）
        normalized_hf_entities = set(hf_entity_names)
        for alias, canonical in alias_map.items():
            if canonical in hf_entity_names:
                normalized_hf_entities.add(alias)
        
        # 2. 使用NER识别文本中的实体位置
        entities_in_text = []
        if self.ie_model_service and self.ie_model_service.is_available():
            entities_in_text = self.ie_model_service.extract_entities(text)
        else:
            entities_in_text = self._extract_entities_by_rules(text)
        
        # 3. 过滤：只保留高频实体
        hf_entities_in_text = []
        for entity in entities_in_text:
            entity_text = entity.get("text", "")
            # 检查是否是高频实体（包括别名）
            normalized = alias_map.get(entity_text, entity_text)
            if normalized in hf_entity_names or entity_text in normalized_hf_entities:
                hf_entities_in_text.append({
                    **entity,
                    "normalized_name": normalized
                })
        
        if len(hf_entities_in_text) < 2:
            logger.debug(f"文本中高频实体数量不足（{len(hf_entities_in_text)}），跳过关系抽取")
            return triples
        
        # 4. 使用规则提取高频实体之间的关系
        # 复用现有的规则抽取逻辑，但只关注高频实体
        rule_triples = self._extract_triples_rule_based(text, hf_data=None, section_title=None)
        
        # 5. 过滤：只保留两个都是高频实体的三元组
        for triple in rule_triples:
            subj, pred, obj = triple[0], triple[1], triple[2]
            conf = triple[3] if len(triple) > 3 else 0.8
            
            # 归一化实体名
            normalized_subj = alias_map.get(subj, subj)
            normalized_obj = alias_map.get(obj, obj)
            
            # 检查是否都是高频实体
            if normalized_subj in hf_entity_names and normalized_obj in hf_entity_names:
                triples.append((normalized_subj, pred, normalized_obj, conf))
        
        logger.debug(f"高频实体关系抽取：从 {len(rule_triples)} 个规则三元组中筛选出 {len(triples)} 个高频实体关系")
        
        return triples
    
    def _adjust_triples_with_hf_entities(
        self,
        triples: List[Tuple[str, str, str, float]],
        hf_data: Dict[str, Any],
        section_title: Optional[str] = None
    ) -> List[Tuple[str, str, str, float]]:
        """
        使用高频实体调整三元组：
        1. 实体归一（别名合并）
        2. 置信度调整（高频实体相关的关系更容易保留）
        3. 过滤低价值关系（低频实体+低频实体的关系可以更严格过滤）
        
        Args:
            triples: 原始三元组列表
            hf_data: 高频实体数据
            section_title: 章节标题（可选）
            
        Returns:
            调整后的三元组列表
        """
        if not hf_data or not triples:
            return triples
        
        adjusted_triples = []
        entity_aliases = hf_data.get('entity_aliases', {})
        
        # 置信度调整阈值
        MIN_CONFIDENCE_LOW_FREQ = 0.6  # 低频实体关系的最低置信度
        MIN_CONFIDENCE_HIGH_FREQ = 0.3  # 高频实体关系的最低置信度（更宽松）
        CONFIDENCE_BOOST_HF = 0.15  # 高频实体关系的置信度提升
        
        for triple in triples:
            if len(triple) < 3:
                continue
            
            subj, pred, obj = triple[0], triple[1], triple[2]
            original_conf = triple[3] if len(triple) > 3 else 0.8
            
            # 1. 实体归一（别名合并）
            normalized_subj = entity_aliases.get(subj, subj)
            normalized_obj = entity_aliases.get(obj, obj)
            
            # 2. 检查是否为高频实体
            is_hf_subj, freq_score_subj = self._is_high_frequency_entity(normalized_subj, hf_data, section_title)
            is_hf_obj, freq_score_obj = self._is_high_frequency_entity(normalized_obj, hf_data, section_title)
            
            # 3. 调整置信度
            adjusted_conf = original_conf
            
            # 3.1 如果至少有一个是高频实体，提升置信度
            if is_hf_subj or is_hf_obj:
                # 根据频率分数提升置信度
                max_freq_score = max(freq_score_subj, freq_score_obj)
                adjusted_conf = min(1.0, original_conf + CONFIDENCE_BOOST_HF * max_freq_score)
                # 降低最低置信度阈值
                min_conf = MIN_CONFIDENCE_HIGH_FREQ
            else:
                # 两个都是低频实体，提高最低置信度阈值
                min_conf = MIN_CONFIDENCE_LOW_FREQ
            
            # 3.2 如果两个都是高频实体，额外提升
            if is_hf_subj and is_hf_obj:
                adjusted_conf = min(1.0, adjusted_conf + 0.1)
            
            # 4. 过滤低价值关系
            if adjusted_conf < min_conf:
                logger.debug(f"过滤低价值关系: ({normalized_subj}, {pred}, {normalized_obj}), 置信度: {adjusted_conf:.2f} < {min_conf:.2f}")
                continue
            
            # 5. 使用归一化后的实体名
            adjusted_triples.append((normalized_subj, pred, normalized_obj, adjusted_conf))
        
        logger.debug(f"高频实体调整: {len(triples)} -> {len(adjusted_triples)} 个三元组")
        return adjusted_triples