from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import os
import copy
from pathlib import Path
from utils.log_helper import get_logger

logger = get_logger("pipeline")


class Pipeline:
    """通用流程/智能体上下文管道

    用于在整个系统中存储和共享数据：
    - 支持所有类型智能体（普通聊天、流程图、工具编排等）
    - 支持多种数据类型：文本、文件、JSON、列表等
    - 支持细化的记忆类型：潜意识、长期记忆、短期记忆
    """

    # 记忆类型定义
    MEMORY_TYPE_SUBCONSCIOUS = 'subconscious'  # 潜意识：存在本地，不常用且搜索困难
    MEMORY_TYPE_LONG_TERM = 'long_term'  # 长期记忆：记忆深刻且能通用于整个系统
    MEMORY_TYPE_SHORT_TERM = 'short_term'  # 短期记忆：针对当前任务，容量有限，需要快速更新

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

        # 初始化记忆类型命名空间
        self._data[f'memory_{self.MEMORY_TYPE_SUBCONSCIOUS}'] = {}  # 潜意识记忆
        self._data[f'memory_{self.MEMORY_TYPE_LONG_TERM}'] = {}  # 长期记忆
        self._data[f'memory_{self.MEMORY_TYPE_SHORT_TERM}'] = {}  # 短期记忆

        # 记忆类型配置
        self._memory_config = {
            self.MEMORY_TYPE_SUBCONSCIOUS: {
                'max_size': None,  # 无限制（本地存储）
                'searchable': False,  # 搜索困难
                'persistent': True,  # 持久化
                'access_frequency': 'low'  # 访问频率低
            },
            self.MEMORY_TYPE_LONG_TERM: {
                'max_size': None,  # 无限制（但需要高质量）
                'searchable': True,  # 可搜索
                'persistent': True,  # 持久化
                'access_frequency': 'medium',  # 中等访问频率
                'quality_threshold': 0.7  # 质量阈值（用于筛选）
            },
            self.MEMORY_TYPE_SHORT_TERM: {
                'max_size': 10000,  # 容量有限（字符数或条目数）
                'searchable': True,  # 可快速搜索
                'persistent': False,  # 不持久化（任务结束后清理）
                'access_frequency': 'high',  # 高访问频率
                'update_strategy': 'fifo'  # 更新策略：先进先出
            }
        }

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
            except Exception:
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
    
    def get_all_memory_types(self) -> List[str]:
        """获取所有记忆类型列表"""
        return [
            self.MEMORY_TYPE_SUBCONSCIOUS,
            self.MEMORY_TYPE_LONG_TERM,
            self.MEMORY_TYPE_SHORT_TERM
        ]
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取所有记忆类型的摘要信息
        
        Returns:
            包含每种记忆类型的统计信息和配置的字典
        """
        summary = {}
        for memory_type in self.get_all_memory_types():
            namespace = self.get_memory_namespace(memory_type)
            namespace_data = self.get_namespace(namespace)
            
            # 统计记忆条目数（排除元数据键）
            memory_keys = [k for k in namespace_data.keys() if not k.endswith('_metadata')]
            memory_count = len(memory_keys)
            
            # 计算总大小
            total_size = self._estimate_memory_size(namespace)
            
            # 获取配置
            config = self.get_memory_config(memory_type)
            
            summary[memory_type] = {
                'count': memory_count,
                'size': total_size,
                'namespace': namespace,
                'config': config,
                'keys': memory_keys[:10]  # 只返回前10个键作为预览
            }
        
        return summary
    
    def export_for_frontend(self) -> Dict[str, Any]:
        """导出管道数据为前端需要的格式
        
        注意：会过滤掉不可序列化的对象（如 AgentContext）
        确保所有记忆类型都被包含，即使为空
        """
        import json
        
        # 过滤掉 agent_contexts 命名空间（包含不可序列化的 AgentContext 对象）
        filtered_data = {}
        for namespace, namespace_data in self._data.items():
            if namespace == 'agent_contexts':
                # 跳过 agent_contexts，这是内部使用的，前端不需要
                continue
            filtered_data[namespace] = {}
            for key, value in namespace_data.items():
                try:
                    # 尝试序列化，如果失败则跳过
                    json.dumps(value, default=str)
                    filtered_data[namespace][key] = value
                except (TypeError, ValueError):
                    # 如果无法序列化，转换为字符串表示
                    filtered_data[namespace][key] = str(value)
        
        # 确保所有记忆类型的命名空间都被包含（即使为空）
        for memory_type in self.get_all_memory_types():
            namespace = self.get_memory_namespace(memory_type)
            if namespace not in filtered_data:
                filtered_data[namespace] = {}
        
        # 获取记忆摘要信息
        memory_summary = self.get_memory_summary()
        
        return {
            'pipeline_data': filtered_data,  # 命名空间 -> key -> value
            'pipeline_files': self._files,  # 命名空间 -> key -> file info
            'pipeline_history': self.get_history(limit=100),  # 最近100条历史记录
            'memory_summary': memory_summary  # 记忆类型摘要信息
        }

    def import_data(self, data: Dict[str, Any]) -> None:
        """导入管道数据"""
        if 'data' in data:
            self._data = data['data']
        if 'files' in data:
            self._files = data['files']
        logger.info(f"Pipeline[{self.pipeline_id}] 导入数据完成")

    # ========== 与上下文 / flow_state 集成 ==========

    @classmethod
    def from_context(cls, context: Dict[str, Any]) -> 'Pipeline':
        """
        从上下文中获取或创建 Pipeline 实例

        说明：
        - 设计为**所有类型智能体通用**的上下文管道，而不仅限于流程图智能体
        - 优先使用上下文根级别的 `context['pipeline']`
        - 为兼容历史逻辑，仍然支持从 `context['flow_state']['pipeline']` 读取
        """
        if context is None:
            context = {}

        # 1. 优先：根级别的 pipeline（通用智能体/流程图智能体统一入口）
        existing = context.get('pipeline')
        if isinstance(existing, Pipeline):
            return existing

        # 2. 兼容：从 flow_state 中读取历史 pipeline
        flow_state = context.get('flow_state')
        if isinstance(flow_state, dict):
            legacy_pipeline = flow_state.get('pipeline')
            if isinstance(legacy_pipeline, Pipeline):
                # 同步一份到根级别，后续统一使用 context['pipeline']
                context['pipeline'] = legacy_pipeline
                return legacy_pipeline

        # 3. 创建新的 pipeline 实例
        pipeline = cls()
        context['pipeline'] = pipeline

        # 如果存在 flow_state，迁移其中的 data 到 pipeline（兼容老的 flow_state 结构）
        if isinstance(flow_state, dict):
            if 'data' in flow_state:
                for key, value in flow_state['data'].items():
                    pipeline.put(key, value, namespace='global')

            # 为流程图智能体保留一份引用，避免破坏现有逻辑
            flow_state['pipeline'] = pipeline

        return pipeline

    def sync_to_flow_state(self, context: Dict[str, Any]) -> None:
        """
        将 pipeline 数据同步到上下文与 flow_state（用于兼容性）

        - 始终在根级别写回 `context['pipeline']`，供所有智能体统一使用
        - 如果存在 `flow_state`，同时同步一份到 `flow_state['pipeline']` 和 `flow_state['data']`
        """
        if context is None:
            return

        # 通用入口：根级别 pipeline 引用
        context['pipeline'] = self

        # 兼容流程图智能体使用的 flow_state 结构
        flow_state = context.get('flow_state')
        if isinstance(flow_state, dict):
            flow_state['pipeline'] = self

            # 同步全局数据到 flow_state.data
            if 'global' in self._data:
                if 'data' not in flow_state:
                    flow_state['data'] = {}
                flow_state['data'].update(self._data['global'])

    # ========== 上下文工程 ==========

    # ----- 记忆类型管理 -----

    def get_memory_namespace(self, memory_type: str) -> str:
        """
        获取记忆类型的命名空间

        Args:
            memory_type: 记忆类型（MEMORY_TYPE_SUBCONSCIOUS/LONG_TERM/SHORT_TERM）

        Returns:
            命名空间名称
        """
        return f'memory_{memory_type}'

    def get_memory_config(self, memory_type: str) -> Dict[str, Any]:
        """获取记忆类型的配置"""
        return self._memory_config.get(memory_type, {})

    # ----- 记忆写入（按类型）-----

    def write_to_memory(
        self,
        content: Union[str, Dict[str, Any], List[Any]],
        memory_type: str,
        key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        quality_score: Optional[float] = None
    ) -> str:
        """
        写入到指定类型的记忆

        Args:
            content: 要写入的内容
            memory_type: 记忆类型（MEMORY_TYPE_SUBCONSCIOUS/LONG_TERM/SHORT_TERM）
            key: 数据键名，如果为 None 则自动生成
            metadata: 元数据
            quality_score: 质量分数（0.0-1.0），用于长期记忆筛选

        Returns:
            实际使用的 key
        """
        namespace = self.get_memory_namespace(memory_type)
        config = self.get_memory_config(memory_type)

        if key is None:
            key = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 长期记忆需要质量检查
        if memory_type == self.MEMORY_TYPE_LONG_TERM:
            threshold = config.get('quality_threshold', 0.7)
            if quality_score is None or quality_score < threshold:
                logger.warning(f"长期记忆质量分数 {quality_score} 低于阈值 {threshold}，将降级为潜意识记忆")
                # 降级为潜意识记忆
                return self.write_to_memory(content, self.MEMORY_TYPE_SUBCONSCIOUS, key, metadata, quality_score)

        # 短期记忆容量检查
        if memory_type == self.MEMORY_TYPE_SHORT_TERM:
            max_size = config.get('max_size')
            if max_size:
                current_size = self._estimate_memory_size(namespace)
                content_size = self._estimate_content_size(content)
                if current_size + content_size > max_size:
                    # 触发清理或压缩
                    self._evict_short_term_memory(namespace, target_size=max_size - content_size)

        # 写入内容
        self.put(key, content, namespace=namespace)

        # 存储元数据
        mem_metadata = metadata or {}
        mem_metadata.update({
            'memory_type': memory_type,
            'created_at': datetime.now().isoformat(),
            'quality_score': quality_score
        })
        self.put(f"{key}_metadata", mem_metadata, namespace=namespace)

        logger.debug(f"Pipeline[{self.pipeline_id}] 写入{memory_type}记忆: {key}")
        return key

    def read_from_memory(
        self,
        key: str,
        memory_type: str,
        default: Any = None
    ) -> Any:
        """
        从指定类型的记忆中读取

        Args:
            key: 数据键名
            memory_type: 记忆类型
            default: 默认值

        Returns:
            记忆内容
        """
        namespace = self.get_memory_namespace(memory_type)
        return self.get(key, default, namespace=namespace)

    def search_memory(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索记忆（仅搜索可搜索的记忆类型）

        Args:
            query: 查询字符串
            memory_types: 要搜索的记忆类型列表，如果为 None 则搜索所有可搜索类型
            limit: 返回的最大条目数

        Returns:
            匹配的记忆列表
        """
        if memory_types is None:
            # 只搜索可搜索的记忆类型
            memory_types = [
                self.MEMORY_TYPE_LONG_TERM,
                self.MEMORY_TYPE_SHORT_TERM
            ]

        results = []
        for memory_type in memory_types:
            config = self.get_memory_config(memory_type)
            if not config.get('searchable', False):
                continue

            namespace = self.get_memory_namespace(memory_type)
            namespace_data = self.get_namespace(namespace)

            for key, content in namespace_data.items():
                if key.endswith('_metadata'):
                    continue

                # TODO: 实现语义搜索
                # 简单实现：文本匹配
                if isinstance(content, str) and query.lower() in content.lower():
                    metadata = namespace_data.get(f"{key}_metadata", {})
                    results.append({
                        'key': key,
                        'content': content,
                        'memory_type': memory_type,
                        'metadata': metadata
                    })

        if limit:
            results = results[:limit]

        logger.debug(f"Pipeline[{self.pipeline_id}] 搜索记忆: 找到 {len(results)} 条")
        return results

    def promote_memory(
        self,
        key: str,
        from_type: str,
        to_type: str,
        quality_score: Optional[float] = None
    ) -> bool:
        """
        提升记忆类型（例如：从短期记忆提升到长期记忆）

        Args:
            key: 记忆键名
            from_type: 源记忆类型
            to_type: 目标记忆类型
            quality_score: 质量分数（用于长期记忆）

        Returns:
            是否成功提升
        """
        from_namespace = self.get_memory_namespace(from_type)
        to_namespace = self.get_memory_namespace(to_type)

        content = self.get(key, namespace=from_namespace)
        if content is None:
            return False

        metadata = self.get(f"{key}_metadata", {}, namespace=from_namespace)
        if quality_score:
            metadata['quality_score'] = quality_score

        # 写入到新类型
        self.write_to_memory(content, to_type, key, metadata, quality_score)

        # 从旧类型删除
        self.delete(key, namespace=from_namespace)
        self.delete(f"{key}_metadata", namespace=from_namespace)

        logger.debug(f"Pipeline[{self.pipeline_id}] 提升记忆: {key} ({from_type} -> {to_type})")
        return True

    def demote_memory(
        self,
        key: str,
        from_type: str,
        to_type: str
    ) -> bool:
        """
        降级记忆类型（例如：从长期记忆降级到潜意识）

        Args:
            key: 记忆键名
            from_type: 源记忆类型
            to_type: 目标记忆类型

        Returns:
            是否成功降级
        """
        return self.promote_memory(key, from_type, to_type, quality_score=0.0)

    def clear_short_term_memory(self) -> int:
        """
        清空短期记忆（任务结束后调用）

        Returns:
            清理的条目数
        """
        namespace = self.get_memory_namespace(self.MEMORY_TYPE_SHORT_TERM)
        count = len(self.get_namespace(namespace))
        self.clear_namespace(namespace)
        logger.debug(f"Pipeline[{self.pipeline_id}] 清空短期记忆: {count} 条")
        return count

    def _estimate_memory_size(self, namespace: str) -> int:
        """估算记忆空间大小（字符数）"""
        namespace_data = self.get_namespace(namespace)
        total_size = 0
        for key, value in namespace_data.items():
            if key.endswith('_metadata'):
                continue
            total_size += self._estimate_content_size(value)
        return total_size

    def _estimate_content_size(self, content: Any) -> int:
        """估算内容大小"""
        if isinstance(content, str):
            return len(content)
        elif isinstance(content, (dict, list)):
            return len(json.dumps(content, ensure_ascii=False))
        else:
            return len(str(content))

    def _evict_short_term_memory(self, namespace: str, target_size: int) -> None:
        """
        淘汰短期记忆（FIFO策略）

        Args:
            namespace: 命名空间
            target_size: 目标大小
        """
        namespace_data = self.get_namespace(namespace)
        items = []

        for key, value in namespace_data.items():
            if key.endswith('_metadata'):
                continue
            metadata = namespace_data.get(f"{key}_metadata", {})
            items.append({
                'key': key,
                'content': value,
                'created_at': metadata.get('created_at', ''),
                'size': self._estimate_content_size(value)
            })

        # 按创建时间排序（最早的在前面）
        items.sort(key=lambda x: x['created_at'])

        current_size = self._estimate_memory_size(namespace)
        for item in items:
            if current_size <= target_size:
                break
            self.delete(item['key'], namespace=namespace)
            self.delete(f"{item['key']}_metadata", namespace=namespace)
            current_size -= item['size']

    # ----- 写入（Writing）-----

    def write_context(
        self,
        content: Union[str, Dict[str, Any], List[Any]],
        key: Optional[str] = None,
        namespace: str = 'global',
        priority: int = 0,
        max_size: Optional[int] = None,
        strategy: str = 'append'
    ) -> str:
        """
        智能写入上下文

        Args:
            content: 要写入的内容（文本、字典或列表）
            key: 数据键名，如果为 None 则自动生成
            namespace: 命名空间，默认为 'global'
            priority: 优先级（数字越大优先级越高），用于后续选择时排序
            max_size: 最大上下文大小（字符数或条目数），超出时触发压缩或淘汰
            strategy: 写入策略
                - 'append': 追加到现有内容
                - 'replace': 替换现有内容
                - 'merge': 合并到现有内容（字典/列表）

        Returns:
            实际使用的 key
        """
        # TODO: 实现智能写入逻辑
        # - 根据 max_size 检查是否需要压缩
        # - 根据 priority 管理优先级队列
        # - 根据 strategy 执行不同的写入策略

        if key is None:
            key = f"ctx_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        if strategy == 'append' and isinstance(content, str):
            self.append_text(key, content, namespace=namespace)
        elif strategy == 'merge':
            if isinstance(content, dict):
                existing = self.get_json(key, {}, namespace=namespace)
                existing.update(content)
                self.put_json(key, existing, namespace=namespace)
            elif isinstance(content, list):
                existing = self.get_list(key, [], namespace=namespace)
                existing.extend(content)
                self.put_list(key, existing, namespace=namespace)
            else:
                self.put(key, content, namespace=namespace)
        else:
            self.put(key, content, namespace=namespace)

        # 存储优先级元数据
        self.put(f"{key}_priority", priority, namespace=namespace)
        if max_size:
            self.put(f"{key}_max_size", max_size, namespace=namespace)

        logger.debug(f"Pipeline[{self.pipeline_id}] 写入上下文: {namespace}.{key} (priority={priority})")
        return key

    def write_context_with_metadata(
        self,
        content: Union[str, Dict[str, Any], List[Any]],
        metadata: Dict[str, Any],
        key: Optional[str] = None,
        namespace: str = 'global'
    ) -> str:
        """
        带元数据的上下文写入

        Args:
            content: 要写入的内容
            metadata: 元数据（如：source, timestamp, relevance_score, tags 等）
            key: 数据键名
            namespace: 命名空间

        Returns:
            实际使用的 key
        """
        if key is None:
            key = f"ctx_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        self.put(key, content, namespace=namespace)
        self.put(f"{key}_metadata", metadata, namespace=namespace)

        logger.debug(f"Pipeline[{self.pipeline_id}] 写入上下文（带元数据）: {namespace}.{key}")
        return key

    # ----- 选择（Selection）-----

    def select_context(
        self,
        query: Optional[str] = None,
        namespace: str = 'global',
        limit: Optional[int] = None,
        min_priority: Optional[int] = None,
        tags: Optional[List[str]] = None,
        sort_by: str = 'priority'  # 'priority', 'relevance', 'timestamp'
    ) -> List[Dict[str, Any]]:
        """
        从上下文中选择相关内容

        Args:
            query: 查询字符串，用于语义匹配（TODO: 实现语义搜索）
            namespace: 命名空间
            limit: 返回的最大条目数
            min_priority: 最小优先级阈值
            tags: 标签过滤
            sort_by: 排序方式（'priority', 'relevance', 'timestamp'）

        Returns:
            选中的上下文列表，每个元素包含 {key, content, metadata, priority, ...}
        """
        # TODO: 实现智能选择逻辑
        # - 基于 query 的语义相似度计算
        # - 基于 priority 的优先级排序
        # - 基于 tags 的标签过滤
        # - 基于时间戳的时效性排序

        selected = []
        namespace_data = self.get_namespace(namespace)

        for key, content in namespace_data.items():
            # 跳过元数据键
            if key.endswith('_priority') or key.endswith('_metadata') or key.endswith('_max_size'):
                continue

            # 获取元数据
            priority = namespace_data.get(f"{key}_priority", 0)
            metadata = namespace_data.get(f"{key}_metadata", {})

            # 过滤条件
            if min_priority is not None and priority < min_priority:
                continue

            if tags:
                item_tags = metadata.get('tags', [])
                if not any(tag in item_tags for tag in tags):
                    continue

            selected.append({
                'key': key,
                'content': content,
                'priority': priority,
                'metadata': metadata,
                'namespace': namespace
            })

        # 排序
        if sort_by == 'priority':
            selected.sort(key=lambda x: x.get('priority', 0), reverse=True)
        elif sort_by == 'timestamp':
            selected.sort(key=lambda x: x.get('metadata', {}).get('timestamp', ''), reverse=True)
        # TODO: relevance 排序需要实现语义相似度计算

        if limit:
            selected = selected[:limit]

        logger.debug(f"Pipeline[{self.pipeline_id}] 选择上下文: {len(selected)} 条")
        return selected

    def select_relevant(
        self,
        query: str,
        namespace: str = 'global',
        top_k: int = 5,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        选择与查询最相关的上下文（语义搜索）

        Args:
            query: 查询字符串
            namespace: 命名空间
            top_k: 返回前 K 个最相关的结果
            threshold: 相关性阈值（0.0-1.0），低于此值的结果将被过滤

        Returns:
            最相关的上下文列表，按相关性降序排列
        """
        # TODO: 实现语义相似度计算
        # - 使用 embedding 模型计算 query 和上下文的相似度
        # - 返回 top_k 个最相关的结果

        logger.debug(f"Pipeline[{self.pipeline_id}] 语义选择上下文: query='{query}', top_k={top_k}")
        # 占位实现：返回空列表
        return []

    # ----- 压缩（Compression）-----

    def compress_context(
        self,
        namespace: str = 'global',
        target_size: Optional[int] = None,
        strategy: str = 'summarize'  # 'summarize', 'remove_low_priority', 'merge_similar'
    ) -> Dict[str, Any]:
        """
        压缩上下文，保留关键信息

        Args:
            namespace: 命名空间
            target_size: 目标大小（字符数或条目数）
            strategy: 压缩策略
                - 'summarize': 使用 LLM 总结上下文
                - 'remove_low_priority': 移除低优先级内容
                - 'merge_similar': 合并相似内容

        Returns:
            压缩结果统计 {original_size, compressed_size, removed_keys, ...}
        """
        # TODO: 实现上下文压缩逻辑
        # - 使用 LLM 总结长文本
        # - 移除低优先级或过时的内容
        # - 合并语义相似的内容

        original_size = len(self.get_namespace(namespace))
        logger.debug(f"Pipeline[{self.pipeline_id}] 压缩上下文: {namespace} (strategy={strategy})")

        if strategy == 'remove_low_priority':
            # 简单实现：移除优先级为 0 或负数的内容
            namespace_data = self.get_namespace(namespace)
            removed_keys = []
            for key in list(namespace_data.keys()):
                if key.endswith('_priority') or key.endswith('_metadata'):
                    continue
                priority = namespace_data.get(f"{key}_priority", 0)
                if priority <= 0:
                    self.delete(key, namespace=namespace)
                    removed_keys.append(key)

            compressed_size = len(self.get_namespace(namespace))
            return {
                'original_size': original_size,
                'compressed_size': compressed_size,
                'removed_keys': removed_keys,
                'strategy': strategy
            }

        # 其他策略的占位实现
        return {
            'original_size': original_size,
            'compressed_size': original_size,
            'removed_keys': [],
            'strategy': strategy,
            'note': '策略未实现'
        }

    def summarize_context(
        self,
        keys: Optional[List[str]] = None,
        namespace: str = 'global',
        max_length: Optional[int] = None
    ) -> str:
        """
        总结上下文内容

        Args:
            keys: 要总结的键列表，如果为 None 则总结整个命名空间
            namespace: 命名空间
            max_length: 总结的最大长度（字符数）

        Returns:
            总结文本
        """
        # TODO: 使用 LLM 生成上下文总结
        # - 收集所有相关上下文
        # - 调用 LLM 生成总结
        # - 返回压缩后的总结文本

        if keys is None:
            namespace_data = self.get_namespace(namespace)
            keys = [k for k in namespace_data.keys() if not k.endswith('_priority') and not k.endswith('_metadata')]

        contents = []
        for key in keys:
            content = self.get(key, namespace=namespace)
            if isinstance(content, str):
                contents.append(content)
            elif isinstance(content, (dict, list)):
                contents.append(json.dumps(content, ensure_ascii=False))

        summary = "\n\n".join(contents)
        if max_length and len(summary) > max_length:
            summary = summary[:max_length] + "..."

        logger.debug(f"Pipeline[{self.pipeline_id}] 总结上下文: {len(keys)} 个键")
        return summary

    # ----- 隔离（Isolation）-----

    def create_isolated_context(
        self,
        context_id: str,
        parent_namespace: Optional[str] = None
    ) -> str:
        """
        创建隔离的上下文空间

        Args:
            context_id: 上下文空间标识符
            parent_namespace: 父命名空间，如果提供则继承父空间的数据

        Returns:
            创建的命名空间名称
        """
        namespace = f"isolated_{context_id}"

        if namespace not in self._data:
            self._data[namespace] = {}

        # 如果指定了父命名空间，复制其数据（但不共享引用）
        if parent_namespace:
            parent_data = self.get_namespace(parent_namespace)
            for key, value in parent_data.items():
                # 深拷贝避免引用共享
                if isinstance(value, (dict, list)):
                    self._data[namespace][key] = copy.deepcopy(value)
                else:
                    self._data[namespace][key] = value

        logger.debug(f"Pipeline[{self.pipeline_id}] 创建隔离上下文: {namespace}")
        return namespace

    def switch_context(
        self,
        context_id: str,
        namespace: str = 'global'
    ) -> str:
        """
        切换到指定的上下文空间（实际上是创建或获取隔离空间）

        Args:
            context_id: 上下文空间标识符
            namespace: 当前命名空间（用于继承数据）

        Returns:
            切换到的命名空间名称
        """
        isolated_namespace = f"isolated_{context_id}"

        if isolated_namespace not in self._data:
            return self.create_isolated_context(context_id, parent_namespace=namespace)

        logger.debug(f"Pipeline[{self.pipeline_id}] 切换到上下文: {isolated_namespace}")
        return isolated_namespace

    def merge_context(
        self,
        source_namespace: str,
        target_namespace: str = 'global',
        strategy: str = 'merge'  # 'merge', 'replace', 'append'
    ) -> Dict[str, Any]:
        """
        合并上下文空间

        Args:
            source_namespace: 源命名空间
            target_namespace: 目标命名空间
            strategy: 合并策略
                - 'merge': 合并数据（字典合并，列表扩展）
                - 'replace': 替换目标空间的数据
                - 'append': 追加到目标空间（键名添加前缀）

        Returns:
            合并结果统计
        """
        source_data = self.get_namespace(source_namespace)
        target_data = self.get_namespace(target_namespace)

        merged_count = 0
        replaced_count = 0

        for key, value in source_data.items():
            if key.endswith('_priority') or key.endswith('_metadata'):
                continue

            if strategy == 'replace':
                self.put(key, value, namespace=target_namespace)
                replaced_count += 1
            elif strategy == 'merge':
                existing = target_data.get(key)
                if isinstance(value, dict) and isinstance(existing, dict):
                    existing.update(value)
                    self.put(key, existing, namespace=target_namespace)
                elif isinstance(value, list) and isinstance(existing, list):
                    existing.extend(value)
                    self.put(key, existing, namespace=target_namespace)
                else:
                    self.put(key, value, namespace=target_namespace)
                merged_count += 1
            elif strategy == 'append':
                new_key = f"{source_namespace}_{key}"
                self.put(new_key, value, namespace=target_namespace)
                merged_count += 1

        logger.debug(f"Pipeline[{self.pipeline_id}] 合并上下文: {source_namespace} -> {target_namespace}")
        return {
            'source_namespace': source_namespace,
            'target_namespace': target_namespace,
            'merged_count': merged_count,
            'replaced_count': replaced_count,
            'strategy': strategy
        }

    def list_isolated_contexts(self) -> List[str]:
        """
        列出所有隔离的上下文空间

        Returns:
            隔离上下文空间列表
        """
        isolated = []
        for namespace in self.get_all_namespaces():
            if namespace.startswith('isolated_'):
                isolated.append(namespace)
        return isolated

    def delete_isolated_context(self, context_id: str) -> bool:
        """
        删除隔离的上下文空间

        Args:
            context_id: 上下文空间标识符

        Returns:
            是否成功删除
        """
        namespace = f"isolated_{context_id}"
        if namespace in self._data:
            self.clear_namespace(namespace)
            del self._data[namespace]
            logger.debug(f"Pipeline[{self.pipeline_id}] 删除隔离上下文: {namespace}")
            return True
        return False


# ========== 便捷函数 ==========

def get_pipeline(context: Dict[str, Any]) -> Pipeline:
    """
    从上下文中获取 Pipeline 实例（便捷函数）

    Args:
        context: 上下文字典（适用于所有智能体）

    Returns:
        Pipeline 实例
    """
    return Pipeline.from_context(context)


__all__ = ["Pipeline", "get_pipeline"]


