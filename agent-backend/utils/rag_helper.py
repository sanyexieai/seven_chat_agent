# -*- coding: utf-8 -*-
from typing import Optional, List, Dict, Any
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

from utils.llm_helper import get_llm_helper
from utils.log_helper import get_logger
from utils.embedding_service import EmbeddingService
from utils.enhanced_chunker import EnhancedChunker
from config import (
    VECTOR_DB_TYPE, VECTOR_DB_PATH,
    CHUNK_SIZE, CHUNK_OVERLAP, TOP_K, MAX_CONTEXT_LENGTH
)

class RAGHelper:
    """基于LangChain的RAG助手类"""
    
    def __init__(self):
        self.logger = get_logger("RAGHelper")
        self.llm_helper = get_llm_helper()
        self.vectorstore = None
        self.embedding_service = EmbeddingService()
        self.chunker = EnhancedChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        self._setup_components()
    
    def _setup_components(self):
        """初始化组件"""
        try:
            self.logger.info(f"✅ RAG组件初始化成功")

            # 尝试加载已存在的向量数据库
            try:
                import os
                if os.path.exists(VECTOR_DB_PATH):
                    self.vectorstore = Chroma(
                        collection_name="company_research",
                        embedding_function=self.embedding_service.model,
                        persist_directory=VECTOR_DB_PATH
                    )
                    self.logger.info(f"✅ 成功加载已存在的向量数据库: {VECTOR_DB_PATH}")
            except Exception as e:
                self.logger.warning(f"⚠️ 加载已存在向量数据库失败: {e}")

        except Exception as e:
            self.logger.error(f"❌ RAG组件初始化失败: {e}")
            raise
    
    def add_documents(self, documents: List[str], metadata: Optional[List[Dict[str, Any]]] = None):
        """添加文档到向量数据库"""
        try:
            # 使用增强分块器分割文档
            split_docs = self.chunker.chunk_documents(documents, metadata)

            # 确保向量数据库目录存在
            import os
            os.makedirs(VECTOR_DB_PATH, exist_ok=True)

            # 创建或加载向量数据库
            if self.vectorstore is None:
                # 首次创建向量数据库
                self.vectorstore = Chroma.from_documents(
                    documents=split_docs,
                    embedding=self.embedding_service.model,
                    collection_name="company_research",
                    persist_directory=VECTOR_DB_PATH
                )
            else:
                # 向现有向量数据库添加文档
                self.vectorstore.add_documents(split_docs)

            self.logger.info(f"✅ 成功添加{len(documents)}个文档到向量数据库，生成{len(split_docs)}个chunks")

        except Exception as e:
            self.logger.error(f"❌ 添加文档失败: {e}")
            raise
    
    def get_context_for_llm(self, query: str, max_chars: int = None, top_k: int = None) -> Optional[str]:
        """为LLM获取相关上下文"""
        try:
            if not self.vectorstore:
                self.logger.warning("⚠️ 向量数据库未初始化，返回空上下文")
                return None

            # 使用配置的默认值
            if max_chars is None:
                max_chars = MAX_CONTEXT_LENGTH
            if top_k is None:
                top_k = TOP_K

            # 检索相关文档
            docs = self.vectorstore.similarity_search(query, k=top_k)

            # 合并文档内容
            context_parts = []
            current_length = 0

            for doc in docs:
                doc_content = doc.page_content
                if current_length + len(doc_content) > max_chars:
                    break
                context_parts.append(doc_content)
                current_length += len(doc_content)

            context = "\n\n".join(context_parts)

            if context:
                self.logger.info(f"✅ 成功获取上下文，长度: {len(context)}字符")
                return context
            else:
                self.logger.warning("⚠️ 未找到相关上下文")
                return None

        except Exception as e:
            self.logger.error(f"❌ 获取上下文失败: {e}")
            raise
    
    def search_similar(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """搜索相似文档"""
        try:
            if not self.vectorstore:
                return []
            
            # 使用配置的默认值
            if top_k is None:
                top_k = TOP_K
            
            docs = self.vectorstore.similarity_search_with_score(query, k=top_k)
            
            results = []
            for doc, score in docs:
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score
                })
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ 搜索失败: {e}")
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            if not self.vectorstore:
                return {"status": "not_initialized"}
            
            # 这里可以添加更多统计信息
            return {
                "status": "initialized",
                "collection_name": "company_research"
            }
            
        except Exception as e:
            self.logger.error(f"❌ 获取统计信息失败: {e}")
            return {"status": "error", "error": str(e)}

class MockRAGHelper:
    """模拟RAG助手，用于测试和开发"""
    
    def __init__(self):
        self.logger = get_logger("MockRAGHelper")
        self.mock_data = {
            "4Paradigm": """
            4Paradigm（第四范式）是一家专注于企业级人工智能平台的公司。
            公司成立于2014年，总部位于北京，是中国领先的AI平台提供商。
            主要产品包括：
            1. 4Paradigm Sage - 企业级AI平台
            2. 4Paradigm Prophet - 机器学习平台
            3. 4Paradigm HyperCycle - 自动机器学习平台
            
            财务数据：
            - 2022年营收：约15亿元人民币
            - 员工规模：超过1000人
            - 客户数量：超过300家企业客户
            
            技术优势：
            - 在自动机器学习领域处于领先地位
            - 拥有多项核心专利技术
            - 在金融、零售、制造等行业有广泛应用
            """,
            "商汤科技": """
            商汤科技（SenseTime）是中国领先的人工智能软件公司。
            公司成立于2014年，专注于计算机视觉和深度学习技术。
            主要业务包括：
            1. 智慧商业 - 为金融、零售、制造等行业提供AI解决方案
            2. 智慧城市 - 面向政府客户的城市管理AI平台
            3. 智慧生活 - 涵盖手机、AR/VR等消费级AI应用
            4. 智能汽车 - 自动驾驶和车舱交互解决方案
            
            财务数据：
            - 2022年营收：38.1亿元人民币
            - 毛利率：69.2%
            - 研发投入：28.6亿元，占收入比重75.1%
            
            技术优势：
            - 拥有8,000多项AI相关专利
            - 建成亚洲最大AI计算平台之一
            - 已服务超过1,200家客户
            """
        }
    
    def get_context_for_llm(self, query: str, max_tokens: int = None, top_k: int = None) -> Optional[str]:
        """获取模拟上下文"""
        try:
            # 使用配置的默认值
            if max_tokens is None:
                max_tokens = MAX_CONTEXT_LENGTH
            
            # 简单的关键词匹配
            if "4Paradigm" in query or "第四范式" in query:
                return self.mock_data.get("4Paradigm", "")
            elif "商汤" in query or "SenseTime" in query:
                return self.mock_data.get("商汤科技", "")
            else:
                # 返回通用信息
                return """
                AI行业概况：
                人工智能行业正处于快速发展阶段，全球AI市场规模预计到2025年将达到1900亿美元。
                主要技术领域包括机器学习、深度学习、计算机视觉、自然语言处理等。
                中国在AI领域具有显著优势，特别是在应用场景和数据资源方面。
                """
                
        except Exception as e:
            self.logger.error(f"❌ 获取模拟上下文失败: {e}")
            return None
    
    def search_similar(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        """模拟搜索"""
        return [
            {
                "content": "模拟搜索结果",
                "metadata": {"source": "mock"},
                "score": 0.95
            }
        ]
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """获取模拟统计信息"""
        return {
            "status": "mock_mode",
            "documents_count": 2,
            "collection_name": "mock_company_research"
        }

def get_rag_helper(use_mock: bool = False) -> RAGHelper:
    """获取RAG助手实例"""
    if use_mock:
        return MockRAGHelper()
    else:
        return RAGHelper() 