# -*- coding: utf-8 -*-
"""
LLM工具适配
"""
from typing import List, Dict, Any, AsyncGenerator, Optional
from utils.llm_helper import LLMHelper
import os


async def ask_llm(
    messages: Any,
    model: str = "gpt-4.1",
    stream: bool = False,
    only_content: bool = False,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    **kwargs
) -> AsyncGenerator[str, None]:
    """调用LLM（适配函数）"""
    llm_helper = LLMHelper()
    
    # 尝试从环境变量或配置获取模型配置
    # 这里需要根据实际模型名称设置provider
    model_provider = os.getenv("MODEL_PROVIDER", "openai")
    if model.startswith("gpt"):
        model_provider = "openai"
    elif model.startswith("claude"):
        model_provider = "anthropic"
    elif "ollama" in model.lower() or model.startswith("qwen") or model.startswith("llama"):
        model_provider = "ollama"
    
    # 转换消息格式
    if isinstance(messages, str):
        formatted_messages = [{"role": "user", "content": messages}]
    elif isinstance(messages, list):
        formatted_messages = messages
    else:
        formatted_messages = [{"role": "user", "content": str(messages)}]
    
    # 设置模型配置并初始化（setup 不是 async 方法）
    llm_helper.setup(llm_config={
        "provider": model_provider,
        "model_name": model,
        "api_key": os.getenv("API_KEY", ""),
        "api_base": os.getenv("BASE_URL", ""),
        "config": {
            "temperature": temperature or 0.7,
            "top_p": top_p
        }
    })
    
    if stream:
        async for chunk in llm_helper.call_stream(
            messages=formatted_messages,
            temperature=temperature,
            top_p=top_p,
            **kwargs
        ):
            if only_content:
                # 只返回内容部分
                if isinstance(chunk, str):
                    yield chunk
                elif isinstance(chunk, dict) and 'content' in chunk:
                    yield chunk['content']
                elif hasattr(chunk, 'content'):
                    yield chunk.content
            else:
                yield chunk
    else:
        response = await llm_helper.call(
            messages=formatted_messages,
            temperature=temperature,
            top_p=top_p,
            **kwargs
        )
        if only_content:
            if isinstance(response, str):
                yield response
            elif isinstance(response, dict) and 'content' in response:
                yield response['content']
            elif hasattr(response, 'content'):
                yield response.content
        else:
            yield response

