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
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from models.database_models import KnowledgeTriple, DocumentChunk, KnowledgeBase
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
# ner_rule: 使用NER识别实体 + 规则提取关系（推荐，速度快且准确，支持动态规则生成）
KG_EXTRACT_MODE = os.getenv("KG_EXTRACT_MODE", "ner_rule").lower()
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
        document_text: Optional[str] = None  # 可选：传入完整文档文本用于分析和规则生成
    ) -> List[Dict[str, Any]]:
        """
        从文本中提取实体和关系，返回三元组列表
        
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
            # 根据模式选择抽取方法
            triples: List[Tuple[str, str, str, float]] = []
            
            if KG_EXTRACT_MODE == "ner_rule":
                # NER + 规则混合模式：使用NER识别实体，规则提取关系
                if self.ie_model_service and self.ie_model_service.is_available():
                    # 获取或生成文档级别的分析和规则（每个文档只分析一次）
                    doc_cache = self._get_or_create_document_analysis(doc_id, document_text or text)
                    triples = self._extract_triples_ner_rule_hybrid(text, doc_cache)
                    logger.debug(f"NER+规则混合抽取得到 {len(triples)} 个三元组")
                else:
                    # NER模型未加载，回退到纯规则模式
                    logger.warning("NER模型未加载，回退到纯规则模式")
                    triples = self._extract_triples_rule_based(text)
            elif KG_EXTRACT_MODE == "model":
                if self.ie_model_service and self.ie_model_service.is_available():
                    # 使用专用IE模型抽取（NER + RE）
                    model_triples = self.ie_model_service.extract_triples(text)
                    triples = model_triples
                    logger.debug(f"模型抽取得到 {len(triples)} 个三元组")
                else:
                    # 模型未加载，回退到规则模式
                    logger.warning("IE模型未加载，回退到规则模式")
                    triples = self._extract_triples_rule_based(text)
            elif KG_EXTRACT_MODE == "rule":
                # 纯规则模式
                triples = self._extract_triples_rule_based(text)
            elif KG_EXTRACT_MODE == "llm":
                # 纯LLM模式
                triples = self._extract_triples_with_llm(text)
            else:  # hybrid 模式（默认）
                # 1) 规则优先：快速规则抽取
                rule_triples = self._extract_triples_rule_based(text)
                triples = rule_triples
                
                # 2) 只在规则抽取结果较少时调用 LLM 补充
                if len(rule_triples) < 2:
                    llm_triples = self._extract_triples_with_llm(text)
                    # 合并规则和LLM结果
                    seen = set((t[0], t[1], t[2]) for t in triples)
                    for t in llm_triples:
                        key = (t[0], t[1], t[2])
                        if key not in seen:
                            seen.add(key)
                            triples.append(t)
            
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
            logger.error(f"提取实体和关系失败: {str(e)}")
            return []
    
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
    
    def _extract_triples_rule_based(self, text: str) -> List[Tuple[str, str, str, float]]:
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
            # X 说 Y
            (r"(.+?)(说|道|曰)(.+)", "说", 1, 3),
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
                if len(subj) > 100 or len(obj) > 100 or len(pred) > 20:
                    continue
                # 过滤掉明显不是实体的内容（如单个字符、标点等）
                if len(subj) < 2 or len(obj) < 2:
                    continue
                
                # 置信度：规则匹配给个中等偏上的值
                conf = 0.8
                triples.append((subj, pred, obj, conf))
        
        if triples:
            logger.debug(f"规则抽取得到 {len(triples)} 个三元组")
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
        doc_cache: Optional[Dict[str, Any]] = None
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
            return self._extract_triples_rule_based(text)
        
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
        
        logger.info(f"总共使用 {len(relation_patterns)} 个规则（{len(default_patterns)} 个默认 + {len(dynamic_rules)} 个动态）")
        
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
