from typing import Dict, List, Optional, Any
import asyncio
import importlib
import inspect
import os
import sys
import tempfile

from agents.agent_manager import AgentManager
from config.settings import get_settings
from database.database import get_db, SessionLocal
from models.database_models import MCPTool, TemporaryTool, ToolConfig
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from tools.base_tool import BaseTool
from utils.log_helper import get_logger

# 获取logger实例
logger = get_logger("tool_manager")


class MCPToolWrapper(BaseTool):
    """MCP工具包装器"""
    
    def __init__(self, mcp_tool: MCPTool, agent_manager: Optional[AgentManager] = None):
        # 优先使用数据库中存储的容器配置
        container_type = mcp_tool.container_type or BaseTool.CONTAINER_TYPE_NONE
        container_config = mcp_tool.container_config or {}
        
        # 如果数据库中没有配置，则根据工具名称推断容器类型
        if container_type == BaseTool.CONTAINER_TYPE_NONE or not container_config:
            tool_name_lower = mcp_tool.name.lower()
            if any(keyword in tool_name_lower for keyword in ['search', 'browser', 'web', 'crawl']):
                container_type = BaseTool.CONTAINER_TYPE_BROWSER
                container_config = {"browser_type": "headless", "timeout": 30}
            # 如果工具名称包含file、write、read等关键词，绑定文件容器
            elif any(keyword in tool_name_lower for keyword in ['file', 'write', 'read', 'save', 'report']):
                container_type = BaseTool.CONTAINER_TYPE_FILE
                container_config = {"workspace_dir": "mcp_tools"}
        
        super().__init__(
            name=f"mcp_{mcp_tool.server_id}_{mcp_tool.name}",
            description=mcp_tool.description or mcp_tool.display_name,
            container_type=container_type,
            container_config=container_config
        )
        self.mcp_tool = mcp_tool
        self.agent_manager = agent_manager
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行MCP工具"""
        if not self.agent_manager or not self.agent_manager.mcp_helper:
            raise RuntimeError("MCP助手未初始化")
        
        # 获取服务器名称
        db = SessionLocal()
        try:
            from models.database_models import MCPServer
            server = db.query(MCPServer).filter(MCPServer.id == self.mcp_tool.server_id).first()
            if not server:
                raise ValueError(f"MCP服务器 {self.mcp_tool.server_id} 不存在")
            server_name = server.name
        finally:
            db.close()
        
        # 调用MCP工具
        result = await self.agent_manager.mcp_helper.call_tool(
            server_name=server_name,
            tool_name=self.mcp_tool.name,
            **parameters
        )
        return result
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        if self.mcp_tool.input_schema:
            return self.mcp_tool.input_schema
        elif self.mcp_tool.tool_schema:
            return self.mcp_tool.tool_schema.get("input", {})
        else:
            return {
                "type": "object",
                "properties": {},
                "required": []
            }


class TemporaryToolWrapper(BaseTool):
    """临时工具包装器"""
    
    def __init__(self, temp_tool: TemporaryTool):
        # 优先使用数据库中存储的容器配置
        container_type = temp_tool.container_type or BaseTool.CONTAINER_TYPE_NONE
        container_config = temp_tool.container_config or {}
        
        # 如果数据库中没有配置，则根据工具名称和描述推断容器类型
        if container_type == BaseTool.CONTAINER_TYPE_NONE or not container_config:
            tool_name_lower = temp_tool.name.lower()
            description_lower = (temp_tool.description or "").lower()
            combined = f"{tool_name_lower} {description_lower}"
            
            # 如果工具名称或描述包含search、browser等关键词，绑定浏览容器
            if any(keyword in combined for keyword in ['search', 'browser', 'web', 'crawl']):
                container_type = BaseTool.CONTAINER_TYPE_BROWSER
                container_config = {"browser_type": "headless", "timeout": 30}
            # 如果工具名称或描述包含file、write、read、code等关键词，绑定文件容器
            elif any(keyword in combined for keyword in ['file', 'write', 'read', 'save', 'report', 'code', 'python']):
                container_type = BaseTool.CONTAINER_TYPE_FILE
                container_config = {"workspace_dir": "temp_tools"}
        
        super().__init__(
            name=f"temp_{temp_tool.name}",
            description=temp_tool.description or temp_tool.display_name,
            container_type=container_type,
            container_config=container_config
        )
        self.temp_tool = temp_tool
        self._compiled_code = None
        self._module = None
    
    def _compile_code(self):
        """编译工具代码"""
        if self._compiled_code is None:
            try:
                self._compiled_code = compile(self.temp_tool.code, f"<tool_{self.temp_tool.name}>", "exec")
            except SyntaxError as e:
                raise ValueError(f"工具代码语法错误: {e}")
    
    async def execute(self, parameters: Dict[str, Any]) -> Any:
        """执行临时工具"""
        self._compile_code()
        
        # 创建执行环境
        exec_globals = {
            "__name__": f"tool_{self.temp_tool.name}",
            "__builtins__": __builtins__,
        }
        exec_locals = {
            "parameters": parameters,
            "result": None
        }
        
        try:
            # 执行代码
            exec(self._compiled_code, exec_globals, exec_locals)
            
            # 获取结果
            result = exec_locals.get("result")
            if result is None:
                # 如果没有设置result，尝试从exec_locals中获取
                exec_locals.pop("parameters", None)
                exec_locals.pop("__name__", None)
                if len(exec_locals) == 1:
                    result = list(exec_locals.values())[0]
                else:
                    result = exec_locals
            
            return result
        except Exception as e:
            logger.error(f"执行临时工具 {self.temp_tool.name} 失败: {e}")
            raise RuntimeError(f"工具执行失败: {str(e)}")
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数模式"""
        if self.temp_tool.input_schema:
            return self.temp_tool.input_schema
        else:
            return {
                "type": "object",
                "properties": {},
                "required": []
            }

class ToolManager:
    """工具管理器 - 支持内置工具、MCP工具和临时工具"""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.tool_categories: Dict[str, List[str]] = {}
        self.tool_types: Dict[str, str] = {}  # 工具名称 -> 工具类型 (builtin, mcp, temporary)
        self.tool_scores: Dict[str, float] = {}  # 工具名称 -> 评分
        self.agent_manager: Optional[AgentManager] = None

        # 评分相关配置（可通过 .env 覆盖）
        settings = get_settings()
        self.default_score: float = getattr(settings, "TOOL_DEFAULT_SCORE", 3.0)
        self.min_available_score: float = getattr(settings, "TOOL_MIN_AVAILABLE_SCORE", 1.5)
        
    def set_agent_manager(self, agent_manager: AgentManager):
        """设置AgentManager引用"""
        self.agent_manager = agent_manager
        
    async def initialize(self):
        """初始化工具管理器"""
        logger.info("初始化工具管理器...")

        # 1. 扫描并注册所有内置工具（统一从 tools/builtin/*/tool.py 加载）
        await self._discover_and_register_builtin_tools()

        # 2. 注册MCP工具
        await self._register_mcp_tools()

        # 3. 注册临时工具
        await self._register_temporary_tools()

        # 4. 按类别组织工具
        self._organize_tools_by_category()

        # 5. 从数据库加载已有评分（如果有），覆盖默认评分
        self._load_tool_scores_from_db()

        logger.info(f"工具管理器初始化完成，共 {len(self.tools)} 个工具")
    
    async def _discover_and_register_builtin_tools(self):
        """
        扫描并注册所有内置工具。

        约定：
        - 目录结构为 tools/builtin/<tool_name>/tool.py
        - 每个 tool.py 中定义一个或多个继承自 BaseTool 的类
        """
        try:
            base_dir = os.path.dirname(__file__)
            builtin_dir = os.path.join(base_dir, "builtin")

            if not os.path.isdir(builtin_dir):
                logger.warning(f"内置工具目录不存在: {builtin_dir}")
                return

            registered_count = 0

            for entry in os.listdir(builtin_dir):
                entry_path = os.path.join(builtin_dir, entry)
                if not os.path.isdir(entry_path):
                    continue

                module_name = f"tools.builtin.{entry}.tool"
                try:
                    module = importlib.import_module(module_name)
                except Exception as e:
                    logger.warning(f"导入内置工具模块失败: {module_name}, 错误: {e}")
                    continue

                # 反射查找 BaseTool 子类
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseTool) and obj is not BaseTool:
                        try:
                            tool_instance = obj()
                            self.register_tool(tool_instance, tool_type="builtin")
                            registered_count += 1
                        except Exception as inst_err:
                            logger.warning(
                                f"实例化内置工具 {obj.__name__} 失败: {inst_err}"
                            )

            logger.info(f"通过目录扫描注册了 {registered_count} 个内置工具")
        except Exception as e:
            logger.error(f"扫描注册内置工具失败: {e}")
    
    async def _register_mcp_tools(self):
        """从数据库注册MCP工具"""
        try:
            db = SessionLocal()
            try:
                try:
                    mcp_tools = db.query(MCPTool).filter(MCPTool.is_active == True).all()
                except OperationalError as e:
                    # 自动迁移：为 mcp_tools 表添加 score 字段（如果不存在）
                    msg = str(e)
                    if "no such column" in msg and "mcp_tools.score" in msg:
                        logger.warning("检测到 mcp_tools.score 缺失，尝试自动迁移添加 score 字段")
                        self._auto_migrate_score_columns()
                        mcp_tools = db.query(MCPTool).filter(MCPTool.is_active == True).all()
                    else:
                        raise
                for mcp_tool in mcp_tools:
                    tool = MCPToolWrapper(mcp_tool, self.agent_manager)
                    self.register_tool(tool, tool_type="mcp")
                logger.info(f"注册了 {len(mcp_tools)} 个MCP工具")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"注册MCP工具失败: {e}")
    
    async def _register_temporary_tools(self):
        """从数据库注册临时工具"""
        try:
            db = SessionLocal()
            try:
                try:
                    temp_tools = db.query(TemporaryTool).filter(TemporaryTool.is_active == True).all()
                except OperationalError as e:
                    # 自动迁移：为 temporary_tools 表添加 score 字段（如果不存在）
                    msg = str(e)
                    if "no such column" in msg and "temporary_tools.score" in msg:
                        logger.warning("检测到 temporary_tools.score 缺失，尝试自动迁移添加 score 字段")
                        self._auto_migrate_score_columns()
                        temp_tools = db.query(TemporaryTool).filter(TemporaryTool.is_active == True).all()
                    else:
                        raise
                for temp_tool in temp_tools:
                    tool = TemporaryToolWrapper(temp_tool)
                    self.register_tool(tool, tool_type="temporary")
                logger.info(f"注册了 {len(temp_tools)} 个临时工具")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"注册临时工具失败: {e}")
    
    async def _register_default_tools(self):
        """
        旧的默认工具注册逻辑（已废弃，保留以兼容历史代码调用）。

        当前 initialize 已改为使用 _discover_and_register_builtin_tools，
        不再依赖此方法注册新工具。
        """
        logger.info("默认工具注册逻辑已由目录扫描替代，_register_default_tools 不再实际注册工具")
    
    def register_tool(self, tool: BaseTool, tool_type: str = "builtin"):
        """注册工具"""
        self.tools[tool.name] = tool
        self.tool_types[tool.name] = tool_type
        # 初始化工具评分（默认 3.0，取区间[1,5]的中间值），如果已有评分则保留
        if tool.name not in self.tool_scores:
            self.tool_scores[tool.name] = self.default_score
        logger.info(f"注册工具: {tool.name} (类型: {tool_type})")
    
    def unregister_tool(self, tool_name: str):
        """注销工具"""
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.info(f"注销工具: {tool_name}")
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self.tools.get(tool_name)
    
    def get_available_tools(self, tool_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        tools_list = []
        for tool_name, tool in self.tools.items():
            if tool_type and self.tool_types.get(tool_name) != tool_type:
                continue
            score = self.tool_scores.get(tool_name, self.default_score)
            is_available = score >= self.min_available_score
            tools_list.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.get_parameters_schema(),
                "category": self._get_tool_category(tool.name),
                "type": self.tool_types.get(tool_name, "unknown"),
                "score": score,
                "is_available": is_available,
                "container_type": tool.get_container_type(),  # 容器类型
                "container_config": tool.get_container_config()  # 容器配置
            })
        # 按评分从高到低排序，规划节点会优先看到高评分工具
        tools_list.sort(key=lambda t: t.get("score", 1.0), reverse=True)
        return tools_list
    
    def get_tools_by_type(self, tool_type: str) -> List[Dict[str, Any]]:
        """按类型获取工具"""
        return self.get_available_tools(tool_type=tool_type)
    
    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        """按类别获取工具"""
        tool_names = self.tool_categories.get(category, [])
        return [
            {
                "name": self.tools[name].name,
                "description": self.tools[name].description,
                "parameters": self.tools[name].get_parameters_schema(),
                "type": self.tool_types.get(name, "unknown"),
                "container_type": self.tools[name].get_container_type(),  # 容器类型
                "container_config": self.tools[name].get_container_config()  # 容器配置
            }
            for name in tool_names
            if name in self.tools
        ]
    
    def get_categories(self) -> List[str]:
        """获取所有工具类别"""
        return list(self.tool_categories.keys())
    
    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """执行工具

        说明：
        - 如果工具执行过程中抛异常，视为失败，降低评分；异常向上抛出。
        - 如果工具返回结果但内容明显是错误信息（如包含“失败”“错误”“不可用”等），
          也视为逻辑失败，用于调整评分和日志，但仍把结果原样返回给调用方。
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"工具 {tool_name} 不存在")

        # 检查评分阈值，低于阈值的工具视为不可用
        current_score = self.tool_scores.get(tool_name, self.default_score)
        if current_score < self.min_available_score:
            msg = (
                f"工具 {tool_name} 当前评分为 {current_score:.2f}，"
                f"低于可用阈值 {self.min_available_score:.2f}，已被设置为不可用。"
                f"请在工具管理中重置评分后再使用。"
            )
            logger.warning(msg)
            raise RuntimeError(msg)
        
        try:
            result = await tool.execute_with_validation(parameters)

            # 根据结果内容进行成功/失败判定（软失败也要反映到评分和日志）
            is_success = self._is_result_successful(tool_name, result)
            if is_success:
                logger.info(f"工具 {tool_name} 执行成功")
                # 成功时略微提高评分
                self._update_tool_score(tool_name, success=True)
            else:
                logger.warning(f"工具 {tool_name} 执行结果包含错误信息，视为失败")
                # 逻辑失败：降低评分，但仍返回结果给上层（由上层决定如何展示）
                self._update_tool_score(tool_name, success=False)

            return result
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {str(e)}")
            # 失败时降低评分
            self._update_tool_score(tool_name, success=False)
            raise

    def _is_result_successful(self, tool_name: str, result: Any) -> bool:
        """
        根据工具返回结果内容做一次“软判断”是否成功。

        注意：
        - 这里只做启发式判断，不改变工具自身的返回值。
        - 主要用于修正像 web_search 这类内部已经捕获异常并返回“搜索失败: ...”字符串的场景，
          否则从外面看永远是“执行成功”。
        """
        try:
            # 显式 error 字段
            if isinstance(result, dict):
                if result.get("error"):
                    return False

            # 文本结果里包含典型错误关键词时，认为是失败
            if isinstance(result, str):
                error_keywords = ["失败", "错误", "不可用", "异常"]
                if any(kw in result for kw in error_keywords):
                    return False
                # 对 web_search 这种搜索类工具，"未找到关于 ..." 也视为失败，避免误判为成功
                if tool_name == "web_search" and result.startswith("未找到关于 "):
                    return False

            return True
        except Exception as e:
            # 任何判断过程中的异常都不影响主流程，默认按成功处理
            logger.warning(f"判断工具 {tool_name} 结果成功/失败时出错: {e}")
            return True

    def _update_tool_score(self, tool_name: str, success: bool):
        """
        根据执行结果更新工具评分

        - 内存中的 `self.tool_scores` 始终更新
        - 同步回写到数据库对应的 score 字段，保证下次启动后仍然生效
        """
        # 1. 先更新内存分数
        if tool_name not in self.tool_scores:
            # 不存在时从中间值 default_score 开始
            self.tool_scores[tool_name] = self.default_score

        score = self.tool_scores[tool_name]
        if success:
            # 成功轻微加分，向上缓慢收敛
            score += 0.1
        else:
            # 失败重扣分
            score -= 0.5

        # 限制评分范围 [1.0, 5.0]
        score = max(1.0, min(5.0, score))
        self.tool_scores[tool_name] = score
        logger.info(f"工具 {tool_name} 新评分: {score:.2f} (success={success})")

        # 2. 尝试把评分持久化到数据库
        self._persist_tool_score(tool_name, score)

    def _persist_tool_score(self, tool_name: str, score: float) -> None:
        """将工具评分及可用状态持久化到数据库"""
        try:
            db = SessionLocal()
            try:
                tool_type = self.tool_types.get(tool_name)
                is_available = score >= self.min_available_score

                if tool_type == "mcp":
                    # mcp 工具在 DB 中的唯一标识：server_id + name
                    # runtime 名称为 mcp_{server_id}_{name}
                    if tool_name.startswith("mcp_"):
                        parts = tool_name.split("_", 2)
                        # 期望格式：["mcp", "{server_id}", "{name}"]
                        if len(parts) == 3:
                            server_id_str, mcp_name = parts[1], parts[2]
                            try:
                                server_id = int(server_id_str)
                                mcp_row = (
                                    db.query(MCPTool)
                                    .filter(
                                        MCPTool.server_id == server_id,
                                        MCPTool.name == mcp_name,
                                    )
                                    .first()
                                )
                                if mcp_row:
                                    mcp_row.score = score
                                    # 同步可用状态
                                    if hasattr(mcp_row, "is_available"):
                                        mcp_row.is_available = is_available
                                    db.add(mcp_row)
                            except ValueError:
                                # server_id 解析失败时忽略持久化，但不影响内存
                                logger.warning(
                                    f"解析 MCP 工具 server_id 失败，tool_name={tool_name}"
                                )

                elif tool_type == "temporary":
                    # 临时工具：name 唯一
                    temp_row = (
                        db.query(TemporaryTool)
                        .filter(TemporaryTool.name == tool_name)
                        .first()
                    )
                    if temp_row:
                        temp_row.score = score
                        if hasattr(temp_row, "is_available"):
                            temp_row.is_available = is_available
                        db.add(temp_row)

                else:
                    # 其它情况（builtin / 默认）使用 ToolConfig 记录评分
                    cfg = (
                        db.query(ToolConfig)
                        .filter(ToolConfig.tool_name == tool_name)
                        .first()
                    )
                    if cfg:
                        cfg.score = score
                        if hasattr(cfg, "is_available"):
                            cfg.is_available = is_available
                        db.add(cfg)
                    else:
                        # 没有记录时自动创建一条 ToolConfig，保持评分及可用状态可持久化
                        cfg = ToolConfig(
                            tool_name=tool_name,
                            tool_type=tool_type or "builtin",
                            score=score,
                            is_available=is_available,
                        )
                        db.add(cfg)

                db.commit()
            finally:
                db.close()
        except Exception as e:
            # 持久化失败不影响主流程，只打日志方便排查
            logger.warning(f"更新工具 {tool_name} 评分到数据库失败: {e}")

    def reset_tool_score(self, tool_name: str) -> float:
        """
        将指定工具的评分重置为默认值。

        返回重置后的评分。
        """
        if tool_name not in self.tools:
            raise ValueError(f"工具 {tool_name} 不存在")

        self.tool_scores[tool_name] = self.default_score
        logger.info(f"工具 {tool_name} 评分已重置为默认值 {self.default_score:.2f}")
        self._persist_tool_score(tool_name, self.default_score)
        return self.default_score

    def _auto_migrate_score_columns(self) -> None:
        """
        自动为工具相关表添加 score 字段（仅在检测到列缺失时调用）。
        主要针对 SQLite，避免因为手工没跑迁移脚本导致启动报错。
        """
        try:
            db = SessionLocal()
            conn = db.connection()
            dialect = conn.dialect.name

            def has_column_sqlite(table: str, column: str) -> bool:
                result = conn.execute(text(f"PRAGMA table_info({table})"))
                columns = [row[1] for row in result.fetchall()]
                return column in columns

            if dialect == "sqlite":
                # mcp_tools.score
                if not has_column_sqlite("mcp_tools", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE mcp_tools
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 mcp_tools 表添加 score 字段")
                # temporary_tools.score
                if not has_column_sqlite("temporary_tools", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE temporary_tools
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 temporary_tools 表添加 score 字段")
                # tool_configs.score
                if not has_column_sqlite("tool_configs", "score"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE tool_configs
                            ADD COLUMN score REAL DEFAULT 3.0
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 tool_configs 表添加 score 字段")

                # mcp_tools.is_available
                if not has_column_sqlite("mcp_tools", "is_available"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE mcp_tools
                            ADD COLUMN is_available BOOLEAN DEFAULT 1
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 mcp_tools 表添加 is_available 字段")

                # temporary_tools.is_available
                if not has_column_sqlite("temporary_tools", "is_available"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE temporary_tools
                            ADD COLUMN is_available BOOLEAN DEFAULT 1
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 temporary_tools 表添加 is_available 字段")

                # tool_configs.is_available
                if not has_column_sqlite("tool_configs", "is_available"):
                    conn.execute(
                        text(
                            """
                            ALTER TABLE tool_configs
                            ADD COLUMN is_available BOOLEAN DEFAULT 1
                            """
                        )
                    )
                    logger.info("自动迁移: 已为 tool_configs 表添加 is_available 字段")
                db.commit()
            else:
                logger.warning(f"当前数据库方言为 {dialect}，暂不自动迁移 score 字段，请手动执行迁移脚本")
        except Exception as e:
            logger.warning(f"自动迁移工具评分字段失败: {str(e)}")
        finally:
            try:
                db.close()
            except Exception:
                pass
    
    async def execute_tools_chain(self, tool_chain: List[Dict[str, Any]]) -> List[Any]:
        """执行工具链"""
        results = []
        
        for tool_call in tool_chain:
            tool_name = tool_call["tool_name"]
            parameters = tool_call["parameters"]
            
            try:
                result = await self.execute_tool(tool_name, parameters)
                results.append({
                    "tool_name": tool_name,
                    "success": True,
                    "result": result
                })
            except Exception as e:
                results.append({
                    "tool_name": tool_name,
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def _organize_tools_by_category(self):
        """按类别组织工具"""
        self.tool_categories = {
            "search": [],
            "report": [],
            "file": [],
            "utility": []
        }
        
        for tool_name, tool in self.tools.items():
            category = self._get_tool_category(tool_name)
            if category in self.tool_categories:
                self.tool_categories[category].append(tool_name)
    
    def _get_tool_category(self, tool_name: str) -> str:
        """获取工具类别"""
        if "search" in tool_name.lower():
            return "search"
        elif "report" in tool_name.lower() or "analysis" in tool_name.lower():
            return "report"
        elif "file" in tool_name.lower() or "read" in tool_name.lower() or "write" in tool_name.lower():
            return "file"
        else:
            return "utility"
    
    def search_tools(self, query: str) -> List[Dict[str, Any]]:
        """搜索工具"""
        matching_tools = []
        query_lower = query.lower()
        
        for tool in self.tools.values():
            if (query_lower in tool.name.lower() or 
                query_lower in tool.description.lower()):
                matching_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_parameters_schema(),
                    "category": self._get_tool_category(tool.name),
                    "type": self.tool_types.get(tool.name, "unknown"),
                    "container_type": tool.get_container_type(),  # 容器类型
                    "container_config": tool.get_container_config()  # 容器配置
                })
        
        return matching_tools
    
    def get_tool_statistics(self) -> Dict[str, Any]:
        """获取工具统计信息"""
        total_tools = len(self.tools)
        category_stats = {}
        type_stats = {}
        
        for category, tool_names in self.tool_categories.items():
            category_stats[category] = len(tool_names)
        
        for tool_type in self.tool_types.values():
            type_stats[tool_type] = type_stats.get(tool_type, 0) + 1
        
        return {
            "total_tools": total_tools,
            "categories": category_stats,
            "categories_list": list(self.tool_categories.keys()),
            "types": type_stats,
            "types_list": list(type_stats.keys())
        }
    
    async def reload_tools(self):
        """重新加载所有工具"""
        logger.info("重新加载工具...")
        self.tools.clear()
        self.tool_types.clear()
        self.tool_scores.clear()
        await self.initialize()
    
    async def reload_mcp_tools(self):
        """重新加载MCP工具"""
        logger.info("重新加载MCP工具...")
        # 移除现有的MCP工具
        tools_to_remove = [name for name, tool_type in self.tool_types.items() if tool_type == "mcp"]
        for name in tools_to_remove:
            if name in self.tools:
                del self.tools[name]
                del self.tool_types[name]
        # 重新注册MCP工具
        await self._register_mcp_tools()
        # 重新加载评分
        self._load_tool_scores_from_db()
    
    async def reload_temporary_tools(self):
        """重新加载临时工具"""
        logger.info("重新加载临时工具...")
        # 移除现有的临时工具
        tools_to_remove = [name for name, tool_type in self.tool_types.items() if tool_type == "temporary"]
        for name in tools_to_remove:
            if name in self.tools:
                del self.tools[name]
                del self.tool_types[name]
        # 重新注册临时工具
        await self._register_temporary_tools()
        # 重新加载评分
        self._load_tool_scores_from_db()

    def _load_tool_scores_from_db(self):
        """从数据库加载工具评分，覆盖内存中的默认评分"""
        try:
            db = SessionLocal()
            # MCP 工具评分
            mcp_tools = db.query(MCPTool).all()
            for t in mcp_tools:
                if t.score is not None:
                    tool_name = f"mcp_{t.server_id}_{t.name}"
                    self.tool_scores[tool_name] = float(t.score)
            # 临时工具评分
            temp_tools = db.query(TemporaryTool).all()
            for t in temp_tools:
                if t.score is not None:
                    tool_name = f"temp_{t.name}"
                    self.tool_scores[tool_name] = float(t.score)
            # 内置工具评分（ToolConfig）
            builtin_configs = db.query(ToolConfig).filter(ToolConfig.tool_type == "builtin").all()
            for cfg in builtin_configs:
                if cfg.score is not None:
                    self.tool_scores[cfg.tool_name] = float(cfg.score)
            db.close()
            logger.info(f"从数据库加载工具评分完成，数量: {len(self.tool_scores)}")
        except Exception as e:
            logger.warning(f"从数据库加载工具评分失败: {str(e)}")