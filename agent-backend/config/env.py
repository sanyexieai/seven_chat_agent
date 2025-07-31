# -*- coding: utf-8 -*-
"""
环境配置
"""

import os
from typing import Optional

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# LLM配置
MODEL = os.getenv("MODEL", "qwen3:32b")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
BASE_URL = os.getenv("BASE_URL", "http://localhost:11434")
API_KEY = os.getenv("API_KEY", "")


# 备用LLM配置
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "gpt-3.5-turbo")
BACKUP_PROVIDER = os.getenv("BACKUP_PROVIDER", "ollama")

# MCP配置
MCP_CONFIG_FILE = os.getenv("MCP_CONFIG_FILE", "config/mcp_config.json")

# 应用配置
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///agent_system.db")

# Redis配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# 文件上传配置
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", "10"))  # MB

# 安全配置
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# 会话配置
SESSION_TIMEOUT = int(os.getenv("SESSION_TIMEOUT", "3600"))  # 秒

# 工具配置
ENABLE_WEB_SEARCH = os.getenv("ENABLE_WEB_SEARCH", "True").lower() == "true"
ENABLE_DOCUMENT_SEARCH = os.getenv("ENABLE_DOCUMENT_SEARCH", "True").lower() == "true"
ENABLE_FILE_OPERATIONS = os.getenv("ENABLE_FILE_OPERATIONS", "True").lower() == "true"

# 智能体配置
DEFAULT_AGENT = os.getenv("DEFAULT_AGENT", "chat_agent")
ENABLE_AGENT_SELECTION = os.getenv("ENABLE_AGENT_SELECTION", "True").lower() == "true"

# 流式响应配置
STREAM_ENABLED = os.getenv("STREAM_ENABLED", "True").lower() == "true"
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", "1024"))

# 缓存配置
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "True").lower() == "true"
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 秒

# 监控配置
ENABLE_MONITORING = os.getenv("ENABLE_MONITORING", "True").lower() == "true"
METRICS_ENDPOINT = os.getenv("METRICS_ENDPOINT", "/metrics")

# 开发配置
RELOAD_ENABLED = os.getenv("RELOAD_ENABLED", "True").lower() == "true"
WORKERS = int(os.getenv("WORKERS", "1"))

def get_config() -> dict:
    """获取完整配置"""
    return {
        "log_level": LOG_LEVEL,
        "model": MODEL,
        "model_provider": MODEL_PROVIDER,
        "temperature": TEMPERATURE,
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "ollama_base_url": OLLAMA_BASE_URL,
        "debug": DEBUG,
        "host": HOST,
        "port": PORT,
        "database_url": DATABASE_URL,
        "redis_url": REDIS_URL,
        "upload_dir": UPLOAD_DIR,
        "max_file_size": MAX_FILE_SIZE,
        "secret_key": SECRET_KEY,
        "allowed_hosts": ALLOWED_HOSTS,
        "session_timeout": SESSION_TIMEOUT,
        "enable_web_search": ENABLE_WEB_SEARCH,
        "enable_document_search": ENABLE_DOCUMENT_SEARCH,
        "enable_file_operations": ENABLE_FILE_OPERATIONS,
        "default_agent": DEFAULT_AGENT,
        "enable_agent_selection": ENABLE_AGENT_SELECTION,
        "stream_enabled": STREAM_ENABLED,
        "stream_chunk_size": STREAM_CHUNK_SIZE,
        "cache_enabled": CACHE_ENABLED,
        "cache_ttl": CACHE_TTL,
        "enable_monitoring": ENABLE_MONITORING,
        "metrics_endpoint": METRICS_ENDPOINT,
        "reload_enabled": RELOAD_ENABLED,
        "workers": WORKERS,
    } 