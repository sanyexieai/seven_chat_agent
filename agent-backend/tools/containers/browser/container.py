from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool
from tools.containers.base_container import BaseContainer


class BrowserContainer(BaseContainer):
    """
    浏览器容器

    典型用途：Web 搜索、网页抓取、页面截图等。
    目前只提供结构和接口，具体的浏览器实现（如 Playwright / Puppeteer）后续再接入。
    """

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(container_type=BaseContainer.TYPE_BROWSER, config=config)

    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        """
        这里可以根据需要，把工具结果转成“浏览器容器”的输出形式。
        先返回原样结果，后续接入真正浏览器逻辑时再扩展。
        """
        # 占位实现：直接透传
        return result


