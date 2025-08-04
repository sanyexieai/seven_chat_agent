import numpy as np
import json
from typing import List, Dict, Any
from utils.log_helper import get_logger

logger = get_logger("embedding_service")

class EmbeddingService:
    """向量嵌入服务"""
    
    def __init__(self, embedding_dim: int = 384):
        self.embedding_dim = embedding_dim
        # 这里可以集成真实的嵌入模型，如sentence-transformers
        # 暂时使用简单的TF-IDF向量化
    
    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        try:
            # 简单的TF-IDF向量化（简化版）
            # 在实际应用中，应该使用专业的嵌入模型如sentence-transformers
            embedding = self._simple_embedding(text)
            return embedding
        except Exception as e:
            logger.error(f"生成嵌入失败: {str(e)}")
            # 返回零向量作为fallback
            return [0.0] * self.embedding_dim
    
    def calculate_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """计算两个嵌入向量的相似度"""
        try:
            # 转换为numpy数组
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # 计算余弦相似度
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"计算相似度失败: {str(e)}")
            return 0.0
    
    def batch_get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入"""
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text)
            embeddings.append(embedding)
        return embeddings
    
    def _simple_embedding(self, text: str) -> List[float]:
        """简单的文本嵌入实现"""
        # 这是一个简化的实现，实际应用中应该使用专业的嵌入模型
        import hashlib
        
        # 将文本转换为固定长度的向量
        # 使用哈希函数确保相同文本产生相同向量
        hash_obj = hashlib.md5(text.encode('utf-8'))
        hash_bytes = hash_obj.digest()
        
        # 将哈希值转换为浮点数向量
        embedding = []
        for i in range(self.embedding_dim):
            byte_index = i % len(hash_bytes)
            value = hash_bytes[byte_index] / 255.0  # 归一化到0-1
            embedding.append(value)
        
        return embedding
    
    def _load_embedding_model(self):
        """加载嵌入模型"""
        # 这里可以加载真实的嵌入模型
        # 例如：from sentence_transformers import SentenceTransformer
        # self.model = SentenceTransformer('all-MiniLM-L6-v2')
        pass
    
    def _get_embedding_from_model(self, text: str) -> List[float]:
        """从模型获取嵌入"""
        # 这里应该调用真实的嵌入模型
        # 例如：return self.model.encode(text).tolist()
        return self._simple_embedding(text) 