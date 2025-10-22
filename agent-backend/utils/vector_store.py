import os
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from utils.log_helper import get_logger

logger = get_logger("vector_store")

class VectorStore:
    """向量存储基类"""
    
    def __init__(self, embedding_dim: int = 384):
        self.embedding_dim = embedding_dim
        self.index = None
        self.metadata = {}
    
    def add_vectors(self, vectors: List[List[float]], metadata: List[Dict[str, Any]]) -> bool:
        """添加向量到存储"""
        raise NotImplementedError
    
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        raise NotImplementedError
    
    def save(self, path: str) -> bool:
        """保存向量存储"""
        raise NotImplementedError
    
    def load(self, path: str) -> bool:
        """加载向量存储"""
        raise NotImplementedError
    
    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        return {
            "embedding_dim": self.embedding_dim,
            "total_vectors": len(self.metadata) if self.metadata else 0,
            "store_type": self.__class__.__name__
        }

class FAISSVectorStore(VectorStore):
    """基于FAISS的向量存储"""
    
    def __init__(self, embedding_dim: int = 384, index_type: str = "flat"):
        super().__init__(embedding_dim)
        self.index_type = index_type
        self.index = None
        self._initialize_index()
    
    def _initialize_index(self):
        """初始化FAISS索引"""
        try:
            import faiss
            
            if self.index_type == "flat":
                # 使用L2距离的平面索引
                self.index = faiss.IndexFlatL2(self.embedding_dim)
            elif self.index_type == "ivf":
                # 使用IVF索引（适合大规模数据）
                quantizer = faiss.IndexFlatL2(self.embedding_dim)
                self.index = faiss.IndexIVFFlat(quantizer, self.embedding_dim, 100)
            elif self.index_type == "hnsw":
                # 使用HNSW索引（适合快速搜索）
                self.index = faiss.IndexHNSWFlat(self.embedding_dim, 32)
            else:
                # 默认使用平面索引
                self.index = faiss.IndexFlatL2(self.embedding_dim)
            
            logger.info(f"FAISS索引初始化成功: {self.index_type}")
            
        except ImportError:
            logger.error("FAISS未安装，请安装: pip install faiss-cpu")
            self.index = None
        except Exception as e:
            logger.error(f"初始化FAISS索引失败: {str(e)}")
            self.index = None
    
    def add_vectors(self, vectors: List[List[float]], metadata: List[Dict[str, Any]]) -> bool:
        """添加向量到FAISS索引"""
        if not self.index:
            logger.error("FAISS索引未初始化")
            return False
        
        try:
            # 转换为numpy数组
            vectors_array = np.array(vectors).astype('float32')
            
            # 添加到索引
            self.index.add(vectors_array)
            
            # 保存元数据
            for i, meta in enumerate(metadata):
                self.metadata[len(self.metadata)] = meta
            
            logger.info(f"成功添加 {len(vectors)} 个向量到FAISS索引")
            return True
            
        except Exception as e:
            logger.error(f"添加向量到FAISS失败: {str(e)}")
            return False
    
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        if not self.index:
            logger.error("FAISS索引未初始化")
            return []
        
        try:
            # 转换为numpy数组
            query_array = np.array([query_vector]).astype('float32')
            
            # 搜索
            distances, indices = self.index.search(query_array, top_k)
            
            # 构建结果
            results = []
            for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
                if idx in self.metadata:
                    result = self.metadata[idx].copy()
                    result['similarity'] = 1.0 / (1.0 + distance)  # 转换为相似度
                    result['distance'] = float(distance)
                    result['rank'] = i + 1
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"FAISS搜索失败: {str(e)}")
            return []
    
    def save(self, path: str) -> bool:
        """保存FAISS索引"""
        if not self.index:
            logger.error("FAISS索引未初始化")
            return False
        
        try:
            import faiss
            
            # 保存索引
            faiss.write_index(self.index, f"{path}.index")
            
            # 保存元数据
            with open(f"{path}.metadata", 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"FAISS索引已保存到: {path}")
            return True
            
        except Exception as e:
            logger.error(f"保存FAISS索引失败: {str(e)}")
            return False
    
    def load(self, path: str) -> bool:
        """加载FAISS索引"""
        try:
            import faiss
            
            # 加载索引
            if os.path.exists(f"{path}.index"):
                self.index = faiss.read_index(f"{path}.index")
            else:
                logger.error(f"索引文件不存在: {path}.index")
                return False
            
            # 加载元数据
            if os.path.exists(f"{path}.metadata"):
                with open(f"{path}.metadata", 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
            else:
                logger.error(f"元数据文件不存在: {path}.metadata")
                return False
            
            logger.info(f"FAISS索引已加载: {path}")
            return True
            
        except Exception as e:
            logger.error(f"加载FAISS索引失败: {str(e)}")
            return False

class ChromaVectorStore(VectorStore):
    """基于Chroma的向量存储"""
    
    def __init__(self, embedding_dim: int = 384, collection_name: str = "default"):
        super().__init__(embedding_dim)
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化Chroma客户端"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # 创建客户端
            self.client = chromadb.Client(Settings(
                persist_directory="./chroma_db",
                anonymized_telemetry=False
            ))
            
            # 获取或创建集合
            try:
                self.collection = self.client.get_collection(self.collection_name)
            except:
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            
            logger.info(f"Chroma客户端初始化成功: {self.collection_name}")
            
        except ImportError:
            logger.error("ChromaDB未安装，请安装: pip install chromadb")
            self.client = None
        except Exception as e:
            logger.error(f"初始化Chroma客户端失败: {str(e)}")
            self.client = None
    
    def add_vectors(self, vectors: List[List[float]], metadata: List[Dict[str, Any]]) -> bool:
        """添加向量到Chroma集合"""
        if not self.collection:
            logger.error("Chroma集合未初始化")
            return False
        
        try:
            # 准备数据
            ids = [str(i) for i in range(len(vectors))]
            documents = [meta.get('content', '') for meta in metadata]
            
            # 添加到集合
            self.collection.add(
                embeddings=vectors,
                documents=documents,
                metadatas=metadata,
                ids=ids
            )
            
            logger.info(f"成功添加 {len(vectors)} 个向量到Chroma集合")
            return True
            
        except Exception as e:
            logger.error(f"添加向量到Chroma失败: {str(e)}")
            return False
    
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        if not self.collection:
            logger.error("Chroma集合未初始化")
            return []
        
        try:
            # 搜索
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k
            )
            
            # 构建结果
            search_results = []
            if results['documents'] and results['documents'][0]:
                for i, (doc, meta, dist) in enumerate(zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    result = meta.copy()
                    result['content'] = doc
                    result['similarity'] = 1.0 - dist  # Chroma使用余弦距离
                    result['distance'] = float(dist)
                    result['rank'] = i + 1
                    search_results.append(result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Chroma搜索失败: {str(e)}")
            return []
    
    def save(self, path: str) -> bool:
        """保存Chroma集合"""
        if not self.client:
            logger.error("Chroma客户端未初始化")
            return False
        
        try:
            # Chroma会自动持久化到磁盘
            logger.info(f"Chroma集合已保存到: {path}")
            return True
            
        except Exception as e:
            logger.error(f"保存Chroma集合失败: {str(e)}")
            return False
    
    def load(self, path: str) -> bool:
        """加载Chroma集合"""
        try:
            # Chroma会自动从磁盘加载
            logger.info(f"Chroma集合已加载: {path}")
            return True
            
        except Exception as e:
            logger.error(f"加载Chroma集合失败: {str(e)}")
            return False

class SimpleVectorStore(VectorStore):
    """简单的内存向量存储（回退方案）"""
    
    def __init__(self, embedding_dim: int = 384):
        super().__init__(embedding_dim)
        self.vectors = []
        self.metadata = {}
    
    def add_vectors(self, vectors: List[List[float]], metadata: List[Dict[str, Any]]) -> bool:
        """添加向量到内存存储"""
        try:
            for i, (vector, meta) in enumerate(zip(vectors, metadata)):
                self.vectors.append(vector)
                self.metadata[len(self.vectors) - 1] = meta
            
            logger.info(f"成功添加 {len(vectors)} 个向量到内存存储")
            return True
            
        except Exception as e:
            logger.error(f"添加向量到内存存储失败: {str(e)}")
            return False
    
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """搜索相似向量"""
        if not self.vectors:
            return []
        
        try:
            # 对齐查询向量维度，避免历史数据与当前模型维度不一致导致报错
            target_dim = len(self.vectors[0])
            if len(query_vector) != target_dim:
                if len(query_vector) > target_dim:
                    query_vector = query_vector[:target_dim]
                else:
                    # 使用0填充到目标维度
                    query_vector = query_vector + [0.0] * (target_dim - len(query_vector))
            # 数值清洗
            query_vector = self._sanitize_vector(query_vector, target_dim)
            
            # 计算相似度
            similarities = []
            for i, vector in enumerate(self.vectors):
                # 防御性：矫正存量向量维度
                if len(vector) != target_dim:
                    if len(vector) > target_dim:
                        vector = vector[:target_dim]
                    else:
                        vector = vector + [0.0] * (target_dim - len(vector))
                vector = self._sanitize_vector(vector, target_dim)
                similarity = self._cosine_similarity(query_vector, vector)
                similarities.append((similarity, i))
            
            # 排序并返回top_k
            similarities.sort(key=lambda x: x[0], reverse=True)
            
            results = []
            for similarity, idx in similarities[:top_k]:
                result = self.metadata[idx].copy()
                result['similarity'] = similarity
                result['rank'] = len(results) + 1
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"内存搜索失败: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        try:
            vec1_np = np.asarray(vec1, dtype=np.float32)
            vec2_np = np.asarray(vec2, dtype=np.float32)
            
            dot_product = np.dot(vec1_np, vec2_np)
            norm1 = np.linalg.norm(vec1_np)
            norm2 = np.linalg.norm(vec2_np)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
            
        except Exception as e:
            logger.error(f"计算余弦相似度失败: {str(e)} | v1_type={type(vec1)}, v2_type={type(vec2)}")
            return 0.0

    def _sanitize_vector(self, vec: List[Any], target_dim: int) -> List[float]:
        """将向量元素强制转换为float，替换非法/NaN为0，并保证长度一致。"""
        clean: List[float] = []
        for i in range(min(len(vec), target_dim)):
            val = vec[i]
            try:
                f = float(val)
                if not np.isfinite(f):
                    f = 0.0
                clean.append(f)
            except Exception:
                clean.append(0.0)
        if len(clean) < target_dim:
            clean += [0.0] * (target_dim - len(clean))
        elif len(clean) > target_dim:
            clean = clean[:target_dim]
        return clean
    
    def save(self, path: str) -> bool:
        """保存内存存储"""
        try:
            data = {
                'vectors': self.vectors,
                'metadata': self.metadata,
                'embedding_dim': self.embedding_dim
            }
            
            with open(f"{path}.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"内存存储已保存到: {path}.json")
            return True
            
        except Exception as e:
            logger.error(f"保存内存存储失败: {str(e)}")
            return False
    
    def load(self, path: str) -> bool:
        """加载内存存储"""
        try:
            with open(f"{path}.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.vectors = data['vectors']
            self.metadata = data['metadata']
            self.embedding_dim = data['embedding_dim']
            
            logger.info(f"内存存储已加载: {path}.json")
            return True
            
        except Exception as e:
            logger.error(f"加载内存存储失败: {str(e)}")
            return False

def create_vector_store(store_type: str = "auto", embedding_dim: int = 384, **kwargs) -> VectorStore:
    """创建向量存储实例"""
    
    if store_type == "auto":
        # 自动选择最佳存储类型
        try:
            import faiss
            return FAISSVectorStore(embedding_dim, **kwargs)
        except ImportError:
            try:
                import chromadb
                return ChromaVectorStore(embedding_dim, **kwargs)
            except ImportError:
                logger.warning("未找到FAISS或ChromaDB，使用简单内存存储")
                return SimpleVectorStore(embedding_dim)
    
    elif store_type == "faiss":
        return FAISSVectorStore(embedding_dim, **kwargs)
    elif store_type == "chroma":
        return ChromaVectorStore(embedding_dim, **kwargs)
    elif store_type == "simple":
        return SimpleVectorStore(embedding_dim)
    else:
        logger.warning(f"未知的存储类型: {store_type}，使用简单内存存储")
        return SimpleVectorStore(embedding_dim)
