# -*- coding: utf-8 -*-
"""
文件工具适配
"""
import os
import uuid
import tempfile
from typing import List, Optional, Dict, Any
from pathlib import Path


def generate_data_id(prefix: str = "") -> str:
    """生成数据ID"""
    if prefix:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    return uuid.uuid4().hex[:8]


async def download_all_files_in_path(
    file_names: Optional[List[str]] = None,
    work_dir: Optional[str] = None
) -> List[Dict[str, str]]:
    """下载文件到工作目录（适配函数）"""
    if not file_names:
        return []
    
    if not work_dir:
        work_dir = tempfile.mkdtemp()
    
    downloaded_files = []
    for file_name in file_names:
        # 这里应该实现实际的文件下载逻辑
        # 目前返回空列表，需要根据实际需求实现
        file_path = os.path.join(work_dir, file_name)
        if os.path.exists(file_path):
            downloaded_files.append({
                "file_name": file_name,
                "file_path": file_path
            })
    
    return downloaded_files


async def upload_file(
    content: str,
    file_name: str,
    file_type: str,
    request_id: str = ""
) -> Dict[str, Any]:
    """上传文件（适配函数）"""
    # 这里应该实现实际的文件上传逻辑
    # 目前返回模拟数据
    return {
        "file_name": file_name,
        "file_type": file_type,
        "url": f"/files/{request_id}/{file_name}",
        "size": len(content)
    }


async def upload_file_by_path(
    file_path: str,
    request_id: str = ""
) -> Optional[Dict[str, Any]]:
    """通过路径上传文件（适配函数）"""
    if not os.path.exists(file_path):
        return None
    
    file_name = os.path.basename(file_path)
    file_type = Path(file_path).suffix[1:] if Path(file_path).suffix else ""
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return await upload_file(
        content=content.decode('utf-8', errors='ignore'),
        file_name=file_name,
        file_type=file_type,
        request_id=request_id
    )


def truncate_files(
    files: List[Any],
    max_tokens: int
) -> List[Any]:
    """截断文件列表以适应token限制（适配函数）"""
    # 简单的实现：如果文件列表太长，截取前面的
    # 实际应该根据内容长度计算token
    if len(files) <= max_tokens // 100:  # 假设每个文件平均100 tokens
        return files
    return files[:max_tokens // 100]


def flatten_search_file(file: Dict[str, Any]) -> List[Dict[str, Any]]:
    """展平搜索文件（适配函数）"""
    # 如果文件是搜索结果格式，需要展平
    if isinstance(file, dict) and "content" in file:
        return [file]
    return [file] if isinstance(file, dict) else []


async def download_all_files(file_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """下载所有文件（适配函数）"""
    return await download_all_files_in_path(file_names=file_names)

