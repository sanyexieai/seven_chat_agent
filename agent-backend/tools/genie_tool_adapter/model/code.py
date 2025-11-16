# -*- coding: utf-8 -*-
"""
代码输出模型适配
"""
from dataclasses import dataclass
from typing import List, Optional, Any


@dataclass
class CodeOuput:
    """代码输出"""
    code: str
    file_name: str
    file_list: Optional[List[Any]] = None


@dataclass
class ActionOutput:
    """动作输出"""
    content: str
    file_list: Optional[List[Any]] = None
    output: Optional[str] = None
    is_final_answer: bool = False

