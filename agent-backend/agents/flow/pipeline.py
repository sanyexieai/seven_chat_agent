# -*- coding: utf-8 -*-
"""
流程管道（Pipeline）系统

管道定义了整个流程中使用或生成的文件、文本等所有数据。
流程中的所有节点都可以从管道中获取需要的数据，也可以向管道写入数据。

设计理念：
1. 管道是流程的全局数据存储，所有节点共享
2. 支持多种数据类型：文本、文件、JSON对象、列表等
3. 数据可以按命名空间组织，避免冲突
4. 支持数据版本管理和历史记录
5. 可以持久化到数据库（可选）
"""
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import os
from pathlib import Path
from utils.log_helper import get_logger

logger = get_logger("flow_pipeline")


class Pipeline:
    """流程管道类
    
    用于在整个流程中存储和共享数据。
    所有节点都可以从管道中读取数据，也可以向管道写入数据。
    """
    
    def __init__(self, pipeline_id: Optional[str] = None, persistent: bool = False):
        """
        初始化管道
        
        Args:
            pipeline_id: 管道唯一标识，用于持久化
            persistent: 是否持久化到数据库
        """
        self.pipeline_id = pipeline_id or f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.persistent = persistent
        
        # 数据存储：按命名空间组织
        # 结构：{namespace: {key: value}}
        self._data: Dict[str, Dict[str, Any]] = {}
        
        # 文件存储：存储文件路径和元数据
        # 结构：{file_key: {'path': str, 'type': str, 'size': int, 'metadata': dict}}
        self._files: Dict[str, Dict[str, Any]] = {}
        
        # 历史记录：记录数据变更历史
        self._history: List[Dict[str, Any]] = []
        
        # 初始化默认命名空间
        self._data['global'] = {}
        self._data['nodes'] = {}  # 节点专用命名空间
        
    # ========== 基础数据操作 ==========
    
    def put(self, key: str, value: Any, namespace: str = 'global') -> None:
        """
        向管道中写入数据
        
        Args:
            key: 数据键名
            value: 数据值（可以是任何类型）
            namespace: 命名空间，默认为 'global'
        """
        if namespace not in self._data:
            self._data[namespace] = {}
        
        old_value = self._data[namespace].get(key)
        self._data[namespace][key] = value
        
        # 记录历史
        self._history.append({
            'timestamp': datetime.now().isoformat(),
            'action': 'put',
            'namespace': namespace,
            'key': key,
            'old_value': old_value,
            'new_value': value
        })
        
        logger.debug(f"Pipeline[{self.pipeline_id}] 写入数据: {namespace}.{key}")
    
    def get(self, key: str, default: Any = None, namespace: str = 'global') -> Any:
        """
        从管道中读取数据
        
        Args:
            key: 数据键名
            default: 默认值
            namespace: 命名空间，默认为 'global'
            
        Returns:
            数据值，如果不存在则返回默认值
        """
        if namespace not in self._data:
            return default
        
        return self._data[namespace].get(key, default)
    
    def has(self, key: str, namespace: str = 'global') -> bool:
        """检查管道中是否存在指定键"""
        if namespace not in self._data:
            return False
        return key in self._data[namespace]
    
    def delete(self, key: str, namespace: str = 'global') -> bool:
        """
        从管道中删除数据
        
        Returns:
            是否成功删除
        """
        if namespace not in self._data:
            return False
        
        if key not in self._data[namespace]:
            return False
        
        old_value = self._data[namespace].pop(key)
        
        # 记录历史
        self._history.append({
            'timestamp': datetime.now().isoformat(),
            'action': 'delete',
            'namespace': namespace,
            'key': key,
            'old_value': old_value
        })
        
        logger.debug(f"Pipeline[{self.pipeline_id}] 删除数据: {namespace}.{key}")
        return True
    
    def get_namespace(self, namespace: str) -> Dict[str, Any]:
        """获取整个命名空间的数据"""
        return self._data.get(namespace, {}).copy()
    
    def clear_namespace(self, namespace: str) -> None:
        """清空指定命名空间的所有数据"""
        if namespace in self._data:
            self._data[namespace].clear()
            logger.debug(f"Pipeline[{self.pipeline_id}] 清空命名空间: {namespace}")
    
    # ========== 节点专用操作 ==========
    
    def put_node(self, node_id: str, key: str, value: Any) -> None:
        """向指定节点的命名空间写入数据"""
        self.put(key, value, namespace=f'node_{node_id}')
    
    def get_node(self, node_id: str, key: str, default: Any = None) -> Any:
        """从指定节点的命名空间读取数据"""
        return self.get(key, default, namespace=f'node_{node_id}')
    
    def get_node_data(self, node_id: str) -> Dict[str, Any]:
        """获取指定节点的所有数据"""
        return self.get_namespace(f'node_{node_id}')
    
    # ========== 文件操作 ==========
    
    def put_file(
        self,
        file_key: str,
        file_path: str,
        file_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        向管道中注册文件
        
        Args:
            file_key: 文件键名
            file_path: 文件路径（绝对路径或相对路径）
            file_type: 文件类型（如 'text', 'image', 'json' 等）
            metadata: 文件元数据
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在: {file_path}")
        
        file_info = {
            'path': str(path.absolute()),
            'type': file_type or self._guess_file_type(file_path),
            'size': path.stat().st_size if path.exists() else 0,
            'metadata': metadata or {},
            'added_at': datetime.now().isoformat()
        }
        
        self._files[file_key] = file_info
        
        # 同时保存到数据中，方便访问
        self.put(f'file_{file_key}', file_info, namespace='files')
        
        logger.debug(f"Pipeline[{self.pipeline_id}] 注册文件: {file_key} -> {file_path}")
    
    def get_file(self, file_key: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        return self._files.get(file_key)
    
    def get_file_path(self, file_key: str) -> Optional[str]:
        """获取文件路径"""
        file_info = self.get_file(file_key)
        return file_info['path'] if file_info else None
    
    def list_files(self) -> List[str]:
        """列出所有文件键名"""
        return list(self._files.keys())
    
    def read_file_content(self, file_key: str, encoding: str = 'utf-8') -> Optional[str]:
        """读取文件内容（文本文件）"""
        file_path = self.get_file_path(file_key)
        if not file_path:
            return None
        
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error(f"读取文件失败 {file_key}: {str(e)}")
            return None
    
    def _guess_file_type(self, file_path: str) -> str:
        """根据文件扩展名猜测文件类型"""
        ext = Path(file_path).suffix.lower()
        type_map = {
            '.txt': 'text',
            '.md': 'markdown',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.py': 'python',
            '.js': 'javascript',
            '.html': 'html',
            '.css': 'css',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.png': 'image',
            '.gif': 'image',
            '.pdf': 'pdf',
            '.doc': 'document',
            '.docx': 'document',
            '.xls': 'spreadsheet',
            '.xlsx': 'spreadsheet',
        }
        return type_map.get(ext, 'unknown')
    
    # ========== 文本操作（便捷方法） ==========
    
    def put_text(self, key: str, text: str, namespace: str = 'global') -> None:
        """写入文本数据"""
        self.put(key, text, namespace=namespace)
    
    def get_text(self, key: str, default: str = '', namespace: str = 'global') -> str:
        """读取文本数据"""
        value = self.get(key, default, namespace=namespace)
        return str(value) if value is not None else default
    
    def append_text(self, key: str, text: str, separator: str = '\n', namespace: str = 'global') -> None:
        """追加文本数据"""
        current = self.get_text(key, namespace=namespace)
        new_text = current + separator + text if current else text
        self.put_text(key, new_text, namespace=namespace)
    
    # ========== JSON 操作（便捷方法） ==========
    
    def put_json(self, key: str, data: Dict[str, Any], namespace: str = 'global') -> None:
        """写入 JSON 数据"""
        self.put(key, data, namespace=namespace)
    
    def get_json(self, key: str, default: Optional[Dict[str, Any]] = None, namespace: str = 'global') -> Dict[str, Any]:
        """读取 JSON 数据"""
        value = self.get(key, default, namespace=namespace)
        if value is None:
            return default or {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except:
                return default or {}
        return default or {}
    
    # ========== 列表操作（便捷方法） ==========
    
    def put_list(self, key: str, items: List[Any], namespace: str = 'global') -> None:
        """写入列表数据"""
        self.put(key, items, namespace=namespace)
    
    def get_list(self, key: str, default: Optional[List[Any]] = None, namespace: str = 'global') -> List[Any]:
        """读取列表数据"""
        value = self.get(key, default, namespace=namespace)
        if value is None:
            return default or []
        if isinstance(value, list):
            return value
        return default or []
    
    def append_list(self, key: str, item: Any, namespace: str = 'global') -> None:
        """向列表追加元素"""
        items = self.get_list(key, namespace=namespace)
        items.append(item)
        self.put_list(key, items, namespace=namespace)
    
    # ========== 历史记录 ==========
    
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取历史记录"""
        history = self._history
        if limit:
            history = history[-limit:]
        return history.copy()
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self._history.clear()
    
    # ========== 导出和导入 ==========
    
    def export(self) -> Dict[str, Any]:
        """导出管道数据（用于持久化或调试）"""
        return {
            'pipeline_id': self.pipeline_id,
            'data': self._data,
            'files': self._files,
            'history_count': len(self._history)
        }
    
    def import_data(self, data: Dict[str, Any]) -> None:
        """导入管道数据"""
        if 'data' in data:
            self._data = data['data']
        if 'files' in data:
            self._files = data['files']
        logger.info(f"Pipeline[{self.pipeline_id}] 导入数据完成")
    
    # ========== 与 flow_state 集成 ==========
    
    @classmethod
    def from_context(cls, context: Dict[str, Any]) -> 'Pipeline':
        """
        从上下文中获取或创建 Pipeline 实例
        
        Args:
            context: 流程上下文字典
            
        Returns:
            Pipeline 实例
        """
        flow_state = context.get('flow_state', {})
        
        # 检查是否已有 pipeline 实例
        if 'pipeline' in flow_state:
            pipeline = flow_state['pipeline']
            if isinstance(pipeline, Pipeline):
                return pipeline
        
        # 创建新的 pipeline 实例
        pipeline = cls()
        flow_state['pipeline'] = pipeline
        
        # 将现有的 flow_state 数据迁移到 pipeline
        if 'data' in flow_state:
            for key, value in flow_state['data'].items():
                pipeline.put(key, value, namespace='global')
        
        return pipeline
    
    def sync_to_flow_state(self, context: Dict[str, Any]) -> None:
        """将 pipeline 数据同步到 flow_state（用于兼容性）"""
        flow_state = context.get('flow_state', {})
        flow_state['pipeline'] = self
        
        # 同步全局数据到 flow_state
        if 'global' in self._data:
            if 'data' not in flow_state:
                flow_state['data'] = {}
            flow_state['data'].update(self._data['global'])
    
    # ========== 工具方法 ==========
    
    def get_all_keys(self, namespace: str = 'global') -> List[str]:
        """获取指定命名空间的所有键名"""
        if namespace not in self._data:
            return []
        return list(self._data[namespace].keys())
    
    def get_all_namespaces(self) -> List[str]:
        """获取所有命名空间"""
        return list(self._data.keys())
    
    def summary(self) -> Dict[str, Any]:
        """获取管道摘要信息"""
        return {
            'pipeline_id': self.pipeline_id,
            'namespaces': self.get_all_namespaces(),
            'total_keys': sum(len(keys) for keys in self._data.values()),
            'total_files': len(self._files),
            'history_count': len(self._history)
        }


# ========== 便捷函数 ==========

def get_pipeline(context: Dict[str, Any]) -> Pipeline:
    """
    从上下文中获取 Pipeline 实例（便捷函数）
    
    Args:
        context: 流程上下文字典
        
    Returns:
        Pipeline 实例
    """
    return Pipeline.from_context(context)

