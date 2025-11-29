"""深度搜索文件工具"""
from typing import List, Any


def truncate_files(
    files: List[Any],
    max_tokens: int
) -> List[Any]:
    """截断文件列表以适应token限制"""
    # 简单的实现：如果文件列表太长，截取前面的
    # 实际应该根据内容长度计算token
    if len(files) <= max_tokens // 100:  # 假设每个文件平均100 tokens
        return files
    return files[:max_tokens // 100]

