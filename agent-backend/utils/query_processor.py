import re
import json
from typing import List, Dict, Any, Optional, Tuple
from utils.log_helper import get_logger

logger = get_logger("query_processor")

class QueryProcessor:
    """查询处理器，支持查询扩展、多轮对话和上下文理解"""
    
    def __init__(self):
        self.query_history: Dict[str, List[Dict[str, Any]]] = {}  # user_id -> query_history
        self.max_history_length = 10
        
    def process_query(self, query: str, user_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理查询"""
        try:
            # 预处理查询
            processed_query = self._preprocess_query(query)
            
            # 查询扩展
            expanded_query = self._expand_query(processed_query, user_id)
            
            # 查询意图识别
            intent = self._identify_intent(processed_query)
            
            # 实体提取
            entities = self._extract_entities(processed_query)
            
            # 查询重写
            rewritten_query = self._rewrite_query(expanded_query, intent, entities, user_id)
            
            # 保存查询历史
            self._save_query_history(user_id, {
                "original_query": query,
                "processed_query": processed_query,
                "expanded_query": expanded_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "entities": entities,
                "timestamp": self._get_timestamp()
            })
            
            return {
                "original_query": query,
                "processed_query": processed_query,
                "expanded_query": expanded_query,
                "rewritten_query": rewritten_query,
                "intent": intent,
                "entities": entities,
                "context": context or {}
            }
            
        except Exception as e:
            logger.error(f"处理查询失败: {str(e)}")
            return {
                "original_query": query,
                "processed_query": query,
                "expanded_query": query,
                "rewritten_query": query,
                "intent": "unknown",
                "entities": [],
                "context": context or {}
            }
    
    def _preprocess_query(self, query: str) -> str:
        """预处理查询"""
        # 移除多余空格
        query = re.sub(r'\s+', ' ', query.strip())
        
        # 移除特殊字符但保留标点
        query = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()[]{}""''""''—–-]', '', query)
        
        # 统一标点符号
        query = query.replace('？', '?').replace('！', '!').replace('，', ',').replace('。', '.')
        
        return query
    
    def _expand_query(self, query: str, user_id: str) -> str:
        """查询扩展"""
        try:
            # 获取用户查询历史
            history = self.query_history.get(user_id, [])
            
            # 基于历史查询进行扩展
            expanded_terms = []
            
            # 添加同义词
            synonyms = self._get_synonyms(query)
            expanded_terms.extend(synonyms)
            
            # 添加相关术语
            related_terms = self._get_related_terms(query, history)
            expanded_terms.extend(related_terms)
            
            # 构建扩展查询
            if expanded_terms:
                expanded_query = f"{query} {' '.join(expanded_terms)}"
            else:
                expanded_query = query
            
            return expanded_query
            
        except Exception as e:
            logger.error(f"查询扩展失败: {str(e)}")
            return query
    
    def _identify_intent(self, query: str) -> str:
        """识别查询意图"""
        query_lower = query.lower()
        
        # 定义意图模式
        intent_patterns = {
            "factual": [
                r"什么是|what is|什么是|定义|definition|解释|explain",
                r"如何|how to|怎么|方法|method|步骤|step",
                r"为什么|why|原因|reason|因为|because"
            ],
            "comparative": [
                r"比较|compare|对比|versus|vs|区别|difference|差异",
                r"哪个更好|which is better|哪个更|which is more"
            ],
            "procedural": [
                r"怎么做|how to do|如何操作|how to operate|步骤|step",
                r"流程|process|程序|procedure|方法|method"
            ],
            "descriptive": [
                r"描述|describe|介绍|introduce|说明|说明|详细|detail",
                r"特点|feature|特性|characteristic|属性|attribute"
            ],
            "analytical": [
                r"分析|analyze|分析|analysis|评估|evaluate|评价|assess",
                r"优缺点|pros and cons|利弊|advantages and disadvantages"
            ],
            "creative": [
                r"创意|creative|想法|idea|建议|suggestion|推荐|recommend",
                r"设计|design|方案|solution|策略|strategy"
            ]
        }
        
        # 匹配意图
        for intent, patterns in intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent
        
        return "general"
    
    def _extract_entities(self, query: str) -> List[Dict[str, Any]]:
        """提取实体"""
        entities = []
        
        # 提取时间实体
        time_patterns = [
            r'\d{4}年', r'\d{1,2}月', r'\d{1,2}日',
            r'今天|明天|昨天|本周|上周|下周|本月|上月|下月|今年|去年|明年',
            r'january|february|march|april|may|june|july|august|september|october|november|december',
            r'monday|tuesday|wednesday|thursday|friday|saturday|sunday'
        ]
        
        for pattern in time_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "type": "time",
                    "value": match,
                    "start": query.find(match),
                    "end": query.find(match) + len(match)
                })
        
        # 提取数字实体
        number_patterns = [
            r'\d+', r'\d+\.\d+', r'\d+%', r'\d+元', r'\d+美元', r'\d+欧元'
        ]
        
        for pattern in number_patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                entities.append({
                    "type": "number",
                    "value": match,
                    "start": query.find(match),
                    "end": query.find(match) + len(match)
                })
        
        # 提取地点实体
        location_patterns = [
            r'北京|上海|广州|深圳|杭州|南京|武汉|成都|西安|重庆',
            r'中国|美国|日本|韩国|英国|法国|德国|意大利|西班牙|加拿大',
            r'beijing|shanghai|guangzhou|shenzhen|hangzhou|nanjing|wuhan|chengdu|xi\'an|chongqing'
        ]
        
        for pattern in location_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            for match in matches:
                entities.append({
                    "type": "location",
                    "value": match,
                    "start": query.find(match),
                    "end": query.find(match) + len(match)
                })
        
        return entities
    
    def _rewrite_query(self, query: str, intent: str, entities: List[Dict[str, Any]], user_id: str) -> str:
        """查询重写"""
        try:
            # 基于意图重写查询
            if intent == "factual":
                # 事实性查询，添加更多上下文
                query = f"请详细解释：{query}"
            elif intent == "comparative":
                # 比较性查询，强调对比
                query = f"请对比分析：{query}"
            elif intent == "procedural":
                # 程序性查询，强调步骤
                query = f"请提供详细步骤：{query}"
            elif intent == "analytical":
                # 分析性查询，强调深度分析
                query = f"请深入分析：{query}"
            
            # 基于实体重写查询
            if entities:
                entity_info = " ".join([e["value"] for e in entities])
                query = f"{query} 涉及：{entity_info}"
            
            return query
            
        except Exception as e:
            logger.error(f"查询重写失败: {str(e)}")
            return query
    
    def _get_synonyms(self, query: str) -> List[str]:
        """获取同义词"""
        # 简单的同义词映射
        synonym_map = {
            "人工智能": ["AI", "artificial intelligence", "机器学习", "machine learning"],
            "机器学习": ["ML", "machine learning", "深度学习", "deep learning"],
            "深度学习": ["deep learning", "神经网络", "neural network"],
            "数据分析": ["data analysis", "数据挖掘", "data mining"],
            "编程": ["programming", "coding", "开发", "development"],
            "算法": ["algorithm", "算法设计", "algorithm design"],
            "数据库": ["database", "DB", "数据存储", "data storage"],
            "网络": ["network", "互联网", "internet", "web"],
            "安全": ["security", "安全性", "保护", "protection"],
            "性能": ["performance", "效率", "efficiency", "优化", "optimization"]
        }
        
        synonyms = []
        for term, syns in synonym_map.items():
            if term in query:
                synonyms.extend(syns)
        
        return synonyms[:3]  # 限制同义词数量
    
    def _get_related_terms(self, query: str, history: List[Dict[str, Any]]) -> List[str]:
        """获取相关术语"""
        related_terms = []
        
        # 基于查询历史获取相关术语
        for hist_query in history[-3:]:  # 只看最近3个查询
            if hist_query.get("entities"):
                for entity in hist_query["entities"]:
                    if entity["type"] in ["location", "time", "number"]:
                        related_terms.append(entity["value"])
        
        return related_terms[:2]  # 限制相关术语数量
    
    def _save_query_history(self, user_id: str, query_info: Dict[str, Any]):
        """保存查询历史"""
        if user_id not in self.query_history:
            self.query_history[user_id] = []
        
        self.query_history[user_id].append(query_info)
        
        # 限制历史长度
        if len(self.query_history[user_id]) > self.max_history_length:
            self.query_history[user_id] = self.query_history[user_id][-self.max_history_length:]
    
    def get_query_history(self, user_id: str) -> List[Dict[str, Any]]:
        """获取查询历史"""
        return self.query_history.get(user_id, [])
    
    def clear_query_history(self, user_id: str):
        """清除查询历史"""
        if user_id in self.query_history:
            del self.query_history[user_id]
    
    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """分析查询复杂度"""
        complexity_score = 0
        
        # 长度复杂度
        if len(query) > 100:
            complexity_score += 2
        elif len(query) > 50:
            complexity_score += 1
        
        # 实体复杂度
        entities = self._extract_entities(query)
        complexity_score += len(entities)
        
        # 意图复杂度
        intent = self._identify_intent(query)
        if intent in ["analytical", "comparative"]:
            complexity_score += 2
        elif intent in ["procedural", "creative"]:
            complexity_score += 1
        
        # 查询类型
        query_type = "simple"
        if complexity_score >= 5:
            query_type = "complex"
        elif complexity_score >= 3:
            query_type = "medium"
        
        return {
            "complexity_score": complexity_score,
            "query_type": query_type,
            "entity_count": len(entities),
            "intent": intent,
            "length": len(query)
        }
    
    def suggest_query_improvements(self, query: str) -> List[str]:
        """建议查询改进"""
        suggestions = []
        
        # 检查查询长度
        if len(query) < 10:
            suggestions.append("查询太短，请提供更多详细信息")
        
        # 检查是否包含具体实体
        entities = self._extract_entities(query)
        if not entities:
            suggestions.append("建议添加具体的时间、地点或数字信息")
        
        # 检查意图明确性
        intent = self._identify_intent(query)
        if intent == "general":
            suggestions.append("建议明确查询意图，如：解释、比较、分析等")
        
        # 检查是否包含关键词
        if not re.search(r'[a-zA-Z\u4e00-\u9fff]', query):
            suggestions.append("查询应包含有意义的文字内容")
        
        return suggestions
