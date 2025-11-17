# -*- coding: utf-8 -*-
"""
文件下载API
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import os
from pathlib import Path
from utils.log_helper import get_logger

logger = get_logger("files_api")

router = APIRouter(prefix="/api/files", tags=["文件"])

# 允许访问的文件目录（白名单）
ALLOWED_DIRS = [
    "reports",  # 报告文件目录
    "uploads",  # 上传文件目录
    "static",   # 静态文件目录
]

def is_safe_path(file_path: str) -> bool:
    """检查文件路径是否安全（防止路径遍历攻击）"""
    try:
        # 解析路径
        resolved_path = Path(file_path).resolve()
        
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.resolve()
        
        # 检查路径是否在允许的目录下
        for allowed_dir in ALLOWED_DIRS:
            allowed_path = project_root / allowed_dir
            try:
                resolved_path.relative_to(allowed_path)
                return True
            except ValueError:
                continue
        
        return False
    except Exception as e:
        logger.error(f"路径安全检查失败: {e}")
        return False

@router.get("/download/{file_path:path}")
async def download_file(file_path: str):
    """
    下载文件
    
    Args:
        file_path: 文件路径（相对于项目根目录，如 reports/report_20251117.md）
    
    Returns:
        FileResponse: 文件响应
    """
    try:
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.resolve()
        full_path = project_root / file_path
        
        # 安全检查
        if not is_safe_path(str(full_path)):
            raise HTTPException(
                status_code=403,
                detail=f"访问被拒绝：文件路径不在允许的目录中"
            )
        
        # 检查文件是否存在
        if not full_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"文件不存在: {file_path}"
            )
        
        if not full_path.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"路径不是文件: {file_path}"
            )
        
        # 获取文件名（用于下载时的文件名）
        filename = full_path.name
        
        # 根据文件扩展名确定媒体类型
        media_type_map = {
            ".md": "text/markdown",
            ".html": "text/html",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".json": "application/json",
            ".csv": "text/csv",
        }
        
        ext = full_path.suffix.lower()
        media_type = media_type_map.get(ext, "application/octet-stream")
        
        logger.info(f"下载文件: {file_path}, 媒体类型: {media_type}")
        
        return FileResponse(
            path=str(full_path),
            filename=filename,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"下载文件失败: {str(e)}"
        )

@router.get("/list")
async def list_files(directory: str = "reports"):
    """
    列出指定目录下的文件
    
    Args:
        directory: 目录名称（必须是允许的目录之一）
    
    Returns:
        List[Dict]: 文件列表
    """
    try:
        # 安全检查
        if directory not in ALLOWED_DIRS:
            raise HTTPException(
                status_code=403,
                detail=f"访问被拒绝：目录 {directory} 不在允许的目录列表中"
            )
        
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.resolve()
        dir_path = project_root / directory
        
        if not dir_path.exists():
            return []
        
        if not dir_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"路径不是目录: {directory}"
            )
        
        # 列出文件
        files = []
        for file_path in dir_path.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": f"{directory}/{file_path.name}",
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "download_url": f"/api/files/download/{directory}/{file_path.name}"
                })
        
        # 按修改时间倒序排序
        files.sort(key=lambda x: x["modified"], reverse=True)
        
        return files
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"列出文件失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"列出文件失败: {str(e)}"
        )

