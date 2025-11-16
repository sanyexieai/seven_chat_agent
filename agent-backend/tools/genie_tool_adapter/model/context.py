# -*- coding: utf-8 -*-
"""
上下文模型适配
"""
from contextvars import ContextVar
from typing import Optional


# 请求ID上下文
request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class RequestIdCtx:
    """请求ID上下文"""
    request_id: str = ""
    
    @classmethod
    def get(cls) -> Optional[str]:
        """获取当前请求ID"""
        return request_id_ctx.get()
    
    @classmethod
    def set(cls, request_id: str):
        """设置请求ID"""
        request_id_ctx.set(request_id)
        cls.request_id = request_id


class LLMModelInfoFactory:
    """LLM模型信息工厂"""
    
    # 默认模型上下文长度映射
    _context_lengths = {
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-4.1": 128000,
        "gpt-3.5-turbo": 16385,
        "gpt-3.5-turbo-16k": 16385,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
    }
    
    @classmethod
    def get_context_length(cls, model: Optional[str] = None) -> int:
        """获取模型的上下文长度"""
        if not model:
            return 8192  # 默认值
        
        # 尝试从环境变量获取
        import os
        env_key = f"{model.upper().replace('-', '_')}_CONTEXT_LENGTH"
        env_value = os.getenv(env_key)
        if env_value:
            try:
                return int(env_value)
            except ValueError:
                pass
        
        # 从映射表获取
        return cls._context_lengths.get(model, 8192)
    
    @classmethod
    def register_model(cls, model_name: str, context_length: int):
        """注册模型上下文长度"""
        cls._context_lengths[model_name] = context_length

