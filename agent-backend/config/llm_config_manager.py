import os
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from database.database import SessionLocal
from services.llm_config_service import LLMConfigService
from utils.log_helper import get_logger

logger = get_logger("llm_config_manager")

class LLMConfigManager:
    """LLM配置管理器"""
    
    def __init__(self):
        self._config_cache = {}
        self._default_config = None
        self._initialized = False
    
    def initialize(self):
        """初始化配置管理器"""
        if self._initialized:
            return
        
        try:
            # 加载默认配置
            self._load_default_config()
            self._initialized = True
            logger.info("LLM配置管理器初始化完成")
        except Exception as e:
            logger.error(f"LLM配置管理器初始化失败: {str(e)}")
            # 如果数据库配置失败，使用默认配置
            self._load_fallback_config()
    
    def _load_default_config(self):
        """从数据库加载默认配置"""
        db = SessionLocal()
        try:
            config = LLMConfigService.get_default_config(db)
            if config:
                self._default_config = config
                self._config_cache[config.name] = config
                logger.info(f"加载默认LLM配置: {config.display_name}")
            else:
                logger.warning("未找到默认LLM配置，使用fallback配置")
                self._load_fallback_config()
        except Exception as e:
            logger.error(f"加载数据库配置失败: {str(e)}")
            self._load_fallback_config()
        finally:
            db.close()
    
    def _load_fallback_config(self):
        """加载fallback配置（从环境变量或默认值）"""
        fallback_config = {
            "name": "default",
            "display_name": "默认配置",
            "provider": "openai",
            "model_name": "gpt-3.5-turbo",
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "api_base": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
            "config": {
                "temperature": 0.7,
                "max_tokens": 2048
            },
            "is_default": True,
            "is_active": True
        }
        
        self._default_config = type('Config', (), fallback_config)()
        self._config_cache["default"] = self._default_config
        logger.info("使用fallback LLM配置")
    
    def get_config(self, config_name: str = None) -> Optional[Dict[str, Any]]:
        """获取LLM配置"""
        if not self._initialized:
            self.initialize()
        
        if config_name:
            # 从缓存获取指定配置
            if config_name in self._config_cache:
                return self._config_cache[config_name]
            
            # 从数据库加载指定配置
            db = SessionLocal()
            try:
                config = LLMConfigService.get_config_by_name(db, config_name)
                if config:
                    self._config_cache[config_name] = config
                    return config
            except Exception as e:
                logger.error(f"加载配置 {config_name} 失败: {str(e)}")
            finally:
                db.close()
        
        # 返回默认配置
        return self._default_config
    
    def get_default_config(self) -> Optional[Dict[str, Any]]:
        """获取默认配置"""
        if not self._initialized:
            self.initialize()
        return self._default_config
    
    def get_config_for_provider(self, provider: str) -> Optional[Dict[str, Any]]:
        """根据提供商获取配置"""
        db = SessionLocal()
        try:
            config = LLMConfigService.get_config_for_provider(db, provider)
            if config:
                self._config_cache[config.name] = config
                return config
        except Exception as e:
            logger.error(f"获取提供商 {provider} 配置失败: {str(e)}")
        finally:
            db.close()
        return None
    
    def refresh_config(self):
        """刷新配置缓存"""
        self._config_cache.clear()
        self._initialized = False
        self.initialize()
    
    def get_openai_config(self) -> Dict[str, Any]:
        """获取OpenAI配置"""
        config = self.get_config_for_provider("openai")
        if config:
            config_dict = {
                "api_key": config.api_key,
                "api_base": config.api_base,
                "model": config.model_name
            }
            if config.config:
                config_dict.update(config.config)
            return config_dict
        
        # 返回默认OpenAI配置
        return {
            "api_key": os.getenv("OPENAI_API_KEY", ""),
            "api_base": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "max_tokens": 2048
        }
    
    def get_anthropic_config(self) -> Dict[str, Any]:
        """获取Anthropic配置"""
        config = self.get_config_for_provider("anthropic")
        if config:
            config_dict = {
                "api_key": config.api_key,
                "api_base": config.api_base,
                "model": config.model_name
            }
            if config.config:
                config_dict.update(config.config)
            return config_dict
        
        # 返回默认Anthropic配置
        return {
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "api_base": os.getenv("ANTHROPIC_API_BASE", "https://api.anthropic.com"),
            "model": "claude-3-sonnet-20240229",
            "temperature": 0.7,
            "max_tokens": 2048
        }
    
    def get_local_config(self) -> Dict[str, Any]:
        """获取本地模型配置"""
        config = self.get_config_for_provider("local")
        if config:
            config_dict = {
                "api_base": config.api_base,
                "model": config.model_name
            }
            if config.config:
                config_dict.update(config.config)
            return config_dict
        
        # 返回默认本地配置
        return {
            "api_base": os.getenv("LOCAL_API_BASE", "http://localhost:11434"),
            "model": "qwen3:32b",
            "temperature": 0.7,
            "max_tokens": 2048
        }
    
    def get_ollama_config(self) -> Dict[str, Any]:
        """获取Ollama配置"""
        config = self.get_config_for_provider("ollama")
        if config:
            config_dict = {
                "api_base": config.api_base,
                "model": config.model_name
            }
            if config.config:
                config_dict.update(config.config)
            return config_dict
        
        # 返回默认Ollama配置
        return {
            "api_base": os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
            "model": "qwen3:32b",
            "temperature": 0.7,
            "max_tokens": 2048
        }
    
    def get_deepseek_config(self) -> Dict[str, Any]:
        """获取DeepSeek配置"""
        config = self.get_config_for_provider("deepseek")
        if config:
            config_dict = {
                "api_key": config.api_key,
                "api_base": config.api_base,
                "model": config.model_name
            }
            if config.config:
                config_dict.update(config.config)
            return config_dict
        
        # 返回默认DeepSeek配置
        return {
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
            "api_base": os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            "model": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 2048
        }

# 全局配置管理器实例
llm_config_manager = LLMConfigManager() 