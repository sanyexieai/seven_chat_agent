import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "AI Agent System"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # 数据库配置
    DATABASE_URL: Optional[str] = None
    
    # Redis配置 (已移除，项目未使用)
    # REDIS_URL: str = "redis://localhost:6379"
    
    # LLM配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_MAX_TOKENS: int = 2048
    OPENAI_TEMPERATURE: float = 0.7
    
    # Anthropic配置
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-sonnet-20240229"
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Optional[str] = "logs/app.log"
    
    # 安全配置
    SECRET_KEY: str = "your-secret-key-here"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 文件上传配置
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_FILE_TYPES: list = [".txt", ".md", ".pdf", ".docx", ".xlsx"]
    
    # WebSocket配置
    WS_HEARTBEAT_INTERVAL: int = 30
    
    # 智能体配置
    DEFAULT_AGENT: str = "general_agent"
    AUTO_SELECT_AGENT: bool = True
    
    # 工具配置
    ENABLE_WEB_SEARCH: bool = True
    ENABLE_DOCUMENT_SEARCH: bool = True
    ENABLE_FILE_OPERATIONS: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# 创建全局设置实例
settings = Settings()

# 环境变量覆盖
def get_settings() -> Settings:
    """获取设置实例"""
    return settings

# 验证必要的配置
def validate_settings():
    """验证配置"""
    if not settings.OPENAI_API_KEY and not settings.ANTHROPIC_API_KEY:
        print("警告: 未配置LLM API密钥，某些功能可能无法正常工作")
    
    if not settings.DATABASE_URL:
        print("信息: 未配置数据库URL，将使用内存存储")
    
    # 创建必要的目录
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True) 