import numpy as np
import json
import os
from typing import List, Dict, Any, Optional
from utils.log_helper import get_logger
from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, EMBEDDING_BASE_URL, EMBEDDING_API_KEY

logger = get_logger("embedding_service")

class EmbeddingService:
    """向量嵌入服务"""

    def __init__(self):
        self.provider = EMBEDDING_PROVIDER
        self.model_name = EMBEDDING_MODEL
        self.base_url = EMBEDDING_BASE_URL
        self.api_key = EMBEDDING_API_KEY
        self.embedding_dim = None
        self.model = None
        self._initialize_model()
    
    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量嵌入"""
        if not self.model:
            error_msg = (
                f"嵌入模型未初始化。请检查配置：\n"
                f"  - EMBEDDING_PROVIDER={self.provider}\n"
                f"  - EMBEDDING_MODEL={self.model_name}\n"
                f"  - EMBEDDING_BASE_URL={self.base_url}\n"
                f"如果使用 Ollama，请确保服务已启动且模型已下载。"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            # 兼容不同的模型接口
            if hasattr(self.model, 'embed_query'):
                embedding = self.model.embed_query(text)
            elif hasattr(self.model, 'encode'):
                embedding = self.model.encode(text).tolist()
            else:
                raise RuntimeError(f"模型对象不支持嵌入操作: {type(self.model)}")
            return embedding
        except Exception as e:
            logger.error(f"生成嵌入失败: {str(e)}")
            raise
    
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
        if not texts:
            return []
        if not self.model:
            error_msg = (
                f"嵌入模型未初始化。请检查配置：\n"
                f"  - EMBEDDING_PROVIDER={self.provider}\n"
                f"  - EMBEDDING_MODEL={self.model_name}\n"
                f"  - EMBEDDING_BASE_URL={self.base_url}\n"
                f"如果使用 Ollama，请确保服务已启动且模型已下载。"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        try:
            # 兼容不同的模型接口
            if hasattr(self.model, 'embed_documents'):
                embeddings = self.model.embed_documents(texts)
            elif hasattr(self.model, 'encode'):
                embeddings = self.model.encode(texts).tolist()
            else:
                raise RuntimeError(f"模型对象不支持批量嵌入操作: {type(self.model)}")
            return embeddings
        except Exception as e:
            logger.error(f"批量获取嵌入失败: {str(e)}")
            raise
    
    
    def _initialize_model(self):
        """初始化嵌入模型"""
        try:
            if self.provider == "ollama":
                # 首先尝试使用 langchain_community
                try:
                    from langchain_community.embeddings import OllamaEmbeddings
                    use_langchain = True
                except ImportError:
                    logger.warning("langchain_community 不可用，将使用直接 Ollama API 调用")
                    use_langchain = False
                    import requests
                
                # 尝试不同的模型名称格式
                model_names_to_try = [
                    self.model_name,  # 原始名称
                    f"{self.model_name}:latest",  # 带 :latest 标签
                    self.model_name.replace(":latest", ""),  # 移除 :latest 标签
                ]
                # 去重
                model_names_to_try = list(dict.fromkeys(model_names_to_try))
                
                last_error = None
                for model_name_attempt in model_names_to_try:
                    try:
                        if use_langchain:
                            logger.info(f"正在尝试初始化 Ollama 嵌入模型 (langchain): {model_name_attempt}, base_url: {self.base_url}")
                            self.model = OllamaEmbeddings(
                                model=model_name_attempt,
                                base_url=self.base_url
                            )
                            # Ollama模型维度需要通过测试获取
                            logger.debug(f"测试模型调用: {model_name_attempt}")
                            test_embedding = self.model.embed_query("test")
                            self.embedding_dim = len(test_embedding)
                        else:
                            # 使用直接 API 调用
                            logger.info(f"正在尝试初始化 Ollama 嵌入模型 (直接API): {model_name_attempt}, base_url: {self.base_url}")
                            # 创建一个简单的包装类
                            class DirectOllamaEmbeddings:
                                def __init__(self, model_name, base_url):
                                    self.model_name = model_name
                                    self.base_url = base_url.rstrip('/')
                                
                                def embed_query(self, text: str) -> List[float]:
                                    url = f"{self.base_url}/api/embeddings"
                                    response = requests.post(url, json={
                                        "model": self.model_name,
                                        "prompt": text
                                    }, timeout=30)
                                    response.raise_for_status()
                                    return response.json()["embedding"]
                                
                                def embed_documents(self, texts: List[str]) -> List[List[float]]:
                                    embeddings = []
                                    for text in texts:
                                        embeddings.append(self.embed_query(text))
                                    return embeddings
                            
                            self.model = DirectOllamaEmbeddings(model_name_attempt, self.base_url)
                            # 测试调用
                            logger.debug(f"测试模型调用: {model_name_attempt}")
                            test_embedding = self.model.embed_query("test")
                            self.embedding_dim = len(test_embedding)
                        
                        logger.info(f"Ollama嵌入模型初始化成功: {model_name_attempt}, 维度: {self.embedding_dim}")
                        # 成功则更新配置中的模型名称
                        self.model_name = model_name_attempt
                        break
                    except Exception as e:
                        last_error = e
                        logger.warning(f"尝试模型名称 {model_name_attempt} 失败: {str(e)}")
                        self.model = None
                        continue
                
                if self.model is None:
                    raise Exception(f"所有模型名称尝试都失败。最后错误: {str(last_error)}")
            elif self.provider == "openai" or self.provider == "openai-compatible":
                from langchain_community.embeddings import OpenAIEmbeddings
                logger.info(f"正在初始化 OpenAI 嵌入模型: {self.model_name}, base_url: {self.base_url}")
                self.model = OpenAIEmbeddings(
                    openai_api_key=self.api_key,
                    openai_api_base=self.base_url,
                    model=self.model_name
                )
                # OpenAI模型维度需要通过测试获取
                test_embedding = self.model.embed_query("test")
                self.embedding_dim = len(test_embedding)
                logger.info(f"OpenAI嵌入模型初始化成功: {self.model_name}, 维度: {self.embedding_dim}")
            elif self.provider == "local" or self.provider == "sentence-transformers":
                # 尝试使用本地 sentence-transformers 模型
                try:
                    from langchain_community.embeddings import HuggingFaceEmbeddings
                    logger.info(f"正在初始化本地嵌入模型: {self.model_name}")
                    self.model = HuggingFaceEmbeddings(
                        model_name=self.model_name,
                        model_kwargs={'device': 'cpu'},
                        encode_kwargs={'normalize_embeddings': True}
                    )
                    test_embedding = self.model.embed_query("test")
                    self.embedding_dim = len(test_embedding)
                    logger.info(f"本地嵌入模型初始化成功: {self.model_name}, 维度: {self.embedding_dim}")
                except ImportError:
                    logger.warning("HuggingFaceEmbeddings 不可用，尝试使用 sentence-transformers 直接加载")
                    try:
                        from sentence_transformers import SentenceTransformer
                        logger.info(f"正在使用 sentence-transformers 加载模型: {self.model_name}")
                        self.model = SentenceTransformer(self.model_name)
                        test_embedding = self.model.encode("test")
                        self.embedding_dim = len(test_embedding)
                        logger.info(f"sentence-transformers 模型加载成功: {self.model_name}, 维度: {self.embedding_dim}")
                    except Exception as e2:
                        logger.error(f"sentence-transformers 加载失败: {str(e2)}")
                        raise
            else:
                raise ValueError(f"不支持的嵌入模型提供商: {self.provider}")
        except Exception as e:
            error_msg = f"加载嵌入模型失败 (provider={self.provider}, model={self.model_name}, base_url={self.base_url}): {str(e)}"
            logger.error(error_msg)
            logger.error("请检查：1) Ollama 服务是否启动 2) 模型是否存在 3) 网络连接是否正常 4) 配置是否正确")
            self.model = None
            self.embedding_dim = 384
            # 不抛出异常，允许服务继续运行，但会在使用时抛出更明确的错误
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim,
            "model_loaded": self.model is not None
        } 