# -*- coding: utf-8 -*-
"""
协议模型适配
"""
from dataclasses import dataclass


@dataclass
class StreamMode:
    """流式模式配置"""
    token: int = 100  # 每次输出的token数

