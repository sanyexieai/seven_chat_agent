# -*- coding: utf-8 -*-
"""
httpx 兼容性模块
解决不同版本 httpx 中 TimeoutError 的兼容性问题
"""

import sys
from typing import Type, Union

# 尝试导入 httpx
try:
    import httpx
except ImportError:
    httpx = None

# 定义兼容的 TimeoutError
_TimeoutError: Type[Exception] = None

def get_timeout_error() -> Type[Exception]:
    """
    获取超时异常类型，兼容不同版本的 httpx
    
    Returns:
        超时异常类
    """
    global _TimeoutError
    
    if _TimeoutError is not None:
        return _TimeoutError
    
    if httpx is None:
        # 如果 httpx 未安装，使用通用异常
        class TimeoutError(Exception):
            """httpx 未安装时的占位符超时异常"""
            pass
        _TimeoutError = TimeoutError
        return _TimeoutError
    
    # 检查 httpx.TimeoutError 是否存在
    if hasattr(httpx, 'TimeoutError'):
        _TimeoutError = httpx.TimeoutError
        return _TimeoutError
    
    # 尝试使用其他超时异常类型
    timeout_exceptions = [
        'TimeoutException',
        'ReadTimeout', 
        'ConnectTimeout',
        'Timeout',
        'RequestError'  # 作为最后的备选
    ]
    
    for exc_name in timeout_exceptions:
        if hasattr(httpx, exc_name):
            exc_class = getattr(httpx, exc_name)
            # 创建一个兼容的异常类
            class TimeoutError(exc_class):
                """兼容 httpx.TimeoutError 的异常类"""
                pass
            _TimeoutError = TimeoutError
            # 同时设置到 httpx 模块，以便其他库使用
            httpx.TimeoutError = TimeoutError
            return _TimeoutError
    
    # 如果都不存在，创建一个占位符
    class TimeoutError(Exception):
        """httpx.TimeoutError 的兼容性占位符"""
        pass
    _TimeoutError = TimeoutError
    httpx.TimeoutError = TimeoutError
    return _TimeoutError


def is_timeout_error(error: Exception) -> bool:
    """
    判断异常是否为超时错误
    
    Args:
        error: 异常对象
        
    Returns:
        是否为超时错误
    """
    if error is None:
        return False
    
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    # 检查异常类型名称
    timeout_types = ['timeout', 'timedout', 'timed_out']
    if any(keyword in error_type.lower() for keyword in timeout_types):
        return True
    
    # 检查异常消息
    timeout_keywords = ['timeout', 'timed out', 'connection timeout', 'read timeout']
    if any(keyword in error_msg for keyword in timeout_keywords):
        return True
    
    # 检查是否是 httpx 超时异常
    if httpx:
        timeout_error = get_timeout_error()
        if isinstance(error, timeout_error):
            return True
    
    return False


# 初始化：在模块导入时立即设置兼容性补丁
if httpx and not hasattr(httpx, 'TimeoutError'):
    get_timeout_error()  # 这会自动设置 httpx.TimeoutError

# 导出
TimeoutError = get_timeout_error()
__all__ = ['TimeoutError', 'get_timeout_error', 'is_timeout_error']

