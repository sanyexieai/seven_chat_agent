# -*- coding: utf-8 -*-
"""
信息抽取模型服务（NER + RE）
使用组合1：RoBERTa-CLUE NER + CasRel RE
"""
import os
from typing import List, Dict, Any, Tuple, Optional
import torch

from utils.log_helper import get_logger

logger = get_logger("ie_model_service")

# 配置
USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"
IE_MODEL_ENABLED = os.getenv("IE_MODEL_ENABLED", "true").lower() == "true"  # 默认启用


class IEModelService:
    """信息抽取模型服务（NER + RE）"""
    
    def __init__(self):
        self.ner_model = None
        self.re_model = None
        self.ner_tokenizer = None
        self.re_tokenizer = None
        self.device = "cuda" if (USE_GPU and torch.cuda.is_available()) else "cpu"
        self._models_loaded = False
        
        if IE_MODEL_ENABLED:
            self._load_models()
        else:
            logger.info("IE模型服务未启用（设置 IE_MODEL_ENABLED=true 启用）")
    
    def _load_models(self):
        """加载NER和RE模型"""
        try:
            logger.info("开始加载信息抽取模型...")
            
            # NER模型：RoBERTa-CLUE
            ner_model_name = "uer/roberta-base-finetuned-cluener2020-chinese"
            logger.info(f"加载NER模型: {ner_model_name} (设备: {self.device})")
            
            try:
                from transformers import AutoTokenizer, AutoModelForTokenClassification
                self.ner_tokenizer = AutoTokenizer.from_pretrained(ner_model_name)
                self.ner_model = AutoModelForTokenClassification.from_pretrained(ner_model_name)
                self.ner_model.to(self.device)
                self.ner_model.eval()
                logger.info(f"NER模型加载成功: {ner_model_name}")
            except Exception as e:
                logger.error(f"加载NER模型失败: {str(e)}")
                logger.error("请确保已安装 transformers 库，并已下载模型权重")
                raise
            
            # RE模型：CasRel（可选，当前使用NER+规则混合模式时不需要）
            # 注意：CasRel的中文权重可能需要从其他源获取
            # 当前默认使用 ner_rule 模式（NER识别实体 + 规则提取关系），RE模型是可选的
            re_model_name = os.getenv("RE_MODEL_NAME", "yubowen-ph/CasRel-bert-base-chinese")
            logger.info(f"尝试加载RE模型（可选）: {re_model_name}")
            
            try:
                # CasRel模型可能需要自定义加载逻辑
                # 这里提供一个基础框架
                from transformers import AutoTokenizer, AutoModel
                self.re_tokenizer = AutoTokenizer.from_pretrained(re_model_name)
                self.re_model = AutoModel.from_pretrained(re_model_name)
                self.re_model.to(self.device)
                self.re_model.eval()
                logger.info(f"RE模型加载成功: {re_model_name}")
            except Exception as e:
                # RE模型加载失败是正常的，因为：
                # 1. 当前使用 ner_rule 模式，使用NER识别实体 + 规则提取关系，不需要RE模型
                # 2. RE模型在HuggingFace上可能不存在或需要特殊配置
                logger.info(f"RE模型加载失败（这是正常的，当前使用NER+规则混合模式）: {str(e)[:200]}")
                logger.info("RE模型是可选的，系统将使用规则模式提取关系（NER+规则混合模式）")
                # RE模型加载失败不影响NER模型使用
                self.re_model = None
                self.re_tokenizer = None
            
            self._models_loaded = True
            logger.info("信息抽取模型加载完成")
            
        except Exception as e:
            logger.error(f"加载信息抽取模型失败: {str(e)}", exc_info=True)
            self._models_loaded = False
            raise
    
    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """使用NER模型提取实体"""
        if not self._models_loaded or not self.ner_model:
            logger.warning("NER模型未加载，无法提取实体")
            return []
        
        try:
            # 使用NER模型进行实体识别
            inputs = self.ner_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.ner_model(**inputs)
                predictions = torch.argmax(outputs.logits, dim=-1)
            
            # 解析实体标签
            entities = []
            # 获取标签ID到标签名的映射
            id2label = self.ner_model.config.id2label
            
            # 将token IDs转换为文本
            input_ids = inputs["input_ids"][0].cpu().numpy()
            tokens = self.ner_tokenizer.convert_ids_to_tokens(input_ids)
            labels = predictions[0].cpu().numpy()
            
            # BIO标注解析
            current_entity = None
            current_label_type = None
            current_start = None
            
            for i, (token, label_id) in enumerate(zip(tokens, labels)):
                if token in ["[CLS]", "[SEP]", "[PAD]"]:
                    if current_entity:
                        # 保存当前实体
                        entity_text = self.ner_tokenizer.convert_tokens_to_string(
                            tokens[current_start:i]
                        ).replace(" ", "")
                        entities.append({
                            "text": entity_text,
                            "label": current_label_type,
                            "start": current_start,
                            "end": i
                        })
                        current_entity = None
                    continue
                
                # 获取标签名
                label_name = id2label.get(label_id, "O")
                
                if label_name.startswith("B-"):
                    # 开始新实体
                    if current_entity:
                        # 保存之前的实体
                        entity_text = self.ner_tokenizer.convert_tokens_to_string(
                            tokens[current_start:i]
                        ).replace(" ", "")
                        entities.append({
                            "text": entity_text,
                            "label": current_label_type,
                            "start": current_start,
                            "end": i
                        })
                    current_label_type = label_name[2:]  # 去掉"B-"前缀
                    current_start = i
                    current_entity = True
                elif label_name.startswith("I-") and current_entity:
                    # 继续当前实体
                    label_type = label_name[2:]
                    if label_type == current_label_type:
                        # 继续同一个实体
                        continue
                    else:
                        # 实体类型改变，结束当前实体
                        entity_text = self.ner_tokenizer.convert_tokens_to_string(
                            tokens[current_start:i]
                        ).replace(" ", "")
                        entities.append({
                            "text": entity_text,
                            "label": current_label_type,
                            "start": current_start,
                            "end": i
                        })
                        current_label_type = label_type
                        current_start = i
                else:
                    # O标签或其他，结束当前实体
                    if current_entity:
                        entity_text = self.ner_tokenizer.convert_tokens_to_string(
                            tokens[current_start:i]
                        ).replace(" ", "")
                        entities.append({
                            "text": entity_text,
                            "label": current_label_type,
                            "start": current_start,
                            "end": i
                        })
                        current_entity = None
            
            # 处理最后一个实体
            if current_entity:
                entity_text = self.ner_tokenizer.convert_tokens_to_string(
                    tokens[current_start:]
                ).replace(" ", "")
                entities.append({
                    "text": entity_text,
                    "label": current_label_type,
                    "start": current_start,
                    "end": len(tokens)
                })
            
            return entities
            
        except Exception as e:
            logger.error(f"NER实体提取失败: {str(e)}", exc_info=True)
            return []
    
    def extract_relations(
        self, 
        text: str, 
        entities: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, str]]:
        """使用RE模型提取关系（三元组）"""
        if not entities:
            return []
        
        # 如果RE模型未加载，使用基于规则的简单关系抽取
        if not self._models_loaded or not self.re_model:
            logger.debug("RE模型未加载，使用基于规则的简单关系抽取")
            return self._extract_relations_rule_based(text, entities)
        
        try:
            # TODO: 实现完整的CasRel关系抽取
            # 目前先使用规则方法作为fallback
            return self._extract_relations_rule_based(text, entities)
            
        except Exception as e:
            logger.error(f"RE关系提取失败: {str(e)}", exc_info=True)
            return self._extract_relations_rule_based(text, entities)
    
    def _extract_relations_rule_based(
        self, 
        text: str, 
        entities: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, str]]:
        """
        基于规则的简单关系抽取（结合NER实体）
        
        注意：这个方法主要用于RE模型不可用时的fallback。
        推荐使用 KnowledgeGraphService._extract_triples_ner_rule_hybrid 方法，
        它提供了更完善的关系提取逻辑。
        """
        import re
        triples = []
        
        # 提取实体文本和位置信息
        entity_texts = set()
        entity_positions = {}  # 实体文本 -> 位置列表
        for e in entities:
            entity_text = e.get("text", "").strip()
            if entity_text and len(entity_text) >= 2:
                entity_texts.add(entity_text)
                if entity_text not in entity_positions:
                    entity_positions[entity_text] = []
                # 查找实体在文本中的所有出现位置
                start = 0
                while True:
                    pos = text.find(entity_text, start)
                    if pos == -1:
                        break
                    entity_positions[entity_text].append((pos, pos + len(entity_text)))
                    start = pos + 1
        
        if not entity_texts:
            return []
        
        # 按句子切分
        sentences = re.split(r"[。！？\n]", text)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 6]
        
        # 常见关系模式（扩展版）
        patterns = [
            (r"(.+?)(是|为|成为)(.+)", "是"),
            (r"(.+?)(位于|在|处于)(.+)", "位于"),
            (r"(.+?)(属于|归属)(.+)", "属于"),
            (r"(.+?)(使用|采用|利用)(.+)", "使用"),
            (r"(.+?)(包含|包括)(.+)", "包含"),
            (r"(.+?)(创建|建立|开发)(.+)", "创建"),
            (r"(.+?)(工作于|就职于)(.+)", "工作于"),
            (r"(.+?)(和|与|同)(.+?)(结义|结拜)", "结义"),
            (r"(.+?)(说|道|曰)(.+)", "说"),
            (r"(.+?)(去|到|前往)(.+)", "前往"),
            (r"(.+?)(来自|出自)(.+)", "来自"),
        ]
        
        for sent in sentences:
            # 检查句子中是否包含至少2个实体
            sent_entities = [e for e in entity_texts if e in sent]
            if len(sent_entities) < 2:
                continue
            
            for pattern, rel in patterns:
                matches = re.finditer(pattern, sent)
                for match in matches:
                    groups = match.groups()
                    if len(groups) < 2:
                        continue
                    
                    # 提取subject和object
                    if rel == "结义" and len(groups) >= 4:
                        subj_text = groups[0].strip()
                        obj_text = groups[2].strip()
                    elif len(groups) >= 3:
                        subj_text = groups[0].strip()
                        obj_text = groups[-1].strip()
                    else:
                        continue
                    
                    # 验证是否匹配到实体
                    subj_entity = None
                    obj_entity = None
                    
                    # 精确匹配实体
                    if subj_text in entity_texts:
                        subj_entity = subj_text
                    else:
                        # 部分匹配：查找包含在subj_text中的实体
                        for entity_text in entity_texts:
                            if entity_text in subj_text and len(entity_text) >= 2:
                                subj_entity = entity_text
                                break
                    
                    if obj_text in entity_texts:
                        obj_entity = obj_text
                    else:
                        # 部分匹配：查找包含在obj_text中的实体
                        for entity_text in entity_texts:
                            if entity_text in obj_text and len(entity_text) >= 2:
                                obj_entity = entity_text
                                break
                    
                    # 至少有一个是实体才保留
                    if subj_entity or obj_entity:
                        final_subj = subj_entity if subj_entity else subj_text
                        final_obj = obj_entity if obj_entity else obj_text
                        
                        # 验证长度
                        if (final_subj and final_obj and 
                            len(final_subj) < 100 and len(final_obj) < 100 and
                            len(final_subj) >= 2 and len(final_obj) >= 2):
                            triples.append((final_subj, rel, final_obj))
        
        # 去重
        seen = set()
        unique_triples = []
        for triple in triples:
            if triple not in seen:
                seen.add(triple)
                unique_triples.append(triple)
        
        return unique_triples
    
    def extract_triples(self, text: str) -> List[Tuple[str, str, str, float]]:
        """
        完整的实体-关系抽取流程
        返回: List[(subject, predicate, object, confidence)]
        """
        if not self._models_loaded:
            logger.warning("IE模型未加载，无法提取三元组")
            return []
        
        try:
            # 1. 提取实体
            entities = self.extract_entities(text)
            if not entities:
                return []
            
            # 2. 提取关系
            triples = self.extract_relations(text, entities)
            
            # 3. 转换为标准格式（添加置信度）
            result = []
            for triple in triples:
                if len(triple) >= 3:
                    confidence = triple[3] if len(triple) > 3 else 0.8
                    result.append((triple[0], triple[1], triple[2], confidence))
            
            return result
            
        except Exception as e:
            logger.error(f"三元组提取失败: {str(e)}", exc_info=True)
            return []
    
    def is_available(self) -> bool:
        """检查模型是否可用"""
        return self._models_loaded and self.ner_model is not None


# 全局单例
_ie_model_service: Optional[IEModelService] = None


def get_ie_model_service() -> IEModelService:
    """获取全局IE模型服务"""
    global _ie_model_service
    if _ie_model_service is None:
        _ie_model_service = IEModelService()
    return _ie_model_service
