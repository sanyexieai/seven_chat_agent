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
        
        # 检查torch是否可用
        try:
            import torch
            self.device = "cuda" if (USE_GPU and torch.cuda.is_available()) else "cpu"
            logger.info(f"使用设备: {self.device}")
        except ImportError:
            logger.warning("torch未安装，将使用CPU模式")
            self.device = "cpu"
        
        self._models_loaded = False
        
        if IE_MODEL_ENABLED:
            try:
                self._load_models()
            except Exception as e:
                # 即使加载失败也不抛出异常，允许系统继续运行
                logger.error(f"IE模型服务初始化失败: {str(e)}", exc_info=True)
                logger.warning("系统将使用规则模式进行实体识别")
                self._models_loaded = False
                self.ner_model = None
                self.ner_tokenizer = None
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
                logger.info(f"正在从HuggingFace下载/加载NER模型: {ner_model_name}...")
                logger.info(f"设备: {self.device}")
                
                # 分步加载，便于定位问题
                try:
                    logger.info("步骤1: 加载Tokenizer...")
                    self.ner_tokenizer = AutoTokenizer.from_pretrained(ner_model_name)
                    logger.info("✓ Tokenizer加载成功")
                except Exception as e:
                    logger.error(f"✗ Tokenizer加载失败: {str(e)}")
                    raise
                
                try:
                    logger.info("步骤2: 加载模型权重...")
                    # 优先尝试使用safetensors格式加载（避免torch版本问题）
                    # 如果模型没有safetensors格式，会自动回退到普通格式
                    try:
                        logger.info("尝试使用safetensors格式加载（推荐，避免torch版本限制）...")
                        self.ner_model = AutoModelForTokenClassification.from_pretrained(
                            ner_model_name,
                            use_safetensors=True,
                            local_files_only=False  # 允许从网络下载
                        )
                        logger.info("✓ 模型权重加载成功（使用safetensors格式）")
                    except (ValueError, OSError) as safetensors_error:
                        error_msg = str(safetensors_error)
                        # 检查是否是torch版本问题
                        if "torch.load" in error_msg and ("v2.6" in error_msg or "CVE-2025-32434" in error_msg):
                            logger.warning("检测到torch版本限制，尝试强制使用safetensors...")
                            # 强制使用safetensors，如果模型不支持则报错
                            try:
                                self.ner_model = AutoModelForTokenClassification.from_pretrained(
                                    ner_model_name,
                                    use_safetensors=True,
                                    local_files_only=False
                                )
                                logger.info("✓ 模型权重加载成功（强制safetensors格式）")
                            except Exception as e2:
                                logger.error("✗ 模型权重加载失败: torch版本过低且模型不支持safetensors")
                                logger.error(f"错误信息: {str(e2)[:500]}")
                                logger.error("解决方案：")
                                logger.error("1. 升级torch到v2.6或更高版本:")
                                logger.error("   pip install --upgrade torch>=2.6")
                                logger.error("   或使用conda: conda install pytorch>=2.6 -c pytorch")
                                logger.error("2. 如果网络问题，可以设置镜像源:")
                                logger.error("   pip install --upgrade torch>=2.6 -i https://pypi.tuna.tsinghua.edu.cn/simple")
                                raise ValueError(f"torch版本过低，需要>=2.6。当前版本可能不支持加载此模型。错误: {str(e2)[:200]}")
                        else:
                            # 其他错误，尝试普通格式
                            logger.warning(f"safetensors加载失败: {error_msg[:200]}，尝试普通格式...")
                            try:
                                self.ner_model = AutoModelForTokenClassification.from_pretrained(
                                    ner_model_name,
                                    use_safetensors=False
                                )
                                logger.info("✓ 模型权重加载成功（使用普通格式）")
                            except ValueError as e3:
                                error_msg3 = str(e3)
                                if "torch.load" in error_msg3 and ("v2.6" in error_msg3 or "CVE-2025-32434" in error_msg3):
                                    logger.error("✗ 模型权重加载失败: torch版本过低")
                                    logger.error("错误信息: " + error_msg3[:500])
                                    logger.error("解决方案：")
                                    logger.error("1. 升级torch到v2.6或更高版本:")
                                    logger.error("   pip install --upgrade torch>=2.6")
                                    logger.error("   或使用conda: conda install pytorch>=2.6 -c pytorch")
                                    logger.error("2. 如果网络问题，可以设置镜像源:")
                                    logger.error("   pip install --upgrade torch>=2.6 -i https://pypi.tuna.tsinghua.edu.cn/simple")
                                    raise ValueError(f"torch版本过低，需要>=2.6。请升级torch后重试。错误: {str(e3)[:200]}")
                                else:
                                    raise
                except Exception as e:
                    logger.error(f"✗ 模型权重加载失败: {str(e)[:500]}")
                    raise
                
                try:
                    logger.info(f"步骤3: 移动模型到设备 {self.device}...")
                    self.ner_model.to(self.device)
                    self.ner_model.eval()
                    logger.info(f"✓ 模型已移动到设备: {self.device}")
                except Exception as e:
                    logger.warning(f"模型移动到设备 {self.device} 失败: {str(e)}，尝试使用CPU")
                    try:
                        self.device = "cpu"
                        self.ner_model.to(self.device)
                        self.ner_model.eval()
                        logger.info(f"✓ 模型已移动到CPU")
                    except Exception as e2:
                        logger.error(f"模型移动到CPU也失败: {str(e2)}")
                        raise
                
                logger.info(f"NER模型加载成功: {ner_model_name} (设备: {self.device})")
            except ImportError as e:
                logger.error(f"导入transformers库失败: {str(e)}")
                logger.error("请安装transformers库: pip install transformers")
                self.ner_model = None
                self.ner_tokenizer = None
                self._models_loaded = False
                return  # 不抛出异常，允许系统继续运行（使用规则模式）
            except Exception as e:
                error_msg = str(e)
                logger.error(f"加载NER模型失败: {error_msg}")
                
                # 检查是否是网络问题
                if "Connection" in error_msg or "timeout" in error_msg.lower() or "network" in error_msg.lower():
                    logger.error("可能是网络问题，无法从HuggingFace下载模型")
                    logger.error("解决方案：")
                    logger.error("1. 检查网络连接")
                    logger.error("2. 或手动下载模型到本地，然后设置环境变量 HF_HOME 或 TRANSFORMERS_CACHE")
                elif "not found" in error_msg.lower() or "does not exist" in error_msg.lower():
                    logger.error("模型在HuggingFace上不存在或无法访问")
                    logger.error("解决方案：检查模型名称是否正确，或使用其他模型")
                else:
                    logger.error("请确保已安装 transformers 库，并已下载模型权重")
                
                # 不抛出异常，允许系统继续运行（使用规则模式）
                self.ner_model = None
                self.ner_tokenizer = None
                self._models_loaded = False
                logger.warning("NER模型加载失败，系统将使用规则模式进行实体识别")
                return
            
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
            
            # 只有NER模型加载成功才标记为已加载
            if self.ner_model is not None:
                self._models_loaded = True
                logger.info("信息抽取模型加载完成（NER模型可用）")
            else:
                self._models_loaded = False
                logger.warning("信息抽取模型加载完成（但NER模型不可用，将使用规则模式）")
            
        except Exception as e:
            # 如果NER模型加载失败，不应该抛出异常，而是优雅降级
            logger.error(f"加载信息抽取模型时发生未预期的错误: {str(e)}", exc_info=True)
            self._models_loaded = False
            # 确保模型对象为None
            if self.ner_model is None:
                self.ner_tokenizer = None
            # 不抛出异常，允许系统继续运行（使用规则模式）
            logger.warning("模型加载失败，系统将使用规则模式进行实体识别")
    
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
                    tokens[current_start:len(tokens)]
                ).replace(" ", "")
                entities.append({
                    "text": entity_text,
                    "label": current_label_type,
                    "start": current_start,
                    "end": len(tokens)
                })
            
            # 后处理：识别事件实体（规则增强）
            event_entities = self._extract_event_entities(text, entities)
            entities.extend(event_entities)
            
            logger.debug(f"NER识别到 {len(entities)} 个实体（包含 {len(event_entities)} 个事件实体）")
            
            return entities
            
        except Exception as e:
            logger.error(f"提取实体失败: {str(e)}", exc_info=True)
            return []
    
    def _extract_event_entities(self, text: str, existing_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用规则识别事件实体（补充NER模型）
        
        识别模式：
        - "在X地Y" -> 事件："X地Y"（如"桃园结义"）
        - "X、Y、Z在W地Y" -> 事件："W地Y"
        - "X和Y在W地Y" -> 事件："W地Y"
        """
        import re
        event_entities = []
        
        # 提取已识别的人名和地名（用于验证）
        person_names = {e["text"] for e in existing_entities if e.get("label") == "person"}
        location_names = {e["text"] for e in existing_entities if e.get("label") == "location"}
        
        # 事件模式1：X、Y、Z在W地结义/结拜
        pattern1 = r"(.+?)[、，,](.+?)[、，,](.+?)在(.+?)(结义|结拜)"
        matches1 = re.finditer(pattern1, text)
        for match in matches1:
            participants = [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
            location = match.group(4).strip()
            action = match.group(5).strip()
            event_name = f"{location}{action}"  # "桃园结义"
            
            # 验证：至少有一个参与者是人名，地点是地名
            if any(p in person_names for p in participants) or location in location_names:
                # 查找事件在文本中的位置
                event_start = match.start(4)  # 地点开始位置
                event_end = match.end(5)  # 动作结束位置
                
                event_entities.append({
                    "text": event_name,
                    "label": "EVENT",
                    "start": event_start,
                    "end": event_end,
                    "metadata": {
                        "location": location,
                        "action": action,
                        "participants": participants,
                        "event_type": "结义事件"
                    }
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
            event_name = f"{location}{action}"  # "桃园结义"
            
            # 验证：至少有一个参与者是人名，地点是地名
            if (participant1 in person_names or participant2 in person_names) or location in location_names:
                event_start = match.start(4)
                event_end = match.end(5)
                
                event_entities.append({
                    "text": event_name,
                    "label": "EVENT",
                    "start": event_start,
                    "end": event_end,
                    "metadata": {
                        "location": location,
                        "action": action,
                        "participants": [participant1, participant2],
                        "event_type": "结义事件"
                    }
                })
                logger.debug(f"识别到事件实体: {event_name} (地点: {location}, 参与者: [{participant1}, {participant2}])")
        
        # 事件模式3：在W地结义/结拜（参与者在前文，需要上下文分析）
        pattern3 = r"在(.+?)(结义|结拜)"
        matches3 = re.finditer(pattern3, text)
        for match in matches3:
            location = match.group(1).strip()
            action = match.group(2).strip()
            event_name = f"{location}{action}"
            
            # 查找前文中的参与者（在事件前50个字符内）
            context_start = max(0, match.start() - 50)
            context_text = text[context_start:match.start()]
            
            # 在前文中查找人名
            participants = []
            for person in person_names:
                if person in context_text:
                    participants.append(person)
            
            # 如果找到参与者或地点是地名，则识别为事件
            if participants or location in location_names:
                event_start = match.start(1)
                event_end = match.end(2)
                
                event_entities.append({
                    "text": event_name,
                    "label": "EVENT",
                    "start": event_start,
                    "end": event_end,
                    "metadata": {
                        "location": location,
                        "action": action,
                        "participants": participants,
                        "event_type": "结义事件"
                    }
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
    """获取全局IE模型服务（单例模式，但允许重新初始化）"""
    global _ie_model_service
    if _ie_model_service is None:
        logger.info("创建新的IE模型服务实例...")
        _ie_model_service = IEModelService()
    # 如果模型未加载且启用，尝试重新初始化（可能是之前的加载失败了）
    elif not _ie_model_service.is_available() and IE_MODEL_ENABLED:
        logger.info("检测到IE模型服务未加载，尝试重新初始化...")
        try:
            _ie_model_service = IEModelService()
        except Exception as e:
            logger.warning(f"重新初始化IE模型服务失败: {str(e)}")
    return _ie_model_service
