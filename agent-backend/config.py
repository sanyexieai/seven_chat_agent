# -*- coding: utf-8 -*-
"""
RAG和嵌入相关配置
"""

import os

# 嵌入模型配置
# 注意: 对于中文文本(如三国演义), 建议使用中文优化的嵌入模型
# 推荐模型: bge-large-zh, bge-m3, qwen2.5 等
# 使用 ollama pull bge-m3 下载中文模型
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

# 向量数据库配置
VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "chroma")
VECTOR_DB_PATH = os.getenv("VECTOR_DB_PATH", "data/vector_db")

# 文本分块配置
# 增大分块大小和重叠以保持上下文完整性(特别是对于叙事文本)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# 检索配置
TOP_K = int(os.getenv("TOP_K", "5"))
MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "4000"))

# LLM配置
BASE_URL = os.getenv("BASE_URL", "http://localhost:11434")
