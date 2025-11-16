from typing import Dict, Any, List
from tools.base_tool import BaseTool
import aiofiles
import os
import json
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

class FileWriterTool(BaseTool):
    """文件写入工具"""
    
    def __init__(self):
        super().__init__(
            name="file_writer",
            description="写入文件内容",
            container_type=BaseTool.CONTAINER_TYPE_FILE,  # 绑定文件容器
            container_config={
                "workspace_dir": "files",
                "read_only": False
            }
        )
        self.supported_extensions = ['.txt', '.md', '.json', '.csv', '.py', '.js', '.html', '.css']
    
    async def execute(self, parameters: Dict[str, Any]) -> str:
        """写入文件"""
        file_path = parameters.get("file_path", "")
        content = parameters.get("content", "")
        encoding = parameters.get("encoding", "utf-8")
        mode = parameters.get("mode", "w")  # w: 覆盖, a: 追加
        
        if not file_path:
            return "文件路径不能为空"
        
        if not content:
            return "文件内容不能为空"
        
        try:
            await self._write_file(file_path, content, encoding, mode)
            return f"文件写入成功: {file_path}"
        except Exception as e:
            return f"文件写入失败: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码",
                    "default": "utf-8"
                },
                "mode": {
                    "type": "string",
                    "description": "写入模式",
                    "enum": ["w", "a"],
                    "default": "w"
                }
            },
            "required": ["file_path", "content"]
        }
    
    async def _write_file(self, file_path: str, content: str, encoding: str, mode: str):
        """写入文件"""
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in self.supported_extensions:
            raise ValueError(f"不支持的文件类型: {file_ext}")
        
        async with aiofiles.open(file_path, mode, encoding=encoding) as f:
            await f.write(content)
    
    def create_directory(self, dir_path: str) -> bool:
        """创建目录"""
        try:
            os.makedirs(dir_path, exist_ok=True)
            return True
        except Exception:
            return False
    
    def list_files(self, dir_path: str) -> List[Dict[str, Any]]:
        """列出目录中的文件"""
        if not os.path.exists(dir_path):
            return []
        
        files = []
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isfile(item_path):
                stat = os.stat(item_path)
                files.append({
                    "name": item,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "extension": Path(item_path).suffix.lower()
                })
        
        return files 