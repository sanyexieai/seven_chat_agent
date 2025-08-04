#!/usr/bin/env python3
"""
LLM配置初始化脚本
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.database import SessionLocal
from services.llm_config_service import LLMConfigService
from models.database_models import LLMConfigCreate
from utils.log_helper import get_logger

logger = get_logger("init_llm_configs")

def init_default_llm_configs():
    """初始化默认LLM配置"""
    db = SessionLocal()
    try:
        # 检查是否已有配置
        existing_configs = LLMConfigService.get_all_configs(db)
        if existing_configs:
            logger.info(f"已存在 {len(existing_configs)} 个LLM配置，跳过初始化")
            return
        
        # 默认配置列表
        default_configs = [
            {
                "name": "openai_gpt4",
                "display_name": "OpenAI GPT-4",
                "description": "OpenAI GPT-4 模型配置",
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "api_base": "https://api.openai.com/v1",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": True
            },
            {
                "name": "openai_gpt35",
                "display_name": "OpenAI GPT-3.5",
                "description": "OpenAI GPT-3.5 Turbo 模型配置",
                "provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_key": os.getenv("OPENAI_API_KEY", ""),
                "api_base": "https://api.openai.com/v1",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "anthropic_claude",
                "display_name": "Anthropic Claude",
                "description": "Anthropic Claude 模型配置",
                "provider": "anthropic",
                "model_name": "claude-3-sonnet-20240229",
                "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
                "api_base": "https://api.anthropic.com",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_qwen",
                "display_name": "Ollama Qwen 模型",
                "description": "Ollama Qwen 模型配置",
                "provider": "ollama",
                "model_name": "qwen2.5:7b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_llama",
                "display_name": "Ollama Llama 模型",
                "description": "Ollama Llama 模型配置",
                "provider": "ollama",
                "model_name": "llama3.2:3b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_mistral",
                "display_name": "Ollama Mistral 模型",
                "description": "Ollama Mistral 模型配置",
                "provider": "ollama",
                "model_name": "mistral:7b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_codellama",
                "display_name": "Ollama Code Llama 模型",
                "description": "Ollama Code Llama 代码生成模型配置",
                "provider": "ollama",
                "model_name": "codellama:7b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "ollama_neural",
                "display_name": "Ollama Neural Chat 模型",
                "description": "Ollama Neural Chat 模型配置",
                "provider": "ollama",
                "model_name": "neural-chat:7b",
                "api_key": "",
                "api_base": "http://localhost:11434",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "deepseek_chat",
                "display_name": "DeepSeek Chat",
                "description": "DeepSeek Chat 模型配置",
                "provider": "deepseek",
                "model_name": "deepseek-chat",
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "api_base": "https://api.deepseek.com",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            },
            {
                "name": "deepseek_coder",
                "display_name": "DeepSeek Coder",
                "description": "DeepSeek Coder 代码生成模型配置",
                "provider": "deepseek",
                "model_name": "deepseek-coder",
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "api_base": "https://api.deepseek.com",
                "config": {
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                "is_default": False
            }
        ]
        
        # 创建配置
        for config_data in default_configs:
            try:
                config_create = LLMConfigCreate(**config_data)
                config = LLMConfigService.create_config(db, config_create)
                logger.info(f"创建LLM配置: {config.display_name}")
            except Exception as e:
                logger.error(f"创建LLM配置失败 {config_data['name']}: {str(e)}")
        
        logger.info("LLM配置初始化完成")
        
    except Exception as e:
        logger.error(f"LLM配置初始化失败: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 开始初始化LLM配置...")
    init_default_llm_configs()
    print("✅ LLM配置初始化完成") 