# -*- coding: utf-8 -*-
"""
文件读取工具
"""
from typing import Dict, Any
from tools.base_tool import BaseTool
import aiofiles
import os
from pathlib import Path


class FileReaderTool(BaseTool):
    """文件读取工具"""
    
    def __init__(self):
        super().__init__(
            name="file_reader",
            description="读取文件内容",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "files",
                "read_only": True
            }
        )
        self.supported_extensions = ['.txt', '.md', '.json', '.csv', '.py', '.js', '.html', '.css']
    
    async def execute(self, parameters: Dict[str, Any]) -> str:
        """读取文件"""
        file_path = parameters.get("file_path", "")
        encoding = parameters.get("encoding", "utf-8")
        
        if not file_path:
            return "文件路径不能为空"
        
        try:
            content = await self._read_file(file_path, encoding)
            return content
        except Exception as e:
            return f"文件读取失败: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码",
                    "default": "utf-8"
                }
            },
            "required": ["file_path"]
        }
    
    async def _read_file(self, file_path: str, encoding: str) -> str:
        """读取文件内容"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.supported_extensions:
            raise ValueError(f"不支持的文件类型: {file_ext}")
        
        async with aiofiles.open(file_path, 'r', encoding=encoding) as f:
            content = await f.read()
        
        return content
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """获取文件信息"""
        if not os.path.exists(file_path):
            return {"error": "文件不存在"}
        
        stat = os.stat(file_path)
        return {
            "name": os.path.basename(file_path),
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "extension": Path(file_path).suffix.lower()
        }
