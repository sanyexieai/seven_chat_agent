"""代码解释器文件工具"""
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
    """下载文件到工作目录"""
    if not file_names:
        return []
    
    if not work_dir:
        work_dir = tempfile.mkdtemp()
    
    downloaded_files = []
    for file_name in file_names:
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
    """上传文件"""
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
    """通过路径上传文件"""
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

