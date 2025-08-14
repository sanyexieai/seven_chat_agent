# -*- coding: utf-8 -*-
"""
LLM配置管理
"""

import os
from typing import Tuple

# 超时配置
OLLAMA_CONNECT_TIMEOUT = int(os.getenv("OLLAMA_CONNECT_TIMEOUT", "10"))  # 连接超时（秒）
OLLAMA_READ_TIMEOUT = int(os.getenv("OLLAMA_READ_TIMEOUT", "120"))      # 读取超时（秒）
OLLAMA_STREAM_READ_TIMEOUT = int(os.getenv("OLLAMA_STREAM_READ_TIMEOUT", "180"))  # 流式读取超时（秒）

# 重试配置
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))          # 最大重试次数
OLLAMA_RETRY_DELAY = float(os.getenv("OLLAMA_RETRY_DELAY", "1.0"))      # 重试延迟（秒）

# 连接池配置
OLLAMA_POOL_CONNECTIONS = int(os.getenv("OLLAMA_POOL_CONNECTIONS", "10"))  # 连接池大小
OLLAMA_POOL_MAXSIZE = int(os.getenv("OLLAMA_POOL_MAXSIZE", "20"))         # 最大连接数

# 其他LLM超时配置
OPENAI_TIMEOUT = int(os.getenv("OPENAI_TIMEOUT", "60"))
ANTHROPIC_TIMEOUT = int(os.getenv("ANTHROPIC_TIMEOUT", "60"))
DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "60"))

def get_ollama_timeout(is_stream: bool = False) -> Tuple[int, int]:
    """
    获取Ollama超时设置
    :param is_stream: 是否为流式请求
    :return: (连接超时, 读取超时)
    """
    if is_stream:
        return (OLLAMA_CONNECT_TIMEOUT, OLLAMA_STREAM_READ_TIMEOUT)
    return (OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT)

def get_ollama_retry_config():
    """
    获取Ollama重试配置
    :return: 重试配置字典
    """
    return {
        'max_retries': OLLAMA_MAX_RETRIES,
        'retry_delay': OLLAMA_RETRY_DELAY,
        'pool_connections': OLLAMA_POOL_CONNECTIONS,
        'pool_maxsize': OLLAMA_POOL_MAXSIZE
    } 