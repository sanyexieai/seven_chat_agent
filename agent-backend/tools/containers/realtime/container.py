from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool
from tools.containers.base_container import BaseContainer


class RealtimeContainer(BaseContainer):
    """
    实时跟随容器

    典型用途：把工具执行过程或结果包装成可推送给前端的实时事件流。
    当前仅定义结构，具体的 WebSocket / SSE 推送逻辑后续再接入。
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(container_type=BaseContainer.TYPE_REALTIME, config=config)

    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        # 占位实现：直接透传
        return result


