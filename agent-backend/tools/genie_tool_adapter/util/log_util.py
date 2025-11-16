# -*- coding: utf-8 -*-
"""
日志工具适配
"""
from functools import wraps
from typing import Callable, Any
import time
from utils.log_helper import get_logger

logger = get_logger("genie_tool_adapter")


def timer(key: str = ""):
    """计时装饰器，支持 @timer 和 @timer() 两种用法"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"{func.__name__} 执行时间: {elapsed:.2f}秒")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func.__name__} 执行失败 (耗时 {elapsed:.2f}秒): {e}")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                logger.debug(f"{func.__name__} 执行时间: {elapsed:.2f}秒")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"{func.__name__} 执行失败 (耗时 {elapsed:.2f}秒): {e}")
                raise
        
        # 检查是否是协程函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    # 如果直接作为装饰器使用（没有参数），key 就是函数本身
    if callable(key):
        func = key
        key = ""
        return decorator(func)
    
    return decorator

