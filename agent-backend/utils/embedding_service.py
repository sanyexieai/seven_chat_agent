import numpy as np
import json
import os
from typing import List, Dict, Any, Optional
from utils.log_helper import get_logger

logger = get_logger("embedding_service")

class EmbeddingService:
    """向量嵌入服务"""
    
    def __init__(self, embedding_dim: int = 384, model_name: str = "all-MiniLM-L6-v2"):
        self.embedding_dim = embedding_dim
        self.model_name = model_name
        self.model = None
        self._initialize_model()
    
    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        try:
            if self.model:
                # 使用sentence-transformers模型
                embedding = self.model.encode(text, convert_to_tensor=False)
                return embedding.tolist()
            else:
                # 回退到简单嵌入
                logger.warning("嵌入模型未加载，使用简单嵌入")
                return self._simple_embedding(text)
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
    
    def batch_get_embeddings(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """批量获取嵌入"""
        if not texts:
            return []
        
        try:
            if self.model:
                # 使用sentence-transformers的批量处理
                embeddings = self.model.encode(texts, convert_to_tensor=False, batch_size=batch_size)
                return embeddings.tolist()
            else:
                # 回退到逐个处理
                embeddings = []
                for text in texts:
                    embedding = self.get_embedding(text)
                    embeddings.append(embedding)
                return embeddings
        except Exception as e:
            logger.error(f"批量获取嵌入失败: {str(e)}")
            # 回退到逐个处理
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
    
    def _initialize_model(self):
        """初始化嵌入模型"""
        try:
            # 尝试加载sentence-transformers模型
            from sentence_transformers import SentenceTransformer
            
            # 检查是否有本地模型缓存
            model_path = os.path.join(os.getcwd(), "models", self.model_name)
            if os.path.exists(model_path):
                logger.info(f"从本地加载模型: {model_path}")
                self.model = SentenceTransformer(model_path)
            else:
                logger.info(f"从HuggingFace下载模型: {self.model_name}")
                self.model = SentenceTransformer(self.model_name)
                
                # 保存模型到本地
                os.makedirs(os.path.dirname(model_path), exist_ok=True)
                self.model.save(model_path)
                logger.info(f"模型已保存到: {model_path}")
            
            # 更新embedding_dim为实际模型维度
            self.embedding_dim = self.model.get_sentence_embedding_dimension()
            logger.info(f"嵌入模型初始化成功: {self.model_name}, 维度: {self.embedding_dim}")
            
        except ImportError:
            logger.warning("sentence-transformers未安装，使用简单嵌入")
            self.model = None
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {str(e)}")
            self.model = None
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "model_loaded": self.model is not None,
            "model_type": "sentence-transformers" if self.model else "simple"
        } 