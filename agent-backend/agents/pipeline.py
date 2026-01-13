from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import json
import os
import copy
from pathlib import Path
from utils.log_helper import get_logger
from utils.llm_helper import get_llm_helper

logger = get_logger("pipeline")


class Pipeline:
    """通用流程/智能体上下文管道

    用于在整个系统中存储和共享数据：
    - 支持所有类型智能体（普通聊天、流程图、工具编排等）
    - 支持多种数据类型：文本、文件、JSON、列表等
    - 支持三维数据组织：用户、话题、智能体
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

        # 数据存储：按三维组织（用户、话题、智能体）
        # 结构：{user_id: {topic_id: {agent_id: {key: value}}}}
        self._data_3d: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}

        # 兼容旧版本：按命名空间组织（向后兼容）
        # 结构：{namespace: {key: value}}
        self._data: Dict[str, Dict[str, Any]] = {}

        # 文件存储：存储文件路径和元数据
        # 结构：{file_key: {'path': str, 'type': str, 'size': int, 'metadata': dict}}
        self._files: Dict[str, Dict[str, Any]] = {}

        # 历史记录：记录数据变更历史
        self._history: List[Dict[str, Any]] = []

        # 默认维度值
        self._default_user_id = 'default_user'
        self._default_topic_id = 'default_topic'
        self._default_agent_id = 'default_agent'

        # 初始化默认命名空间（向后兼容）
        self._data['global'] = {}
        self._data['nodes'] = {}  # 节点专用命名空间

    # ========== 基础数据操作 ==========

    def _get_dimensions_from_context(self, context: Optional[Dict[str, Any]] = None) -> tuple[str, str, str]:
        """
        从上下文中提取三维信息（用户、话题、智能体）
        
        Args:
            context: 上下文字典
            
        Returns:
            (user_id, topic_id, agent_id)
        """
        if context is None:
            return self._default_user_id, self._default_topic_id, self._default_agent_id
        
        user_id = context.get('user_id') or context.get('user') or self._default_user_id
        topic_id = context.get('topic_id') or context.get('topic') or context.get('session_id') or self._default_topic_id
        agent_id = context.get('agent_id') or context.get('agent_name') or context.get('agent') or self._default_agent_id
        
        return str(user_id), str(topic_id), str(agent_id)

    def put(
        self, 
        key: str, 
        value: Any, 
        namespace: str = 'global',
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        向管道中写入数据（支持三维和命名空间两种模式）

        Args:
            key: 数据键名
            value: 数据值（可以是任何类型）
            namespace: 命名空间，默认为 'global'（向后兼容）
            user_id: 用户ID（三维模式）
            topic_id: 话题ID（三维模式）
            agent_id: 智能体ID（三维模式）
            context: 上下文字典（用于自动提取维度信息）
        """
        # 如果提供了三维参数或 context，使用三维存储
        if user_id is not None or topic_id is not None or agent_id is not None or context is not None:
            if user_id is None or topic_id is None or agent_id is None:
                # 从 context 中提取缺失的维度
                ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
                user_id = user_id or ctx_user
                topic_id = topic_id or ctx_topic
                agent_id = agent_id or ctx_agent
            
            # 三维存储
            if user_id not in self._data_3d:
                self._data_3d[user_id] = {}
            if topic_id not in self._data_3d[user_id]:
                self._data_3d[user_id][topic_id] = {}
            if agent_id not in self._data_3d[user_id][topic_id]:
                self._data_3d[user_id][topic_id][agent_id] = {}
            
            old_value = self._data_3d[user_id][topic_id][agent_id].get(key)
            self._data_3d[user_id][topic_id][agent_id][key] = value
            
            # 记录历史
            self._history.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'put',
                'user_id': user_id,
                'topic_id': topic_id,
                'agent_id': agent_id,
                'key': key,
                'old_value': old_value,
                'new_value': value
            })
            
            logger.debug(f"Pipeline[{self.pipeline_id}] 写入数据（三维）: {user_id}.{topic_id}.{agent_id}.{key}")
        else:
            # 向后兼容：使用命名空间存储
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

    def get(
        self, 
        key: str, 
        default: Any = None, 
        namespace: str = 'global',
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        从管道中读取数据（支持三维和命名空间两种模式）

        Args:
            key: 数据键名
            default: 默认值
            namespace: 命名空间，默认为 'global'（向后兼容）
            user_id: 用户ID（三维模式）
            topic_id: 话题ID（三维模式）
            agent_id: 智能体ID（三维模式）
            context: 上下文字典（用于自动提取维度信息）

        Returns:
            数据值，如果不存在则返回默认值
        """
        # 如果提供了三维参数或 context，使用三维读取
        if user_id is not None or topic_id is not None or agent_id is not None or context is not None:
            if user_id is None or topic_id is None or agent_id is None:
                # 从 context 中提取缺失的维度
                ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
                user_id = user_id or ctx_user
                topic_id = topic_id or ctx_topic
                agent_id = agent_id or ctx_agent
            
            # 三维读取
            if user_id not in self._data_3d:
                return default
            if topic_id not in self._data_3d[user_id]:
                return default
            if agent_id not in self._data_3d[user_id][topic_id]:
                return default
            
            return self._data_3d[user_id][topic_id][agent_id].get(key, default)
        else:
            # 向后兼容：使用命名空间读取
            if namespace not in self._data:
                return default

            return self._data[namespace].get(key, default)

    def has(
        self, 
        key: str, 
        namespace: str = 'global',
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """检查管道中是否存在指定键"""
        # 如果提供了三维参数或 context，使用三维检查
        if user_id is not None or topic_id is not None or agent_id is not None or context is not None:
            if user_id is None or topic_id is None or agent_id is None:
                ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
                user_id = user_id or ctx_user
                topic_id = topic_id or ctx_topic
                agent_id = agent_id or ctx_agent
            
            if user_id not in self._data_3d:
                return False
            if topic_id not in self._data_3d[user_id]:
                return False
            if agent_id not in self._data_3d[user_id][topic_id]:
                return False
            return key in self._data_3d[user_id][topic_id][agent_id]
        else:
            # 向后兼容
            if namespace not in self._data:
                return False
            return key in self._data[namespace]

    def delete(
        self, 
        key: str, 
        namespace: str = 'global',
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从管道中删除数据

        Returns:
            是否成功删除
        """
        # 如果提供了三维参数或 context，使用三维删除
        if user_id is not None or topic_id is not None or agent_id is not None or context is not None:
            if user_id is None or topic_id is None or agent_id is None:
                ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
                user_id = user_id or ctx_user
                topic_id = topic_id or ctx_topic
                agent_id = agent_id or ctx_agent
            
            if user_id not in self._data_3d:
                return False
            if topic_id not in self._data_3d[user_id]:
                return False
            if agent_id not in self._data_3d[user_id][topic_id]:
                return False
            if key not in self._data_3d[user_id][topic_id][agent_id]:
                return False

            old_value = self._data_3d[user_id][topic_id][agent_id].pop(key)

            # 记录历史
            self._history.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'delete',
                'user_id': user_id,
                'topic_id': topic_id,
                'agent_id': agent_id,
                'key': key,
                'old_value': old_value
            })

            logger.debug(f"Pipeline[{self.pipeline_id}] 删除数据（三维）: {user_id}.{topic_id}.{agent_id}.{key}")
            return True
        else:
            # 向后兼容
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
        """获取整个命名空间的数据（向后兼容）"""
        return self._data.get(namespace, {}).copy()
    
    def get_3d_data(
        self,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        获取三维数据（用户、话题、智能体）
        
        Args:
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）
            
        Returns:
            该三维空间下的所有数据
        """
        if user_id is None or topic_id is None or agent_id is None:
            ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
            user_id = user_id or ctx_user
            topic_id = topic_id or ctx_topic
            agent_id = agent_id or ctx_agent
        
        if user_id not in self._data_3d:
            return {}
        if topic_id not in self._data_3d[user_id]:
            return {}
        if agent_id not in self._data_3d[user_id][topic_id]:
            return {}
        
        return self._data_3d[user_id][topic_id][agent_id].copy()

    def clear_namespace(self, namespace: str) -> None:
        """清空指定命名空间的所有数据（向后兼容）"""
        if namespace in self._data:
            self._data[namespace].clear()
            logger.debug(f"Pipeline[{self.pipeline_id}] 清空命名空间: {namespace}")
    
    def clear_3d_data(
        self,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        清空三维数据（用户、话题、智能体）
        
        Args:
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）
        """
        if user_id is None or topic_id is None or agent_id is None:
            ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
            user_id = user_id or ctx_user
            topic_id = topic_id or ctx_topic
            agent_id = agent_id or ctx_agent
        
        if user_id in self._data_3d:
            if topic_id in self._data_3d[user_id]:
                if agent_id in self._data_3d[user_id][topic_id]:
                    self._data_3d[user_id][topic_id][agent_id].clear()
                    logger.debug(f"Pipeline[{self.pipeline_id}] 清空三维数据: {user_id}.{topic_id}.{agent_id}")

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
            'data': self._data,  # 向后兼容的命名空间数据
            'data_3d': self._data_3d,  # 三维数据
            'files': self._files,
            'history_count': len(self._history)
        }
    
    
    def export_for_frontend(self) -> Dict[str, Any]:
        """导出管道数据为前端需要的格式
        
        注意：会过滤掉不可序列化的对象（如 AgentContext）
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
        
        # 过滤三维数据（同样处理不可序列化对象）
        filtered_data_3d = {}
        for user_id, user_data in self._data_3d.items():
            filtered_data_3d[user_id] = {}
            for topic_id, topic_data in user_data.items():
                filtered_data_3d[user_id][topic_id] = {}
                for agent_id, agent_data in topic_data.items():
                    filtered_data_3d[user_id][topic_id][agent_id] = {}
                    for key, value in agent_data.items():
                        try:
                            json.dumps(value, default=str)
                            filtered_data_3d[user_id][topic_id][agent_id][key] = value
                        except (TypeError, ValueError):
                            filtered_data_3d[user_id][topic_id][agent_id][key] = str(value)
        
        return {
            'pipeline_data': filtered_data,  # 命名空间 -> key -> value（向后兼容）
            'pipeline_data_3d': filtered_data_3d,  # 三维数据：user_id -> topic_id -> agent_id -> key -> value
            'pipeline_files': self._files,  # 命名空间 -> key -> file info
            'pipeline_history': self.get_history(limit=100)  # 最近100条历史记录
        }

    def import_data(self, data: Dict[str, Any]) -> None:
        """导入管道数据"""
        if 'data' in data:
            self._data = data['data']
        if 'data_3d' in data:
            self._data_3d = data['data_3d']
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

    # ----- 记忆写入（简化版，直接使用三维存储）-----

    def write_to_memory(
        self,
        content: Union[str, Dict[str, Any], List[Any]],
        key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        写入记忆（使用三维存储）

        Args:
            content: 要写入的内容
            key: 数据键名，如果为 None 则自动生成
            metadata: 元数据
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）

        Returns:
            实际使用的 key
        """
        # 从 context 中提取缺失的维度
        if user_id is None or topic_id is None or agent_id is None:
            ctx_user, ctx_topic, ctx_agent = self._get_dimensions_from_context(context)
            user_id = user_id or ctx_user
            topic_id = topic_id or ctx_topic
            agent_id = agent_id or ctx_agent

        if key is None:
            key = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # 写入内容
        self.put(key, content, user_id=user_id, topic_id=topic_id, agent_id=agent_id, context=context)

        # 存储元数据
        if metadata:
            mem_metadata = metadata.copy()
            mem_metadata['created_at'] = datetime.now().isoformat()
            self.put(f"{key}_metadata", mem_metadata, user_id=user_id, topic_id=topic_id, agent_id=agent_id, context=context)

        logger.debug(f"Pipeline[{self.pipeline_id}] 写入记忆: {user_id}.{topic_id}.{agent_id}.{key}")
        return key

    def read_from_memory(
        self,
        key: str,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        default: Any = None
    ) -> Any:
        """
        从记忆中读取

        Args:
            key: 数据键名
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）
            default: 默认值

        Returns:
            记忆内容
        """
        return self.get(key, default, user_id=user_id, topic_id=topic_id, agent_id=agent_id, context=context)

    def search_memory(
        self,
        query: str,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索记忆

        Args:
            query: 查询字符串
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）
            limit: 返回的最大条目数

        Returns:
            匹配的记忆列表
        """
        data = self.get_3d_data(user_id, topic_id, agent_id, context)
        results = []

        for key, content in data.items():
            if key.endswith('_metadata'):
                continue

            # TODO: 实现语义搜索
            # 简单实现：文本匹配
            if isinstance(content, str) and query.lower() in content.lower():
                metadata = data.get(f"{key}_metadata", {})
                results.append({
                    'key': key,
                    'content': content,
                    'metadata': metadata
                })

        if limit:
            results = results[:limit]

        logger.debug(f"Pipeline[{self.pipeline_id}] 搜索记忆: 找到 {len(results)} 条")
        return results

    def _estimate_memory_size(
        self,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """估算记忆空间大小（字符数）"""
        data = self.get_3d_data(user_id, topic_id, agent_id, context)
        total_size = 0
        for key, value in data.items():
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

    def clear_memory(
        self,
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        清空指定三维空间的记忆

        Args:
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典（用于自动提取维度信息）

        Returns:
            清理的条目数
        """
        data = self.get_3d_data(user_id, topic_id, agent_id, context)
        count = len([k for k in data.keys() if not k.endswith('_metadata')])
        self.clear_3d_data(user_id, topic_id, agent_id, context)
        logger.debug(f"Pipeline[{self.pipeline_id}] 清空记忆: {count} 条")
        return count

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
    
    # ========== 三维数据查询方法 ==========
    
    def list_users(self) -> List[str]:
        """列出所有用户ID"""
        return list(self._data_3d.keys())
    
    def list_topics(self, user_id: Optional[str] = None) -> List[str]:
        """列出话题ID
        
        Args:
            user_id: 用户ID，如果为 None 则返回所有用户的话题
        """
        if user_id:
            if user_id in self._data_3d:
                return list(self._data_3d[user_id].keys())
            return []
        else:
            topics = set()
            for user_data in self._data_3d.values():
                topics.update(user_data.keys())
            return list(topics)
    
    def list_agents(
        self, 
        user_id: Optional[str] = None,
        topic_id: Optional[str] = None
    ) -> List[str]:
        """列出智能体ID
        
        Args:
            user_id: 用户ID，如果为 None 则返回所有用户的智能体
            topic_id: 话题ID，如果为 None 则返回所有话题的智能体
        """
        if user_id and topic_id:
            if user_id in self._data_3d and topic_id in self._data_3d[user_id]:
                return list(self._data_3d[user_id][topic_id].keys())
            return []
        elif user_id:
            agents = set()
            if user_id in self._data_3d:
                for topic_data in self._data_3d[user_id].values():
                    agents.update(topic_data.keys())
            return list(agents)
        else:
            agents = set()
            for user_data in self._data_3d.values():
                for topic_data in user_data.values():
                    agents.update(topic_data.keys())
            return list(agents)
    
    def get_all_namespaces(self) -> List[str]:
        """获取所有命名空间（向后兼容）"""
        return list(self._data.keys())

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

    # ========== 三维信息提取（通过 LLM 提示词） ==========
    
    async def extract_user_knowledge(
        self,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 200,
        llm_helper = None
    ) -> str:
        """
        提取用户维度的知识（用户偏好、习惯、特征等）
        
        原则：用最少的 token 记录最大信息密度的知识
        
        Args:
            user_id: 用户ID
            context: 上下文字典
            max_tokens: 最大 token 数（目标压缩后的大小）
            llm_helper: LLM 助手实例，如果为 None 则使用默认实例
            
        Returns:
            压缩后的用户知识（高信息密度）
        """
        # 收集该用户在所有话题和智能体下的数据
        user_data_list = []
        if user_id in self._data_3d:
            for topic_id, topic_data in self._data_3d[user_id].items():
                for agent_id, agent_data in topic_data.items():
                    for key, value in agent_data.items():
                        if key.endswith('_metadata'):
                            continue
                        value_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                        user_data_list.append(f"{key}: {value_str}")
        
        if not user_data_list:
            return ""
        
        # 合并原始数据
        raw_content = "\n".join(user_data_list)
        
        # 使用 LLM 提炼用户知识
        system_prompt = """你是一个知识压缩专家。你的任务是从对话和交互数据中提取用户的特征、偏好和习惯。

提取原则：
1. 只提取可复用的、跨话题的用户特征（如：偏好简洁回答、喜欢技术细节、习惯用英文等）
2. 使用最简洁的语言，去除冗余和重复
3. 用关键词和短语，而非完整句子
4. 信息密度最大化，token 数最小化
5. 格式：用分号分隔的短语，如"偏好简洁回答;喜欢技术细节;习惯用英文"

输出要求：
- 只输出提炼后的知识，不要解释
- 如果信息不足，输出空字符串
- 目标：用 50-200 token 记录最大信息量"""

        user_prompt = f"""请从以下数据中提取用户特征和偏好（跨话题的通用特征）：

{raw_content}

请用最简洁的方式提炼用户知识（目标：{max_tokens} token以内）。"""

        try:
            if llm_helper is None:
                llm_helper = get_llm_helper()
            
            response = await llm_helper.call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # 低温度确保输出稳定
                max_tokens=max_tokens * 2  # 给 LLM 一些缓冲
            )
            
            # 清理响应（去除可能的解释性文字）
            knowledge = response.strip()
            # 如果响应包含"提炼"、"总结"等词，可能是解释，尝试提取核心内容
            if "：" in knowledge or ":" in knowledge:
                lines = knowledge.split('\n')
                # 取最后一行或包含实际内容的部分
                knowledge = lines[-1] if lines else knowledge
            
            logger.debug(f"Pipeline[{self.pipeline_id}] 提取用户知识: {user_id} -> {len(knowledge)} 字符")
            return knowledge
        except Exception as e:
            logger.error(f"Pipeline[{self.pipeline_id}] 提取用户知识失败: {e}")
            # 降级：简单截取
            return raw_content[:max_tokens * 3] if len(raw_content) > max_tokens * 3 else raw_content
    
    async def extract_topic_knowledge(
        self,
        user_id: str,
        context: Optional[Dict[str, Any]] = None,
        max_topics: int = 10,
        llm_helper = None
    ) -> List[str]:
        """
        从对话内容中提取话题列表（如：星座、编程、性格等）
        
        原则：用最少的 token 记录最大信息密度的知识
        
        Args:
            user_id: 用户ID
            context: 上下文字典
            max_topics: 最大话题数量
            llm_helper: LLM 助手实例，如果为 None 则使用默认实例
            
        Returns:
            话题列表（已合并相似话题）
        """
        # 收集该用户所有话题下的对话数据
        all_conversations = []
        if user_id in self._data_3d:
            for topic_id, topic_data in self._data_3d[user_id].items():
                for agent_id, agent_data in topic_data.items():
                    for key, value in agent_data.items():
                        if key.endswith('_metadata'):
                            continue
                        # 提取对话相关的内容
                        value_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                        # 过滤掉太短的内容，保留所有对话相关内容
                        if len(value_str) > 10:
                            # 优先提取包含对话关键词的内容
                            if '用户' in value_str or '助手' in value_str or '消息' in value_str or '回复' in value_str or '对话' in value_str:
                                all_conversations.append(value_str)
                            # 也包含其他较长的文本内容（可能是对话的一部分）
                            elif len(value_str) > 50:
                                all_conversations.append(value_str)
        
        if not all_conversations:
            return []
        
        # 合并对话内容（限制长度，避免超出 token 限制）
        max_content_length = 5000  # 限制总长度
        raw_content = "\n".join(all_conversations)
        if len(raw_content) > max_content_length:
            raw_content = raw_content[:max_content_length] + "..."
        
        # 使用 LLM 识别和提取话题
        system_prompt = """你是一个话题识别专家。你的任务是从对话内容中识别出用户讨论的话题。

识别原则：
1. 识别对话中涉及的主要话题（如：星座、编程、性格、健康、工作、学习等）
2. 合并相似话题（如："Python编程"和"编程"合并为"编程"）
3. 只提取明确讨论的话题，忽略闲聊和无关内容
4. 话题名称要简洁（1-4个字）
5. 按话题出现频率或重要性排序

输出格式（JSON）：
{
    "topics": ["话题1", "话题2", "话题3", ...]
}

要求：
- topics 是一个字符串数组
- 每个话题是简洁的中文名称（1-4个字）
- 已合并相似话题
- 最多返回 10 个话题
- 只输出 JSON，不要其他解释"""

        user_prompt = f"""请从以下对话内容中识别并提取话题：

{raw_content}

请识别出用户讨论的主要话题，合并相似话题，返回 JSON 格式的话题列表（最多 {max_topics} 个）。"""

        try:
            if llm_helper is None:
                llm_helper = get_llm_helper()
            
            response = await llm_helper.call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            # 解析 JSON 响应
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                topics = result.get('topics', [])
                
                # 验证和清理话题列表
                topics = [t.strip() for t in topics if isinstance(t, str) and len(t.strip()) > 0]
                topics = topics[:max_topics]  # 限制数量
                
                logger.debug(f"Pipeline[{self.pipeline_id}] 提取话题列表: {user_id} -> {len(topics)} 个话题: {topics}")
                return topics
            else:
                # 如果无法解析 JSON，尝试提取话题关键词
                logger.warning(f"Pipeline[{self.pipeline_id}] 无法解析话题 JSON，尝试提取关键词")
                # 简单降级：返回空列表
                return []
        except Exception as e:
            logger.error(f"Pipeline[{self.pipeline_id}] 提取话题列表失败: {e}")
            return []
    
    async def extract_agent_knowledge(
        self,
        user_id: str,
        topic_id: str,
        agent_id: str,
        context: Optional[Dict[str, Any]] = None,
        max_tokens: int = 300,
        llm_helper = None
    ) -> str:
        """
        提取智能体维度的知识（提炼的聊天内容、关键对话等）
        
        原则：用最少的 token 记录最大信息密度的知识
        
        Args:
            user_id: 用户ID
            topic_id: 话题ID
            agent_id: 智能体ID
            context: 上下文字典
            max_tokens: 最大 token 数（目标压缩后的大小）
            llm_helper: LLM 助手实例，如果为 None 则使用默认实例
            
        Returns:
            压缩后的智能体知识（高信息密度）
        """
        # 收集该智能体的所有数据
        agent_data_list = []
        if user_id in self._data_3d and topic_id in self._data_3d[user_id] and agent_id in self._data_3d[user_id][topic_id]:
            agent_data = self._data_3d[user_id][topic_id][agent_id]
            for key, value in agent_data.items():
                if key.endswith('_metadata'):
                    continue
                value_str = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                agent_data_list.append(f"{key}: {value_str}")
        
        if not agent_data_list:
            return ""
        
        # 合并原始数据
        raw_content = "\n".join(agent_data_list)
        
        # 使用 LLM 提炼智能体知识
        system_prompt = """你是一个知识压缩专家。你的任务是从对话和交互数据中提取智能体的关键输出和提炼内容。

提取原则：
1. 提取智能体的关键回复、重要信息和有价值的内容
2. 去除闲聊、重复和无关内容
3. 保留核心知识点、解决方案、重要结论
4. 使用最简洁的语言，信息密度最大化
5. 格式：简洁的提炼内容，用分号或换行分隔要点

输出要求：
- 只输出提炼后的知识，不要解释
- 如果信息不足，输出空字符串
- 目标：用 100-300 token 记录关键内容"""

        user_prompt = f"""请从以下数据中提取智能体"{agent_id}"的关键内容：

{raw_content}

请用最简洁的方式提炼智能体知识（目标：{max_tokens} token以内）。"""

        try:
            if llm_helper is None:
                llm_helper = get_llm_helper()
            
            response = await llm_helper.call(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=max_tokens * 2
            )
            
            knowledge = response.strip()
            # 清理响应
            if "：" in knowledge or ":" in knowledge:
                lines = knowledge.split('\n')
                knowledge = "\n".join([line for line in lines if not line.startswith("提炼") and not line.startswith("总结")])
            
            logger.debug(f"Pipeline[{self.pipeline_id}] 提取智能体知识: {user_id}.{topic_id}.{agent_id} -> {len(knowledge)} 字符")
            return knowledge
        except Exception as e:
            logger.error(f"Pipeline[{self.pipeline_id}] 提取智能体知识失败: {e}")
            # 降级：简单截取
            return raw_content[:max_tokens * 3] if len(raw_content) > max_tokens * 3 else raw_content
    
    async def extract_all_dimensions(
        self,
        user_id: str,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        llm_helper = None
    ) -> Dict[str, Any]:
        """
        一次性提取所有三维信息
        
        Args:
            user_id: 用户ID
            topic_id: 话题ID（可选，已废弃，现在从对话中自动提取话题）
            agent_id: 智能体ID（可选，如果为 None 则提取所有智能体）
            context: 上下文字典
            llm_helper: LLM 助手实例
            
        Returns:
            {
                'user': '用户知识',
                'topics': ['话题1', '话题2', ...],  # 话题列表（从对话中提取）
                'agents': {'agent1': '智能体知识1', 'agent2': '智能体知识2'}
            }
        """
        result = {
            'user': '',
            'topics': [],
            'agents': {}
        }
        
        # 提取用户知识
        result['user'] = await self.extract_user_knowledge(user_id, context, llm_helper=llm_helper)
        
        # 从对话内容中提取话题列表（自动识别和合并相似话题）
        result['topics'] = await self.extract_topic_knowledge(user_id, context, llm_helper=llm_helper)
        
        # 提取智能体知识（基于实际存在的 topic_id 和 agent_id）
        # 由于话题现在是列表，我们需要遍历所有实际的话题ID
        actual_topics = self.list_topics(user_id) if user_id in self._data_3d else []
        
        if topic_id and topic_id in actual_topics:
            # 如果指定了 topic_id，只提取该话题下的智能体
            if agent_id:
                agents = [(topic_id, agent_id)]
            else:
                agents = [(topic_id, a_id) for a_id in self.list_agents(user_id, topic_id)]
        else:
            # 提取所有话题下的智能体
            agents = []
            for t_id in actual_topics:
                for a_id in self.list_agents(user_id, t_id):
                    agents.append((t_id, a_id))
        
        for t_id, a_id in agents:
            result['agents'][f"{t_id}.{a_id}"] = await self.extract_agent_knowledge(user_id, t_id, a_id, context, llm_helper=llm_helper)
        
        return result
    
    async def extract_and_store_dimensions(
        self,
        user_id: str,
        topic_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        llm_helper = None,
        auto_store: bool = True
    ) -> Dict[str, str]:
        """
        提取并存储三维信息
        
        Args:
            user_id: 用户ID
            topic_id: 话题ID（可选）
            agent_id: 智能体ID（可选）
            context: 上下文字典
            llm_helper: LLM 助手实例
            auto_store: 是否自动存储到 Pipeline
            
        Returns:
            提取的知识字典
        """
        # 提取知识
        knowledge = await self.extract_all_dimensions(
            user_id=user_id,
            topic_id=topic_id,
            agent_id=agent_id,
            context=context,
            llm_helper=llm_helper
        )
        
        # 自动存储
        if auto_store:
            # 存储用户知识
            if knowledge['user']:
                self.put(
                    key='user_knowledge',
                    value=knowledge['user'],
                    user_id=user_id,
                    context=context
                )
            
            # 存储话题列表（作为 JSON 字符串）
            if knowledge['topics']:
                topics_json = json.dumps(knowledge['topics'], ensure_ascii=False)
                self.put(
                    key='topics_list',
                    value=topics_json,
                    user_id=user_id,
                    context=context
                )
            
            # 存储智能体知识
            for agent_key, agent_knowledge in knowledge['agents'].items():
                if agent_knowledge:
                    # agent_key 格式: "topic_id.agent_id"
                    parts = agent_key.split('.', 1)
                    if len(parts) == 2:
                        t_id, a_id = parts
                        self.put(
                            key='agent_knowledge',
                            value=agent_knowledge,
                            user_id=user_id,
                            topic_id=t_id,
                            agent_id=a_id,
                            context=context
                        )
        
        logger.info(f"Pipeline[{self.pipeline_id}] 提取并存储三维信息: user={user_id}, topics={len(knowledge.get('topics', []))}, agents={len(knowledge.get('agents', {}))}")
        return knowledge


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


