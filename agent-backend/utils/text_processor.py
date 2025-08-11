import re
from typing import List
from utils.log_helper import get_logger

logger = get_logger("text_processor")

class TextProcessor:
    """文本处理工具类"""
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def split_text(self, text: str) -> List[str]:
        """将文本分割成块"""
        if not text:
            return []
        
        # 清理文本
        text = self._clean_text(text)
        
        # 按句子分割
        sentences = self._split_sentences(text)
        
        # 合并句子成块
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # 如果当前块加上新句子超过大小限制
            if len(current_chunk) + len(sentence) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    # 保留重叠部分
                    overlap_text = current_chunk[-self.overlap:] if self.overlap > 0 else ""
                    current_chunk = overlap_text + sentence
                else:
                    # 单个句子就超过限制，强制分割
                    chunks.append(sentence[:self.chunk_size])
                    current_chunk = sentence[self.chunk_size:]
            else:
                current_chunk += sentence
        
        # 添加最后一个块
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊字符（保留中文、英文、数字和基本标点）
        # 修复转义序列问题，使用原始字符串
        text = re.sub(r'[^\w\s\u4e00-\u9fff.,!?;:()""''\[\]{}]', '', text)
        
        return text.strip()
    
    def _split_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 中文句子分割
        chinese_sentences = re.split(r'([。！？；：])', text)
        
        sentences = []
        current_sentence = ""
        
        for i in range(0, len(chinese_sentences), 2):
            if i + 1 < len(chinese_sentences):
                sentence = chinese_sentences[i] + chinese_sentences[i + 1]
            else:
                sentence = chinese_sentences[i]
            
            if sentence.strip():
                sentences.append(sentence.strip())
        
        # 如果没有找到中文标点，尝试英文标点
        if not sentences:
            english_sentences = re.split(r'([.!?;:])', text)
            for i in range(0, len(english_sentences), 2):
                if i + 1 < len(english_sentences):
                    sentence = english_sentences[i] + english_sentences[i + 1]
                else:
                    sentence = english_sentences[i]
                
                if sentence.strip():
                    sentences.append(sentence.strip())
        
        # 如果还是没有，按段落分割
        if not sentences:
            paragraphs = text.split('\n')
            for paragraph in paragraphs:
                if paragraph.strip():
                    sentences.append(paragraph.strip())
        
        return sentences
    
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