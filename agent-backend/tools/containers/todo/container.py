from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool
from tools.containers.base_container import BaseContainer


class TodoContainer(BaseContainer):
    """
    代办容器

    典型用途：把工具输出写入“待办事项 / 任务列表”之类的数据结构。
    目前只提供接口，真正的待办存储（数据库 / 外部服务）后续再实现。
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(container_type=BaseContainer.TYPE_TODO, config=config)

    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        # 占位实现：直接透传
        return result


