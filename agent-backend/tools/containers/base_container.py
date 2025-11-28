from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional

from tools.base_tool import BaseTool


class BaseContainer(ABC):
    """
    容器基类

    设计目标：
    - 和工具的 BaseTool 一样，所有具体容器都继承自这个基类；
    - 不同类型的容器（实时跟随 / 浏览器 / 文件 / 代办等）实现各自的工作区、输出处理逻辑；
    - 后续可以按“一个容器一个文件夹”的方式扩展，而不用在 ToolManager 里写一堆 if/else。
    """

    TYPE_NONE = "none"
    TYPE_BROWSER = "browser"
    TYPE_FILE = "file"
    TYPE_REALTIME = "realtime"
    TYPE_TODO = "todo"

    def __init__(
        self,
        container_type: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.container_type = container_type
        self.name = name or container_type
        self.config: Dict[str, Any] = config or {}

    # -------- 公共能力：工作目录 / 配置 --------
    def get_workspace_dir(self, tool: BaseTool) -> Optional[Path]:
        """
        计算当前容器对某个工具的工作目录。

        约定：
        - 优先读取容器自身 config.workspace_dir；
        - 其次读取工具的 container_config.workspace_dir；
        - 都没有时返回 None，由具体子类决定是否需要工作目录。
        """
        workspace_dir = self.config.get("workspace_dir") or tool.get_container_config().get(
            "workspace_dir"
        )
        if not workspace_dir:
            return None
        path = Path(workspace_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # -------- 抽象接口：由子类实现 --------
    @abstractmethod
    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        """
        容器对工具原始执行结果的处理入口。

        一些典型用法：
        - 浏览器容器：把结果渲染为 HTML / 截图文件等，返回文件路径或链接；
        - 文件容器：把结果持久化到工作空间目录，返回文件信息；
        - 实时跟随容器：把结果转成可推送给前端的实时事件流；
        - 代办容器：把结果写入代办列表数据库等。

        返回值会作为 BaseTool.execute_with_result 中的 container_output 或扩展结果使用。
        """

    # 可选扩展：执行前准备
    async def prepare(self, tool: BaseTool) -> None:
        """
        执行前的准备工作（默认不做任何事，子类按需重写），例如：
        - 初始化浏览器实例
        - 准备临时文件夹
        """
        return None


