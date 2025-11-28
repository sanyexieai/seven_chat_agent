from __future__ import annotations

from typing import Any, Dict, Optional, Type

from tools.base_tool import BaseTool
from tools.containers.base_container import BaseContainer
from tools.containers.browser.container import BrowserContainer
from tools.containers.file.container import FileContainer
from tools.containers.realtime.container import RealtimeContainer
from tools.containers.todo.container import TodoContainer


class ContainerManager:
    """
    容器管理器

    职责：
    - 根据工具声明的 container_type 返回对应的容器实例；
    - 统一调用容器的 handle_result，对工具原始结果做“容器级”处理；
    - 后续如果要扩展新容器，只需要在 containers 目录下加子类并在这里注册。
    """

    def __init__(self) -> None:
        self._registry: Dict[str, Type[BaseContainer]] = {
            BaseContainer.TYPE_BROWSER: BrowserContainer,
            BaseContainer.TYPE_FILE: FileContainer,
            BaseContainer.TYPE_REALTIME: RealtimeContainer,
            BaseContainer.TYPE_TODO: TodoContainer,
        }

    def get_container(self, tool: BaseTool) -> Optional[BaseContainer]:
        container_type = tool.get_container_type()
        if not container_type or container_type == BaseContainer.TYPE_NONE:
            return None

        cls = self._registry.get(container_type)
        if not cls:
            return None

        # 容器可以读取工具本身的 container_config 作为默认配置
        config = tool.get_container_config() or {}
        return cls(config=config)

    async def handle_result(self, tool: BaseTool, result: Any) -> Any:
        """
        对工具执行结果做容器级处理。
        - 如果没有绑定容器，直接返回原始结果；
        - 如果有容器，先调用 prepare，再调用 handle_result。
        """
        container = self.get_container(tool)
        if not container:
            return result

        await container.prepare(tool)
        processed = await container.handle_result(tool, result)
        return processed


