import re
import os
from typing import List, Dict, Any, Optional
from utils.log_helper import get_logger

logger = get_logger("text_processor")

class TextProcessor:
    """智能文本处理工具类 - 支持分层分割策略"""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 50, 
                 chunk_strategy: str = "hierarchical", min_chunk_size: int = 100,
                 max_chunk_size: int = 800, use_llm_merge: bool = False):
        self.chunk_size = chunk_size  # 目标分块大小
        self.overlap = overlap  # 重叠长度
        self.chunk_strategy = chunk_strategy  # hierarchical, semantic, sentence, fixed
        self.min_chunk_size = min_chunk_size  # 最小分块大小
        self.max_chunk_size = max_chunk_size  # 最大分块大小
        self.use_llm_merge = use_llm_merge  # 是否使用LLM合并分块
        self.semantic_splitter = None
        
        # 初始化语义分割器（如果可用）
        if chunk_strategy == "semantic":
            self._initialize_semantic_splitter()
    
    def split_text(self, text: str) -> List[str]:
        """智能分层文本分割"""
        if not text:
            return []
        
        # 清理文本
        text = self._clean_text(text)
        
        # 根据策略选择分割方法
        if self.chunk_strategy == "hierarchical":
            return self._hierarchical_split(text)
        elif self.chunk_strategy == "semantic" and self.semantic_splitter:
            return self._semantic_split(text)
        elif self.chunk_strategy == "sentence":
            return self._sentence_split(text)
        else:
            return self._fixed_split(text)
    
    def _hierarchical_split(self, text: str) -> List[str]:
        """分层分割策略：结构 -> 段落 -> 句子 -> 滑动窗口"""
        logger.info("开始分层分割处理...")
        
        # 步骤1：预处理文档，提取结构
        structure_info = self._extract_document_structure(text)
        
        if structure_info['has_structure']:
            # 步骤2：按章节分割
            logger.info("检测到文档结构，按章节分割")
            chunks = self._split_by_sections(text, structure_info['sections'])
        else:
            # 步骤5：没有结构，直接按段落分割
            logger.info("未检测到明显结构，按段落分割")
            chunks = self._split_by_paragraphs_hierarchical(text)
        
        # 后处理：合并过短的分块，分割过长的分块
        chunks = self._post_process_chunks(chunks)
        
        # 可选：使用LLM优化分块
        if self.use_llm_merge:
            chunks = self._llm_optimize_chunks(chunks)
        
        logger.info(f"分层分割完成，共生成 {len(chunks)} 个分块")
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """清理文本：保留换行以利于分段，压缩多余空格与多余空行"""
        # 统一换行符，保留单个换行
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # 压缩连续空格/制表符为单个空格，但不影响换行
        text = re.sub(r"[ \t]+", " ", text)
        # 压缩过多的空行为最多两个换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 保留常见标点与中英文，移除不可见控制字符
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text.strip()
    
    def _semantic_split(self, text: str) -> List[str]:
        """语义分割"""
        try:
            if self.semantic_splitter:
                chunks = self.semantic_splitter.split_text(text)
                # 过滤太小的块
                filtered_chunks = []
                for chunk in chunks:
                    if len(chunk.strip()) >= self.min_chunk_size:
                        filtered_chunks.append(chunk.strip())
                    elif filtered_chunks:
                        # 将小块合并到前一个块
                        filtered_chunks[-1] += " " + chunk.strip()
                
                return filtered_chunks
            else:
                # 回退到句子分割
                return self._sentence_split(text)
        except Exception as e:
            logger.error(f"语义分割失败: {str(e)}")
            return self._sentence_split(text)
    
    def _sentence_split(self, text: str) -> List[str]:
        """句子分割"""
        sentences = self._split_sentences(text)
        
        # 合并句子成块
        chunks: List[str] = []
        current_chunk = ""
        
        for sentence in sentences:
            # 如果单个句子本身就超过限制，先把已有的块提交，然后对该句子做滑窗切分
            if len(sentence) > self.chunk_size:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.extend(self._split_long_text_with_overlap(sentence))
                continue
            
            # 尝试把句子放进当前块
            if len(current_chunk) + len(sentence) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    # 保留重叠部分
                    overlap_text = current_chunk[-self.overlap:] if self.overlap > 0 else ""
                    current_chunk = overlap_text + sentence
                else:
                    chunks.append(sentence[:self.chunk_size])
                    current_chunk = sentence[self.chunk_size:]
            else:
                current_chunk += sentence
        
        # 添加最后一个块
        if current_chunk.strip():
            if len(current_chunk) > self.chunk_size:
                chunks.extend(self._split_long_text_with_overlap(current_chunk))
            else:
                chunks.append(current_chunk.strip())
        
        return chunks
    
    def _fixed_split(self, text: str) -> List[str]:
        """固定长度分割"""
        return self._split_long_text_with_overlap(text)
    
    def _initialize_semantic_splitter(self):
        """初始化语义分割器"""
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            
            self.semantic_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.overlap,
                length_function=len,
                separators=["\n\n", "\n", "。", "！", "？", "；", "：", ".", "!", "?", ";", ":", " ", ""]
            )
            logger.info("语义分割器初始化成功")
        except ImportError:
            logger.warning("langchain未安装，使用句子分割")
            self.semantic_splitter = None
        except Exception as e:
            logger.error(f"初始化语义分割器失败: {str(e)}")
            self.semantic_splitter = None
    
    def _split_sentences(self, text: str) -> List[str]:
        """按句子分割文本（优先中文标点，再英文标点，最后按换行分）"""
        sentences: List[str] = []
        
        # 先按中文标点切分，保留分隔符
        chinese_parts = re.split(r'([。！？；：])', text)
        if any(p.strip() for p in chinese_parts):
            for i in range(0, len(chinese_parts), 2):
                if i + 1 < len(chinese_parts):
                    sentence = chinese_parts[i] + chinese_parts[i + 1]
                else:
                    sentence = chinese_parts[i]
                if sentence.strip():
                    sentences.append(sentence)
        
        # 若中文未切分出结果，尝试英文标点
        if not sentences:
            english_parts = re.split(r'([.!?;:])', text)
            for i in range(0, len(english_parts), 2):
                if i + 1 < len(english_parts):
                    sentence = english_parts[i] + english_parts[i + 1]
                else:
                    sentence = english_parts[i]
                if sentence.strip():
                    sentences.append(sentence)
        
        # 若仍没有结果，则按换行分割，再退化为整段
        if not sentences:
            for paragraph in text.split('\n'):
                if paragraph.strip():
                    sentences.append(paragraph)
        
        return sentences
    
    def _split_long_text_with_overlap(self, text: str) -> List[str]:
        """对超长文本进行滑窗切分，支持重叠"""
        if self.chunk_size <= 0:
            return [text]
        step = max(1, self.chunk_size - max(0, self.overlap))
        chunks: List[str] = []
        start = 0
        length = len(text)
        while start < length:
            end = min(start + self.chunk_size, length)
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            if end == length:
                break
            start += step
        return chunks
    
    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取（基于词频）
        words = re.findall(r'\w+', text.lower())
        
        # 过滤停用词
        stop_words = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这',
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should'
        }
        
        word_freq = {}
        for word in words:
            if len(word) > 1 and word not in stop_words:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, freq in sorted_words[:max_keywords]]
    
    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（基于关键词重叠）"""
        keywords1 = set(self.extract_keywords(text1))
        keywords2 = set(self.extract_keywords(text2))
        
        if not keywords1 or not keywords2:
            return 0.0
        
        intersection = keywords1.intersection(keywords2)
        union = keywords1.union(keywords2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def get_chunk_metadata(self, chunk: str, chunk_index: int = 0) -> Dict[str, Any]:
        """获取分块的元数据"""
        return {
            "chunk_index": chunk_index,
            "chunk_size": len(chunk),
            "word_count": len(chunk.split()),
            "char_count": len(chunk),
            "has_numbers": bool(re.search(r'\d', chunk)),
            "has_urls": bool(re.search(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', chunk)),
            "language": self._detect_language(chunk)
        }
    
    def _detect_language(self, text: str) -> str:
        """简单的语言检测"""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if chinese_chars > english_chars:
            return "zh"
        elif english_chars > 0:
            return "en"
        else:
            return "unknown"
    
    def preprocess_text(self, text: str) -> str:
        """预处理文本"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符但保留标点
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()[]{}""''""''—–-]', '', text)
        
        return text.strip()
    
    def split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割"""
        paragraphs = text.split('\n\n')
        filtered_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para:  # 移除最小长度限制，让分层策略处理
                filtered_paragraphs.append(para)
        
        return filtered_paragraphs
    
    def _extract_document_structure(self, text: str) -> Dict[str, Any]:
        """提取文档结构信息"""
        structure_info = {
            'has_structure': False,
            'sections': [],
            'structure_type': 'none'
        }
        
        # 检测章节标题模式
        section_patterns = [
            r'^第[一二三四五六七八九十\d]+[章节回]',  # 第X章/节/回
            r'^\d+\.',  # 1. 标题
            r'^[一二三四五六七八九十]+、',  # 一、标题
            r'^[A-Z]\.',  # A. 标题
            r'^#{1,6}\s+',  # Markdown标题
        ]
        
        lines = text.split('\n')
        sections = []
        current_section = {'title': '', 'start_line': 0, 'end_line': 0}
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # 检查是否匹配章节模式
            for pattern in section_patterns:
                if re.match(pattern, line, re.MULTILINE):
                    if current_section['title']:
                        current_section['end_line'] = i - 1
                        sections.append(current_section)
                    
                    current_section = {
                        'title': line,
                        'start_line': i,
                        'end_line': len(lines) - 1
                    }
                    structure_info['has_structure'] = True
                    break
        
        if current_section['title']:
            sections.append(current_section)
        
        structure_info['sections'] = sections
        if structure_info['has_structure']:
            structure_info['structure_type'] = 'sections'
            logger.info(f"检测到 {len(sections)} 个章节")
        
        return structure_info
    
    def _split_by_sections(self, text: str, sections: List[Dict]) -> List[str]:
        """按章节分割文本"""
        lines = text.split('\n')
        chunks = []
        
        for i, section in enumerate(sections):
            start_line = section['start_line']
            end_line = section['end_line']
            section_text = '\n'.join(lines[start_line:end_line + 1]).strip()
            
            if not section_text:
                continue
            
            # 对每个章节按段落进一步分割
            section_chunks = self._split_by_paragraphs_hierarchical(section_text)
            chunks.extend(section_chunks)
        
        return chunks
    
    def _split_by_paragraphs_hierarchical(self, text: str) -> List[str]:
        """按段落分割（分层策略）"""
        paragraphs = self.split_by_paragraphs(text)
        chunks = []
        
        for para in paragraphs:
            if len(para) <= self.chunk_size:
                # 段落长度合适，直接使用
                chunks.append(para)
            elif len(para) <= self.max_chunk_size:
                # 段落稍长但可接受
                chunks.append(para)
            else:
                # 段落太长，按句子分割
                sentence_chunks = self._split_long_paragraph_by_sentences(para)
                chunks.extend(sentence_chunks)
        
        return chunks
    
    def _split_long_paragraph_by_sentences(self, paragraph: str) -> List[str]:
        """将长段落按句子分割并合并到合适长度"""
        sentences = self._split_sentences(paragraph)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # 如果添加这个句子会超过最大长度
            if len(current_chunk) + len(sentence) > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    # 保留重叠部分
                    overlap_text = current_chunk[-self.overlap:] if self.overlap > 0 else ""
                    current_chunk = overlap_text + sentence
                else:
                    # 单个句子就太长，强制分割
                    chunks.append(sentence[:self.max_chunk_size])
                    current_chunk = sentence[self.max_chunk_size:]
            else:
                current_chunk += sentence
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _post_process_chunks(self, chunks: List[str]) -> List[str]:
        """后处理分块：合并过短的分块，分割过长的分块"""
        processed_chunks = []
        i = 0
        
        while i < len(chunks):
            chunk = chunks[i]
            
            # 如果分块太短，尝试与下一个合并
            if len(chunk) < self.min_chunk_size and i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                merged = chunk + " " + next_chunk
                
                if len(merged) <= self.max_chunk_size:
                    processed_chunks.append(merged)
                    i += 2  # 跳过下一个分块
                    continue
            
            # 如果分块太长，使用滑动窗口分割
            if len(chunk) > self.max_chunk_size:
                logger.info(f"分块过长({len(chunk)}字符)，使用滑动窗口分割")
                window_chunks = self._sliding_window_split(chunk)
                processed_chunks.extend(window_chunks)
            else:
                processed_chunks.append(chunk)
            
            i += 1
        
        return processed_chunks
    
    def _sliding_window_split(self, text: str) -> List[str]:
        """滑动窗口分割长文本"""
        if len(text) <= self.max_chunk_size:
            return [text]
        
        chunks = []
        start = 0
        step = self.chunk_size - self.overlap
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            if end == len(text):
                break
            
            start += step
        
        return chunks
    
    def _llm_optimize_chunks(self, chunks: List[str]) -> List[str]:
        """使用LLM优化分块"""
        if not self.use_llm_merge:
            return chunks
        
        try:
            logger.info("开始使用LLM优化分块...")
            optimized_chunks = []
            i = 0
            
            while i < len(chunks):
                current_chunk = chunks[i]
                
                # 如果分块太短，尝试与后续分块合并
                if len(current_chunk) < self.min_chunk_size and i < len(chunks) - 1:
                    # 收集可以合并的短分块
                    merge_candidates = [current_chunk]
                    j = i + 1
                    
                    while (j < len(chunks) and 
                           len(' '.join(merge_candidates + [chunks[j]])) <= self.max_chunk_size and
                           len(chunks[j]) < self.min_chunk_size):
                        merge_candidates.append(chunks[j])
                        j += 1
                    
                    if len(merge_candidates) > 1:
                        # 使用LLM判断是否应该合并
                        merged_text = ' '.join(merge_candidates)
                        if self._should_merge_chunks(merge_candidates):
                            optimized_chunks.append(merged_text)
                            i = j
                        else:
                            # 不合并，保持原样
                            optimized_chunks.extend(merge_candidates)
                            i = j
                    else:
                        optimized_chunks.append(current_chunk)
                        i += 1
                
                # 如果分块太长，使用LLM进行智能分割
                elif len(current_chunk) > self.max_chunk_size:
                    split_chunks = self._llm_split_long_chunk(current_chunk)
                    optimized_chunks.extend(split_chunks)
                    i += 1
                
                else:
                    optimized_chunks.append(current_chunk)
                    i += 1
            
            logger.info(f"LLM优化完成: {len(chunks)} -> {len(optimized_chunks)} 个分块")
            return optimized_chunks
            
        except Exception as e:
            logger.warning(f"LLM优化分块失败: {str(e)}")
            return chunks
    
    def _should_merge_chunks(self, chunks: List[str]) -> bool:
        """使用基于规则的方法判断是否应该合并分块（不调用LLM）"""
        try:
            if len(chunks) <= 1:
                return True
            
            combined_text = ' '.join(chunks)
            combined_length = len(combined_text)
            
            # 规则1：如果合并后长度在合理范围内，倾向于合并
            if combined_length <= self.max_chunk_size:
                # 规则2：检查是否有明显的段落分隔（多个换行）
                if combined_text.count('\n\n') <= 1:
                    # 规则3：检查句子完整性（最后一个分块是否以句号结尾）
                    if chunks[-1].strip().endswith(('。', '！', '？', '.', '!', '?')):
                        return True
            
            # 规则4：如果所有分块都很短，倾向于合并
            if all(len(c) < self.min_chunk_size for c in chunks):
                return True
            
            # 规则5：检查是否有明显的主题连续性（简单关键词匹配）
            # 提取每个分块的前几个词和后几个词
            first_words = [c.split()[:3] for c in chunks if c.split()]
            last_words = [c.split()[-3:] for c in chunks if c.split()]
            
            # 如果相邻分块有共同词汇，倾向于合并
            for i in range(len(chunks) - 1):
                if first_words[i] and last_words[i]:
                    common_words = set(first_words[i+1]) & set(last_words[i])
                    if len(common_words) > 0:
                        return True
            
            return False
            
        except Exception as e:
            logger.warning(f"合并判断失败: {str(e)}")
            # 默认不合并
            return False
    
    def _llm_split_long_chunk(self, text: str) -> List[str]:
        """使用基于规则的方法分割长文本（不调用LLM）"""
        try:
            # 优先按段落分割
            chunks = self._split_by_paragraphs(text)
            
            # 如果分割后还有太长的块，继续按句子分割
            final_chunks = []
            for chunk in chunks:
                if len(chunk) <= self.max_chunk_size:
                    final_chunks.append(chunk)
                else:
                    # 按句子进一步分割
                    sentence_chunks = self._split_by_sentences(chunk)
                    final_chunks.extend(sentence_chunks)
            
            return final_chunks if final_chunks else self._sliding_window_split(text)
                
        except Exception as e:
            logger.warning(f"分割长文本失败: {str(e)}")
            # 降级：使用滑动窗口分割
            return self._sliding_window_split(text)
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割文本"""
        # 按双换行符分割
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # 如果当前块加上新段落不超过最大长度，合并
            if len(current_chunk) + len(para) + 2 <= self.max_chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 保存当前块，开始新块
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 按句号、问号、感叹号分割
        sentences = re.split(r'([。！？\n])', text)
        chunks = []
        current_chunk = ""
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else "")
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if len(current_chunk) + len(sentence) <= self.max_chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks 