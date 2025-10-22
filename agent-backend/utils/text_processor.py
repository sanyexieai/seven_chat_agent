import re
import os
from typing import List, Dict, Any, Optional
from utils.log_helper import get_logger

logger = get_logger("text_processor")

class TextProcessor:
    """文本处理工具类"""
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 200, 
                 chunk_strategy: str = "semantic", min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunk_strategy = chunk_strategy  # semantic, sentence, fixed
        self.min_chunk_size = min_chunk_size
        self.semantic_splitter = None
        
        # 初始化语义分割器（如果可用）
        if chunk_strategy == "semantic":
            self._initialize_semantic_splitter()
    
    def split_text(self, text: str) -> List[str]:
        """将文本分割成块"""
        if not text:
            return []
        
        # 清理文本
        text = self._clean_text(text)
        
        # 优先尝试按段落分割
        paragraphs = self.split_by_paragraphs(text)
        if len(paragraphs) > 1:
            # 如果段落分割成功，对每个段落进一步处理
            chunks = []
            for para in paragraphs:
                if len(para) <= self.chunk_size:
                    chunks.append(para)
                else:
                    # 段落太长，进一步分割
                    if self.chunk_strategy == "semantic" and self.semantic_splitter:
                        chunks.extend(self._semantic_split(para))
                    else:
                        chunks.extend(self._sentence_split(para))
            return chunks
        
        # 如果没有段落分割，使用原有策略
        if self.chunk_strategy == "semantic" and self.semantic_splitter:
            return self._semantic_split(text)
        elif self.chunk_strategy == "sentence":
            return self._sentence_split(text)
        else:
            return self._fixed_split(text)
    
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
            if para and len(para) >= self.min_chunk_size:
                filtered_paragraphs.append(para)
        
        return filtered_paragraphs 